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

隐私注意：本适配器会把输入照片压缩后（base64）发送到你配置的端点——这是它与引擎
其它路径（纯本地）的唯一例外。端点强制 https（仅本机回环地址允许 http）。

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
    "5. 坐标 0..1000，每设计 14~22 个图元（输出 token 有限：务必完整输出全部图元与字段，宁可略少也不可截断或省略结尾）；"
    "素材纹章为大面积有机图形：主母题优先用有机面图元（blob 团块/flame 焰瓣/ribbon 绶带）承载，"
    "饰件用 wing/laurel/sunburst/star/bezier/banner，勿全靠直线 poly 拼形。\n"
    "参考示例（你的输出应达到或超过该示例的图元数量与构图丰富度）：\n"
    "{\"shapes\":[{\"t\":\"circle\",\"cx\":500,\"cy\":500,\"r\":330,\"fill\":0.88,\"stroke\":0.22,\"w\":18},"
    "{\"t\":\"circle\",\"cx\":500,\"cy\":500,\"r\":280,\"fill\":0.55,\"stroke\":0.22,\"w\":8},"
    "{\"t\":\"blob\",\"cx\":500,\"cy\":470,\"r\":190,\"lobes\":5,\"amp\":0.28,\"fill\":0.55,\"stroke\":0.22,\"w\":10},"
    "{\"t\":\"flame\",\"cx\":500,\"cy\":430,\"h\":220,\"w0\":110,\"lean\":0.1,\"fill\":0.88,\"stroke\":0.22,\"w\":8},"
    "{\"t\":\"wing\",\"cx\":240,\"cy\":340,\"length\":230,\"spread\":120,\"angle\":35,\"feathers\":5,\"stroke\":0.22,\"w\":8},"
    "{\"t\":\"wing\",\"cx\":760,\"cy\":340,\"length\":230,\"spread\":120,\"angle\":145,\"feathers\":5,\"stroke\":0.22,\"w\":8},"
    "{\"t\":\"ribbon\",\"x0\":150,\"y0\":800,\"x1\":850,\"y1\":800,\"width\":64,\"sway\":60,\"waves\":2,\"fill\":0.55,\"stroke\":0.22,\"w\":8},"
    "{\"t\":\"star\",\"cx\":500,\"cy\":470,\"r1\":70,\"points\":6,\"rot\":-90,\"fill\":0.88,\"stroke\":0.22,\"w\":8},"
    "{\"t\":\"sunburst\",\"cx\":500,\"cy\":500,\"r0\":60,\"r1\":260,\"count\":16,\"stroke\":0.55,\"w\":6},"
    "{\"t\":\"line\",\"x1\":300,\"y1\":500,\"x2\":700,\"y2\":500,\"lum\":0.22,\"w\":6}]}\n"
    "输出要求：仅输出一行严格 JSON，格式 {\"shapes\":[...]}；图元类型限定为 "
    "poly/circle/line/arc/rect/bezier/star/sunburst/laurel/banner/blob/ribbon/wing/flame；"
    "poly 用 {\"t\":\"poly\",\"pts\":[[x,y],...],\"fill\":0.55,\"stroke\":0.22,\"w\":10}，"
    "circle 用 {\"t\":\"circle\",\"cx\":500,\"cy\":500,\"r\":300,...}，"
    "line 用 {\"t\":\"line\",\"x1\":0,\"y1\":0,\"x2\":0,\"y2\":0,\"lum\":0.22,\"w\":8}，"
    "arc 用 {\"t\":\"arc\",\"cx\":500,\"cy\":500,\"r\":300,\"a0\":0,\"a1\":360,...}，"
    "rect 用 {\"t\":\"rect\",\"x0\":0,\"y0\":0,\"x1\":0,\"y1\":0,...}，"
    "bezier 用 {\"t\":\"bezier\",\"p0\":[x,y],\"p1\":[x,y],\"p2\":[x,y],\"p3\":[x,y],...}，"
    "star 用 {\"t\":\"star\",\"cx\":500,\"cy\":500,\"r1\":20,\"points\":5,\"rot\":-90,...}，"
    "sunburst 用 {\"t\":\"sunburst\",\"cx\":500,\"cy\":500,\"r0\":40,\"r1\":200,\"count\":16,...}，"
    "laurel 用 {\"t\":\"laurel\",\"cx\":500,\"cy\":500,\"length\":240,\"angle\":30,\"branches\":9,...}，"
    "banner 用 {\"t\":\"banner\",\"x0\":0,\"y0\":0,\"x1\":0,\"y1\":0,\"fold\":26,...}，"
    "blob 用 {\"t\":\"blob\",\"cx\":500,\"cy\":500,\"r\":190,\"lobes\":5,\"amp\":0.28,\"rot\":0,...}（有机团块：lobes 瓣数 3~8，amp 起伏 0.1~0.45），"
    "ribbon 用 {\"t\":\"ribbon\",\"x0\":150,\"y0\":800,\"x1\":850,\"y1\":800,\"width\":64,\"sway\":60,\"waves\":2,...}（绶带：sway 摆动幅度 ±，waves 褶皱数），"
    "wing 用 {\"t\":\"wing\",\"cx\":240,\"cy\":340,\"length\":230,\"spread\":120,\"angle\":35,\"feathers\":5,...}（翼：羽片 3~9，angle 羽轴方向），"
    "flame 用 {\"t\":\"flame\",\"cx\":500,\"cy\":430,\"h\":220,\"w0\":110,\"lean\":0.1,\"rot\":-90,...}（焰/瓣：基部在 cx,cy 向 rot 方向伸展，lean 偏向 ±0.8）。"
    "不要输出任何解释、markdown 或代码围栏；必须输出完整闭合、可被 JSON 解析的一行对象，"
    "若空间不足请减少图元数量，而不是省略字段或结尾。"
)


