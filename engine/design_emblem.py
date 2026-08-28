# -*- coding: utf-8 -*-
"""
design_emblem.py · OpenAI 兼容视觉 API 适配器
============================================
给「没有自带视觉能力」的 agent 环境补齐 AI 纹章主路径：
    读图 → 视觉 API 产出设计稿 JSON →（可选）本地渲染 PNG
仅依赖 stdlib + numpy/Pillow（与本仓库一致），无新增第三方包。

配置（全部走环境变量，绝不写入仓库）：
    OPENAI_API_KEY    必填，API 密钥
    OPENAI_BASE_URL   可选，默认 https://api.openai.com/v1
                      （任何 OpenAI 兼容端点均可，如本地/中转服务）
    OPENAI_MODEL      可选，默认 gpt-4o-mini（需支持图片输入）
    OPENAI_MAX_TOKENS 可选，默认 1024（GLM-4V-Flash 上限；其它端点可调大，如 4000）

用法：
    $env:OPENAI_API_KEY='...'
    python engine/design_emblem.py photo.jpg -o design.json
    python engine/design_emblem.py photo.jpg -o design.json --render out.png `
        --style arknights --tone silver --text "阿米娅"
输出 JSON 与引擎 `--mode emblem --emblem-design` 完全兼容。
"""
import argparse
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import badge_engine as be

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = (
    "你是蚀刻章纹章设计师，负责把照片抽象成可渲染的几何图元设计稿。\n"
    "规则：\n"
    "1. 「转译」不是「临摹」：提取主体 1~2 个标志性特征作母题，与纹章元素组合"
    "（交叉元素、环带包围、放射星芒、菱形/星形饰件、底部字带收口）；\n"
    "2. 对称（或 X 形中心对称）构图，主母题占中央约 55~65%，饰件环绕；\n"
    "3. 三档硬明度 0.22 / 0.55 / 0.88；粗轮廓（宽 14~22）配细内部线（宽 6~10）；\n"
    "4. 若照片与游戏相关（如明日方舟角色），先做游戏关联分析：识别角色/物件，"
    "提取其标志性符号为母题，不得输出与游戏无关的泛化图形；\n"
    "5. 坐标 0..1000，每设计 12~20 个图元（输出 token 有限：务必完整输出全部图元与字段，宁可略少也不可截断或省略结尾）；装饰原语优先（bezier/laurel/sunburst/star/banner）。\n"
    "参考示例（你的输出应达到或超过该示例的图元数量与构图丰富度）：\n"
    "{\"shapes\":[{\"t\":\"circle\",\"cx\":500,\"cy\":500,\"r\":330,\"fill\":0.88,\"stroke\":0.22,\"w\":18},"
    "{\"t\":\"circle\",\"cx\":500,\"cy\":500,\"r\":280,\"fill\":0.55,\"stroke\":0.22,\"w\":8},"
    "{\"t\":\"star\",\"cx\":500,\"cy\":500,\"r1\":180,\"points\":6,\"rot\":-90,\"fill\":0.88,\"stroke\":0.22,\"w\":10},"
    "{\"t\":\"sunburst\",\"cx\":500,\"cy\":500,\"r0\":60,\"r1\":260,\"count\":16,\"stroke\":0.55,\"w\":6},"
    "{\"t\":\"laurel\",\"cx\":320,\"cy\":640,\"length\":200,\"angle\":40,\"branches\":8,\"stroke\":0.22,\"w\":8},"
    "{\"t\":\"laurel\",\"cx\":680,\"cy\":640,\"length\":200,\"angle\":140,\"branches\":8,\"stroke\":0.22,\"w\":8},"
    "{\"t\":\"banner\",\"x0\":150,\"y0\":830,\"x1\":850,\"y1\":830,\"fold\":26,\"fill\":0.55,\"stroke\":0.22,\"w\":10},"
    "{\"t\":\"line\",\"x1\":300,\"y1\":500,\"x2\":700,\"y2\":500,\"lum\":0.22,\"w\":6}]}\n"
    "输出要求：仅输出一行严格 JSON，格式 {\"shapes\":[...]}；图元类型限定为 "
    "poly/circle/line/arc/rect/bezier/star/sunburst/laurel/banner；"
    "poly 用 {\"t\":\"poly\",\"pts\":[[x,y],...],\"fill\":0.55,\"stroke\":0.22,\"w\":10}，"
    "circle 用 {\"t\":\"circle\",\"cx\":500,\"cy\":500,\"r\":300,...}，"
    "line 用 {\"t\":\"line\",\"x1\":0,\"y1\":0,\"x2\":0,\"y2\":0,\"lum\":0.22,\"w\":8}，"
    "arc 用 {\"t\":\"arc\",\"cx\":500,\"cy\":500,\"r\":300,\"a0\":0,\"a1\":360,...}，"
    "rect 用 {\"t\":\"rect\",\"x0\":0,\"y0\":0,\"x1\":0,\"y1\":0,...}，"
    "bezier 用 {\"t\":\"bezier\",\"p0\":[x,y],\"p1\":[x,y],\"p2\":[x,y],\"p3\":[x,y],...}，"
    "star 用 {\"t\":\"star\",\"cx\":500,\"cy\":500,\"r1\":20,\"points\":5,\"rot\":-90,...}，"
    "sunburst 用 {\"t\":\"sunburst\",\"cx\":500,\"cy\":500,\"r0\":40,\"r1\":200,\"count\":16,...}，"
    "laurel 用 {\"t\":\"laurel\",\"cx\":500,\"cy\":500,\"length\":240,\"angle\":30,\"branches\":9,...}，"
    "banner 用 {\"t\":\"banner\",\"x0\":0,\"y0\":0,\"x1\":0,\"y1\":0,\"fold\":26,...}。"
    "不要输出任何解释、markdown 或代码围栏；必须输出完整闭合、可被 JSON 解析的一行对象，"
    "若空间不足请减少图元数量，而不是省略字段或结尾。"
)