def image_to_data_uri(path, max_dim=1024):
    """读图 → 限尺寸压缩 → base64 JPEG data URI（压缩 token 开销）"""
    from PIL import Image
    img = Image.open(path)
    img.load()
    be.check_input_pixels(img, "视觉 API 输入")
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
    except urllib.error.URLError as e:
        raise SystemExit(f"[error] 无法连接视觉 API 端点：{e.reason}")
    try:
        content = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise SystemExit(
            "[error] API 响应结构异常（choices/message/content 缺失），"
            "请确认端点为 OpenAI 兼容 chat/completions。响应片段：\n"
            + json.dumps(resp, ensure_ascii=False)[:300])
    if not isinstance(content, str):
        raise SystemExit(
            "[error] API 响应的 content 不是文本（可能触发了内容过滤或端点不兼容）。响应片段：\n"
            + json.dumps(resp, ensure_ascii=False)[:300])
    try:
        design = extract_json(content)
    except json.JSONDecodeError:
        raise SystemExit(
            "[error] 模型回复无法解析为 JSON（可能因输出被 max_tokens 截断）。\n"
            "端点允许时可尝试 --max-tokens 调大后重试。回复片段：\n" + content[:300])
    if (not isinstance(design, dict)
            or not isinstance(design.get("shapes"), list) or not design["shapes"]):
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

    # 明文传输防护：照片（base64）与 Bearer 密钥都会发往该端点，拒绝非加密的非本机地址
    base = args.base_url.strip()
    if base.startswith("http://"):
        host = base[len("http://"):].split("/", 1)[0].split(":", 1)[0].lower()
        if host not in ("localhost", "127.0.0.1", "::1", "[::1]"):
            raise SystemExit(
                f"[error] OPENAI_BASE_URL 指向明文 http://{host}：API 密钥与照片将以明文传输。\n"
                "请改用 https:// 端点；仅本机回环地址（localhost/127.0.0.1）允许 http。")

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