def image_to_data_uri(path, max_dim=1024):
    """读图 → 限尺寸压缩 → base64 JPEG data URI（压缩 token 开销）"""
    from PIL import Image
    img = Image.open(path)
    img.load()
    img = img.convert("RGB")
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def extract_json(text):
    """从模型回复中稳健提取 JSON 对象（容忍代码围栏/前后杂质）"""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            return json.loads(t[start:end + 1])
        raise


def call_vision(data_uri, api_key, base_url, model, timeout=180, max_tokens=1024):
    """调用 OpenAI 兼容 chat/completions（图片 data URI），返回设计稿 dict"""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.6,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "请为这张图片设计纹章，输出严格 JSON。"},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]},
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"[error] API 返回 HTTP {e.code}: {detail}")
    content = resp["choices"][0]["message"]["content"]
    try:
        design = extract_json(content)
    except json.JSONDecodeError:
        raise SystemExit(
            "[error] 模型回复无法解析为 JSON（可能因输出被 max_tokens 截断）。\n"
            "端点允许时可尝试 --max-tokens 调大后重试。回复片段：\n" + content[:300])
    if not isinstance(design.get("shapes"), list) or not design["shapes"]:
        raise SystemExit("[error] 模型回复不含有效 shapes 列表，请重试或换模型")
    return design


def main():
    ap = argparse.ArgumentParser(description="视觉 API 设计稿生成 + 可选本地渲染")
    ap.add_argument("input", help="输入照片路径")
    ap.add_argument("-o", "--output", default=None, help="设计稿 JSON 输出路径")
    ap.add_argument("--render", default=None, help="同时渲染 PNG 的输出路径")
    ap.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--max-tokens", type=int,
                    default=int(os.environ.get("OPENAI_MAX_TOKENS", "1024")),
                    help="回复最大 token 数（GLM-4V-Flash 上限 1024；其它端点可调大）")
    # 渲染参数（与 badge_engine 对齐，仅 --render 时使用）
    ap.add_argument("--style", default="arknights", choices=["arknights", "endfield", "candy"])
    ap.add_argument("--tone", default=None)
    ap.add_argument("--text", default="蚀刻勋章")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--serial", default="")
    ap.add_argument("--emblem-style", default="lineart", choices=["lineart", "flat"])
    ap.add_argument("--polarity", default="dark-on-light", choices=["dark-on-light", "light-on-dark"])
    ap.add_argument("--carve", default="machine", choices=["machine", "hand"])
    args = ap.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "[error] 未设置 OPENAI_API_KEY。请先执行：\n"
            "  $env:OPENAI_API_KEY='你的密钥'\n"
            "（可选：$env:OPENAI_BASE_URL / $env:OPENAI_MODEL 覆盖默认端点与模型）")
    try:
        api_key.encode("ascii")
    except UnicodeEncodeError:
        raise SystemExit(
            "[error] OPENAI_API_KEY 含非 ASCII 字符（可能仍是占位文本，未替换为真实密钥）。\n"
            "请先执行 $env:OPENAI_API_KEY='真实密钥' 后重试。")

    data_uri = image_to_data_uri(args.input)
    design = call_vision(data_uri, api_key, args.base_url, args.model, args.timeout,
                         args.max_tokens)

    out = args.output or (os.path.splitext(os.path.basename(args.input))[0] + "_design.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(design, f, ensure_ascii=False, separators=(",", ":"))
    print(out)

    if args.render:
        path, warn = be.generate(
            args.input, args.render, args.style, args.tone, args.text,
            args.subtitle, args.serial, False, 1.0, 1.0, 26.0, "",
            "emblem", out, args.emblem_style, args.polarity, args.carve)
        print(path)
        if warn:
            print(warn, file=sys.stderr)


if __name__ == "__main__":
    main()
