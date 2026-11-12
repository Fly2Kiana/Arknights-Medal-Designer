# -*- coding: utf-8 -*-
"""
方舟蚀刻章设计器引擎 v5 · Arknights Medal Designer Engine（参照公开官方素材归纳）
=========================================================
依据 PRTS 公开官方素材归纳：
  明日方舟蚀刻章 = 尖角正六边形(pointy-top, 宽高比≈0.87) + 3~4层同心细线套环
                   + 石板蓝哑光网点底 + 银白细线描符号纹章 + 嵌入式横字带
                   （无发光/无渐变/无投影；金色仅活动金章；镀层版为全息虹彩）
  终末地蚀刻章 = 尖角正六边形(实测宽高比≈0.88) + 单细深描边
                   + 阳极氧化拉丝金属反光（镜面高光带 + 青绿虹移）+ 章面极简文字
                   （三家族轮廓统一，无切角、无外凸挂扣；名牌框/圆盘/触点均在章面内部）

用法:
  python badge_engine.py <input> [-o out.png] [--style arknights|endfield]
      [--tone silver|gold|plated] [--text 主文本] [--subtitle 副文本]
      [--serial 编号] [--no-matting] [--line-strength 1.0] [--detail 1.0]
"""
import argparse
import colorsys
import json
import math
import os
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef_layer_geom import CORNER_SIZE as EF_CORNER_SIZE  # noqa: E402
from ef_layer_geom import PLATE as EF_PLATE  # 装饰层落笔几何单一事实源（纪律 ⑬）
from ef_layer_geom import corner_origins as _ef_corner_origins  # noqa: E402
from ef_layer_geom import annot_ring as _ef_annot_ring  # 注记背景环带 = 深度尺同一张圈  # noqa: E402

# ----------------------------------------------------------------------------
# 字体
# ----------------------------------------------------------------------------
FONT_DIRS = [r"C:\Windows\Fonts", "/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
             "/Library/Fonts", "/usr/share/fonts", "/usr/share/fonts/truetype",
             "/usr/share/fonts/opentype", "/usr/local/share/fonts"]


def _find_font(candidates):
    for d in FONT_DIRS:
        for name in candidates:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None


FONT_CN = _find_font(["msyh.ttc", "msyhbd.ttc", "simhei.ttf",
                      "PingFang.ttc", "Hiragino Sans GB.ttc",
                      "NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf",
                      "wqy-microhei.ttc", "wqy-zenhei.ttc"])
FONT_CN_BOLD = _find_font(["msyhbd.ttc", "msyh.ttc", "simhei.ttf",
                           "PingFang.ttc", "Hiragino Sans GB.ttc",
                           "NotoSansCJK-Bold.ttc", "NotoSansCJKsc-Bold.otf"])
FONT_CN_ROUND = _find_font(["simyou.ttf", "msyhbd.ttc", "msyh.ttc",
                            "Hiragino Maru Gothic ProN W4.ttc", "wqy-microhei.ttc"])  # 幼圆：Q弹感
FONT_EN_BLACK = _find_font(["bahnschrift.ttf", "ariblk.ttf", "arialbd.ttf", "impact.ttf",
                            "DejaVuSans-Bold.ttf"])  # DIN 科技体
FONT_EN_ROUND = _find_font(["arlrdbd.ttf", "bahnschrift.ttf", "ariblk.ttf",
                            "Hiragino Maru Gothic ProN W4.ttc"])  # Arial Rounded：圆体英文
FONT_MONO = _find_font(["consola.ttf", "Menlo.ttc", "DejaVuSansMono.ttf"])


def load_font(path, size):
    if path is None:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(path, int(size))
    except Exception:
        return ImageFont.load_default()


def draw_tracked_text(d, text, cx, y, font, fill, tracking=4, anchor="center",
                      shadow=None):
    """字距跟踪 + 精确基线居中绘制（修复错位问题）"""
    widths = [d.textlength(c, font=font) for c in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x0 = cx - total / 2 if anchor == "center" else cx
    # 精确垂直居中（用真实字形盒高，不用 font.size 名义值）
    bbox = font.getbbox(text)
    asc, desc = bbox[1], bbox[3]
    cap_h = desc - asc
    y_adj = y - (asc + desc) / 2
    for i, c in enumerate(text):
        if shadow:
            d.text((x0 + 2, y_adj + 2), c, font=font, fill=shadow)
        d.text((x0, y_adj), c, font=font, fill=fill)
        x0 += widths[i] + tracking
    return total, cap_h


# ----------------------------------------------------------------------------
# 一、主体提取（v3 同版：背景主色屏障 + 泛洪 + 多部件 + 填洞）
# ----------------------------------------------------------------------------

def _border_palette(a, n_clusters=6):
    h, w = a.shape[:2]
    border = np.concatenate([a[0, :, :], a[-1, :, :], a[:, 0, :], a[:, -1, :]])
    idx = np.linspace(0, len(border) - 1, n_clusters).astype(int)
    centers = border[idx].astype(np.float64)
    for _ in range(10):
        d = ((border[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
        lab = d.argmin(1)
        for c in range(n_clusters):
            sel = border[lab == c]
            if len(sel):
                centers[c] = sel.mean(0)
    return centers


def _flood_bg(a, tol_local, tol_global, barrier):
    h, w = a.shape[:2]
    centers = _border_palette(a)
    visited = np.zeros((h, w), dtype=bool)
    q = deque()

    def visit(y, x):
        if not visited[y, x] and not barrier[y, x]:
            visited[y, x] = True
            q.append((y, x))

    for x in range(w):
        visit(0, x)
        visit(h - 1, x)
    for y in range(h):
        visit(y, 0)
        visit(y, w - 1)

    tl2, tg2 = tol_local ** 2 * 3.0, tol_global ** 2 * 3.0
    while q:
        y, x = q.popleft()
        c0 = a[y, x]
        dg = ((centers - c0) ** 2).sum(-1).min()
        absorb_all = dg <= tg2
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and not barrier[ny, nx]:
                if absorb_all:
                    visited[ny, nx] = True
                    q.append((ny, nx))
                else:
                    d = a[ny, nx] - c0
                    if float(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) <= tl2:
                        visited[ny, nx] = True
                        q.append((ny, nx))
    return visited


def _main_components(mask):
    h, w = mask.shape
    lbl = np.zeros((h, w), dtype=np.int32)
    sizes = {}
    cur = 0
    for yy in range(h):
        row = mask[yy]
        for xx in range(w):
            if row[xx] and lbl[yy, xx] == 0:
                cur += 1
                size, qq = 0, deque([(yy, xx)])
                lbl[yy, xx] = cur
                while qq:
                    cy, cx = qq.popleft()
                    size += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and lbl[ny, nx] == 0:
                            lbl[ny, nx] = cur
                            qq.append((ny, nx))
                sizes[cur] = size
    if not sizes:
        return mask, {}
    biggest = max(sizes.values())
    min_keep = max(int(biggest * 0.06), int(h * w * 0.002), 64)
    keep = np.zeros_like(mask)
    for lid, sz in sizes.items():
        if sz >= min_keep:
            keep |= lbl == lid
    return keep, sizes


def _fill_holes(mask):
    h, w = mask.shape
    inv = ~mask
    outside = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if inv[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if inv[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and inv[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                q.append((ny, nx))
    return mask | (inv & ~outside)


# 输入像素上限：显式防线，早于 Pillow 默认 DecompressionBomb 告警（约 1.79 亿像素）触发
MAX_INPUT_PIXELS = 80_000_000


def check_input_pixels(img: Image.Image, source: str = "输入"):
    if img.width * img.height > MAX_INPUT_PIXELS:
        raise SystemExit(
            f"[error] {source}图像 {img.width}x{img.height}"
            f"（{img.width * img.height // 1_000_000}MP）超过 {MAX_INPUT_PIXELS // 1_000_000}MP 上限，"
            "请先缩小图片后重试（防御解压炸弹）")


def extract_subject(img: Image.Image, tolerance: float = 26.0):
    img = img.convert("RGB")
    max_dim = 760
    scale = min(1.0, max_dim / max(img.size))
    work = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                      Image.BILINEAR) if scale < 1.0 else img.copy()
    a = np.asarray(work).astype(np.float32)
    centers = _border_palette(a, 6)
    dbg = np.sqrt(((a[:, :, None, :] - centers[None, None, :, :]) ** 2).sum(-1).min(-1))
    barrier = dbg >= tolerance + 30
    core_bg = dbg <= tolerance

    bg = _flood_bg(a, tolerance, tolerance + 8, barrier) | core_bg
    fg = ~bg
    coverage = float(fg.mean())
    if coverage < 0.04 or coverage > 0.96:
        bg = _flood_bg(a, tolerance * 0.62, tolerance * 0.62 + 5, barrier)
        fg = ~bg
        coverage = float(fg.mean())
    if coverage < 0.04 or coverage > 0.96:
        return img.convert("RGBA"), coverage

    fg, sizes = _main_components(fg)
    # 碎片化检测：主体被切成离散碎片时，宁可整图回退也不要输出碎片
    if sizes:
        total = sum(sizes.values())
        biggest = max(sizes.values())
        fragmented = biggest < total * 0.55 or len(sizes) >= 6
        if fragmented:
            return img.convert("RGBA"), -1.0
    fg = _fill_holes(fg)
    m = Image.fromarray((fg * 255).astype(np.uint8), "L")
    m = m.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    m = m.filter(ImageFilter.GaussianBlur(1.4))
    alpha = m.resize(img.size, Image.LANCZOS)
    out = img.convert("RGBA")
    out.putalpha(alpha)
    return out, coverage


def crop_to_subject(rgba, pad_ratio=0.03):
    bbox = rgba.getchannel("A").getbbox()
    if not bbox:
        return rgba
    l, t, r, b = bbox
    pw, ph = int((r - l) * pad_ratio), int((b - t) * pad_ratio)
    l, t = max(0, l - pw), max(0, t - ph)
    r, b = min(rgba.width, r + pw), min(rgba.height, b + ph)
    return rgba.crop((l, t, r, b))


# ----------------------------------------------------------------------------
# 一·〇、可选 AI 抠图后端（onnxruntime + u2net 族模型；零硬编码路径）
#   开关：MEDAL_AI_MATTING=1 启用；模型：MEDAL_MATTING_MODEL 指向 .onnx 文件
#   （如 silueta/u2netp）。不可用或失败一律静默回退经典抠图，不影响默认行为。
# ----------------------------------------------------------------------------

def _find_matting_model():
    env = os.environ.get("MEDAL_MATTING_MODEL", "").strip()
    if env and os.path.isfile(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, os.pardir, "models", "silueta.onnx"),
              os.path.join(os.path.expanduser("~"), ".medal", "models", "silueta.onnx")):
        if os.path.isfile(p):
            return p
    return None


def ai_matting_enabled():
    """装了模型就默认启用；MEDAL_AI_MATTING=0 显式关掉。

    旧口径是「必须显式 MEDAL_AI_MATTING=1」——模型已随仓库落位，还要调用方记得设
    环境变量，等于线上永远跑经典抠图（真照片覆盖率 3% ⇒ 整图回退 ⇒ 章面糊成一团）。
    """
    env = os.environ.get("MEDAL_AI_MATTING", "").strip().lower()
    if env in ("0", "false", "off", "no"):
        return False
    if env in ("1", "true", "on", "yes"):
        return True
    return _find_matting_model() is not None


def ai_matting(img: Image.Image):
    """U²-Net 族 salient object detection 抠图。返回 RGBA 或 None（不可用/失败）。"""
    try:
        import onnxruntime as ort
    except ImportError:
        return None
    model_path = _find_matting_model()
    if not model_path:
        return None
    try:
        sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        inp = sess.get_inputs()[0]
        # u2net 族固定 320x320 输入；shape 可能带动态维度
        w = inp.shape[2] if isinstance(inp.shape[2], int) and inp.shape[2] > 0 else 320
        h = inp.shape[3] if isinstance(inp.shape[3], int) and inp.shape[3] > 0 else 320
        small = img.convert("RGB").resize((w, h), Image.BILINEAR)
        x = np.asarray(small, dtype=np.float32) / 255.0
        x = (x - np.array([0.485, 0.456, 0.406], dtype=np.float32)) \
            / np.array([0.229, 0.224, 0.225], dtype=np.float32)
        x = x.transpose(2, 0, 1)[None]
        out = sess.run(None, {inp.name: x})[0]
        out = np.squeeze(out)
        if out.ndim != 2 or out.max() - out.min() < 1e-6:
            return None
        out = (out - out.min()) / (out.max() - out.min())
        mask = Image.fromarray((out * 255).astype(np.uint8), "L").resize(
            img.size, Image.LANCZOS)
        rgba = img.convert("RGBA")
        rgba.putalpha(mask)
        return rgba
    except Exception as e:   # 任何推理失败都回退，不中断出章
        print(f"[warn] AI 抠图失败，回退经典算法：{e}", file=sys.stderr)
        return None


# ----------------------------------------------------------------------------
# 一·五、输入感知与抽象化（zine 式自适应：任何图片都能成章）
# ----------------------------------------------------------------------------

def analyze_input(img: Image.Image):
    """判定输入类型。返回 (has_alpha, kind)：kind ∈ {'graphic','photo'}"""
    has_alpha = False
    rgba = img.convert("RGBA")
    a_min, a_max = rgba.getchannel("A").getextrema()
    if a_min < 220:
        has_alpha = True

    small = img.convert("RGB").resize((160, 160))
    arr = np.asarray(small, dtype=np.uint8)
    # 4bit 量化后的独立颜色数
    quant = (arr >> 4).reshape(-1, 3)
    uniq = len(np.unique(quant, axis=0))
    # 强边缘像素占比
    g = np.asarray(small.convert("L"), dtype=np.int16)
    gx = np.abs(np.diff(g, axis=1))
    gy = np.abs(np.diff(g, axis=0))
    strong = (gx[:, :] > 40).sum() + (gy[:, :] > 40).sum()
    edge_ratio = strong / (159 * 320)
    kind = "graphic" if (uniq <= 52 or edge_ratio > 0.20) else "photo"
    return has_alpha, kind


def flatten_texture(rgba: Image.Image, strength: float = 1.0) -> Image.Image:
    """照片抽象化前处理：压平材质纹理、保边简化（中值+受限高光）。"""
    if strength <= 0:
        return rgba
    rgb = rgba.convert("RGB")
    a = rgba.getchannel("A")
    sm = rgb.filter(ImageFilter.MedianFilter(size=5))
    sm = sm.filter(ImageFilter.GaussianBlur(0.9 * strength))
    # 细节回注：只把中等强度结构加回来一点，避免糊成一团
    detail = ImageChops.subtract(rgb, sm, scale=1, offset=128)
    detail = detail.point(lambda v: 128 + int((v - 128) * 0.45))
    out = ImageChops.add(ImageChops.subtract(sm, Image.new("RGB", sm.size, (128, 128, 128))),
                         Image.new("RGB", sm.size, (128, 128, 128)))
    out = Image.blend(sm, ImageChops.overlay(sm, detail.filter(
        ImageFilter.GaussianBlur(0.4))), 0.35)
    res = out.convert("RGBA")
    res.putalpha(a)
    return res


def _edge_alpha_of(img_gray_arr, sigma=1.0):
    g1 = _gauss_arr(img_gray_arr, sigma)
    g2 = _gauss_arr(img_gray_arr, sigma * 1.9)
    e = np.abs(g1 - g2)
    m = e.max()
    return e / max(m, 1e-6)


# ----------------------------------------------------------------------------
# 二、蚀刻纹章化：银白细线描 + 分面明度（去饱和、无发光）
# ----------------------------------------------------------------------------

def _gray_arr(rgba):
    bg = Image.new("RGBA", rgba.size, (128, 128, 128, 255))
    flat = Image.alpha_composite(bg, rgba).convert("L")
    return np.asarray(flat, dtype=np.float32) / 255.0


def _gauss_arr(g01, sigma):
    im = Image.fromarray((np.clip(g01, 0, 1) * 255).astype(np.uint8), "L")
    return np.asarray(im.filter(ImageFilter.GaussianBlur(sigma)), dtype=np.float32) / 255.0


def _hatch(h, w, period=9.0, angle_deg=32.0):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    th = math.radians(angle_deg)
    s = xx * math.sin(th) + yy * math.cos(th)
    frac = np.abs(((s / period) % 1.0) - 0.5) * 2.0
    return np.clip(1.0 - frac * 1.5, 0.0, 1.0)


def _stretch_lut(hist, cutoff_pct=1):
    """自动色阶的单通道 LUT（逐字镜像 Pillow ImageOps.autocontrast(cutoff=1) 的规则）：
    两端各截掉 cutoff_pct 后线性拉伸。收成 LUT 是为了能只对块内像素统计、
    却把映射套回整帧 —— PIL 只能整帧做，块内参考就没法用它的 API。"""
    h = list(hist)
    n = sum(h)
    cut = int(n * cutoff_pct // 100)
    for lo in range(256):
        if cut > h[lo]:
            cut -= h[lo]
            h[lo] = 0
        else:
            h[lo] -= cut
            cut = 0
        if cut <= 0:
            break
    cut = int(n * cutoff_pct // 100)
    for hi in range(255, -1, -1):
        if cut > h[hi]:
            cut -= h[hi]
            h[hi] = 0
        else:
            h[hi] -= cut
            cut = 0
        if cut <= 0:
            break
    for lo in range(256):
        if h[lo]:
            break
    for hi in range(255, -1, -1):
        if h[hi]:
            break
    if hi <= lo:
        return list(range(256))
    scale = 255.0 / (hi - lo)
    offset = -lo * scale
    return [max(0, min(255, int(ix * scale + offset))) for ix in range(256)]


# 方向性浮雕：光从右上打（与 compose_endfield 的「右上高光→左下渐暗」同向）。
# 单调的「电平→颜色」坡道只给明暗、不给凸起，金属蚀刻的可读性主要来自棱边
# 一侧亮一侧暗 —— 官方章面纹章能一眼认出形状，靠的就是这道棱。
EMBOSS_HI = 0.60           # 迎光面向 bright 靠拢的比例
EMBOSS_LO = 0.72           # 背光面向暗端靠拢的比例
EMBOSS_LX, EMBOSS_LY = 0.62, -0.60   # 光向（图像坐标，y 轴向下）
EMBOSS_NORM_PCT = 92       # 斜率场按自身分位归一（固定增益会被平滑坡道的海量小梯度吃掉）
EMBOSS_STRENGTH = {"line": 0.55}     # 线稿支细边多，棱要弱；其余档走 1.0

# 电平分带数：官方章面读作「几层平涂的蚀刻台 + 硬边」，连续坡道读作「贴在金属上
# 的一张照片」。分带后斜率只在台界上非零 ⇒ 浮雕棱正好落在硬边上。
RELIEF_BANDS = 4

# 纹章占面：etch_face 出图像长边 = FACE_PX，compose_endfield 只缩不放到 EMBLEM_CAP。
# 两者同值时纹章才真正吃满这个尺寸（旧值 520/580 让 580 那一档永远用不上）。
# 660 是目检取的：520 时纹章只占章面宽 64%（官方约 85%），800 会压到内环与铭牌。
FACE_PX = 690
EMBLEM_CAP = 690


# ===== 实验面（章面排线纹理，2026-10-12 纹理原型轮）=====
# 分带坡道在**平滑区**斜率为零 ⇒ `_emboss` 在那里没有棱可长，天空/水面读作平涂色块。
# 官方章面在平滑区靠**排线的疏密**给出明暗（蚀刻的金属语言本来就是"线"不是"面"）。
# 这里把明暗翻译成线宽：越暗线越宽，越亮线越细，硬边附近让路给蚀刻轮廓。
# `MEDAL_ENGRAVE=0` 关掉（逐字节回到改前面），数值可覆盖增益以便 A/B 目检。
def _envf(name, default):
    v = os.environ.get(name)
    return default if v is None or v == "" else float(v)


ENGRAVE_PERIOD = _envf("MEDAL_ENG_PERIOD", 5.0)     # 线间距（章面像素）
ENGRAVE_ANGLE = _envf("MEDAL_ENG_ANGLE", 32.0)      # 与 line 支 `_hatch` 同向
ENGRAVE_GAIN = _envf("MEDAL_ENG_GAIN", 0.16)        # 零均值调制的幅度（TX-2 判出的可上岗档）
ENGRAVE_SOFT = _envf("MEDAL_ENG_SOFT", 0.30)        # 线剖面软边（相位单位）
ENGRAVE_DARK_K = _envf("MEDAL_ENG_DARKK", 1.6)      # 明暗→线宽的增益（>1 让亮部也留几根线）
ENGRAVE_FLOOR = _envf("MEDAL_ENG_FLOOR", 0.22)    # 最亮处的线深（避免高光变成死白平涂）
ENGRAVE_EDGE_SUPPRESS = _envf("MEDAL_ENG_SUP", 0.75)  # 强边附近排线让路

# ===== LN-2 脊线墨迹（第五个改图杠杆，2026-10-14 上岗档 τ=0.90 只发满铺支）=====
# 用户路线口径（2026-10-13）：终末地蚀刻章的章面主体大多以**线条抽象构成**读出来，我方读作
# "贴在金属上的一张连续具体图像"。LN-1 的尺度归一靶表（`output/_linenote/ln1_norm202.log`，
# 窗 = 202 px 尺度）把这句话量成两条可核对的数：
#   · 平涂占比（5×5 极差 <6）：官方银档 **50.9%**，我方满铺支 21.3%（12 张池均）；
#   · 细频段（σ1.1→2.1 @ 阈 0.40）线长占比：官方 2.07%，我方 2.2~4.0% ⇒ **线不缺，
#     缺的是"线之间是平的"**。
# 病根：`ENGRAVE_FLOOR=0.22` 保证电平再高也留线，于是高频只以**等距织物**的形式铺满每一寸，
# 从不沿主体的真实轮廓落刀 ⇒ 抽象构成 = 零。这一组旋钮把墨的来源从"平行三角波"换成
# "`edges`（引擎自己的 DoG 带）细化后的线中心脊"，明暗→线宽仍走同一条算式。
# 取档实测：平涂 <6 的池均 off 21.3 → τ=0.60 41.6
# → **τ=0.90 44.6** → τ=1.00 45.1 → τ=1.20 45.8（曲线已饱和；s120 在 `pet_pug` 上整条死档）
# ⇒ 取 0.90 留悬崖余量。`align`（LN-3 方向尺）只在 off→开档那一步跳变、此后随 τ 平 ⇒
# 收益来自"换了笔迹来源"，不是"删了线"（官方 align 仅 +0.239 ⇒ 只作归因，不作达标线）。
# 作用面靠**调用点**隔离（㊾）：`LA_FB` 只在满铺支那一段算脊、`LA_SILO` 只在剪影支算。
# 剪影支默认**不发**（`LA_SILO=0`）：同一支杠杆在剪影面只有 +1.1 pp（22.4→23.5），
# 未单独复判不双开。`LA_WIDTH` 保持 1.5：`_box_mean` 走 `k = max(int(round(r)), 1)`，
# 1.5 与 2.2 取整成同一个核 ⇒ 宽度旋钮在这一段是惰性的，启用档不跟着动（回归抓到过）。
LA_TAU = _envf("MEDAL_LA_TAU", 0.90)       # 脊门限 = `edges` 自身 p99 的这一倍；<=0 = 不接线
LA_WIDTH = _envf("MEDAL_LA_WIDTH", 1.5)    # 笔画半径（章面像素，两次箱式均值 ≈ 高斯）
LA_MIX = _envf("MEDAL_LA_MIX", 1.0)        # 0 = 纯平行排线（改前算式），1 = 纯脊线
LA_SILO = _envf("MEDAL_LA_SILO", 0.0)      # 剪影支开关（实测判负，默认不接线）
LA_FB = _envf("MEDAL_LA_FB", 1.0)          # 满铺支开关（上岗档）
LA_STAT = {}                               # 接线证据：{("silo"|"fb", tone): 脊像元占比}

# ===== 章面电平（2026-10-12 坡道顶端/电平闭环轮）=====
# 四臂探针（`output/_visible/plate_probe.py`，目检 + 同口径量测）否掉了两条**全局常数**：
#   · 顶端收到 mid：金档纸白没了（好），但银档 object_arch 暗部 74.4% → 86.7%（更黑）。
#     银档 mid=(150,154,158) 是石墨本色、bright 才是金属高光，收顶等于把整枚章压成暗牌。
#   · 曝光锚（中位搬到 0.5）：暗照片救活了（74.4% → 14.5%），亮照片却过曝
#     （landscape/ef_gold 暗部 15.5% → 1.0%，官方金档全池中位 25.5%）。
# ⇒ 一个常数管不了两头：暗的要抬、亮的要压，方向相反。这里改成**逐张解**（分位锚），
#   并把顶端收档只发给目检确实出现纸白的金档。两个开关都留 A/B 口，0 = 逐字节回到改前。
#   第二版把锚从「均值」换成「暗部占比分位」：均值闭环在五臂板上现证会把暗照片抬成一片白。
PLATE_TOP_K = _envf("MEDAL_PLATE_TOP", 0.0)     # 金档坡道顶端落点（0=收到 mid，1=改前顶到近白）
PLATE_TOP_TONES = ("ef_gold",)
# 整图入章支的电平锚：**官方 95 张 crop 池**同档暗部占比中位（官方 crop 池现读，
# alpha>128、luma<110 同口径）。锚分位而不是锚均值 —— 均值闭环已在五臂板上现证会塌：
# object_arch/ef_gold 为凑 mean=157.9 把整场抬起，暗部 23.25% → 0.23%，建筑轮廓糊成一片白。
PLATE_DARK = {"ef_gold": 0.2551, "ef_silver": 0.2012}
PLATE_DARK_LUMA = 110.0        # 与上面同一把尺的暗部阈值（灰阶）
PLATE_LCL_K = _envf("MEDAL_PLATE_LCL", 1.0)     # 锚的强度（0=改前、不锁；1=分位精确落位）

# 剪影支的明暗极性（第三支杠杆）—— **判负，默认关**（目检 + 读数实测）。
# 立项理由当时成立：上面两支都挂在整图入章支或只收顶端，剪影支（抠图成功 = 生产主路径）
# 没被碰到，黑毛狗在银档把整枚章压成暗牌。但「把主体搬进一个窄窗口」这个**机制**是错的：
# 金档坡道 luma 100.9→227.3，暗部（<110）只能落在 t<0.072，而窗口中心 0.81/跨度 0.38 的
# 下沿是 0.62 ⇒ 暗部按构造必然为 0（现读 face dark 2.84%→0.01%、face mean 178→204，官方
# 同档 face 19–26% / 164–176）。银档反向往错：狗 face dark 55.5%→62.3%（官方 20–27%）。
# 四格里只有 silver/portrait_girl 一格进带（11.42%→20.27%）。⇒ 官方金档面是**宽双峰**
# （众数 t≈0.5 + 一条 20% 的深尾），不是窄窗口；窗口只换电平、必然吃掉动态范围
# （face spread 135→101）。后续要做的是配**分布**（尾部落位），不是搬中心。
SILO_POLAR = {"ef_gold": (0.45, 0.81), "ef_silver": (0.88, 0.22)}
SILO_POLAR_K = _envf("MEDAL_SILO_POLAR", 0.0)
SILO_POLAR_SPAN = _envf("MEDAL_SILO_SPAN", 0.38)   # 主体在坡道上占用的行程

# 纹章**落影**的颜色口径（HS 轮第一支杠杆，目检胜出）。旧写法把影画成 `tp["engrave"]`，
# 而六档里五档的 engrave 是近白（ef_gold (250,247,235)、ef_silver (238,238,236)）⇒ 代码与
# 它自己那行注释「右下永远有一条硬边**暗影**」相反。3× 局部板（`hs_shade_zoom.png`）现证：
# 关掉时黑狗四周浮一圈白、像剪下来贴上去的贴纸；打开后同一圈落成暖古铜/石墨的接触影。
# 峰值不透明度 0.80→0.42：近白 ×0.80 在亮底上是"提亮"，暗色 ×0.80 会把整圈糊成黑边。
SILO_SHADE_K = _envf("MEDAL_SILO_SHADE", 1.0)
SILO_SHADE_A = _envf("MEDAL_SILO_SHADE_A", 0.42)
SILO_SHADE_MUL = _envf("MEDAL_SILO_SHADE_MUL", 0.45)

# 分带**之前**的场地平滑（HS 轮第二支杠杆，取 1.6）。`_posterize` 是逐像元量化：照片自带的
# 高频噪声让它把同一片天空/毛皮渲成 4 个电位的椒盐（原生分辨率目检：狗脸一片奶油/棕渣、
# 山脊线碎成沙）⇒ 官方章面读作"几块平涂的蚀刻台 + 硬边"，我们读作"打了抖的一张复印件"。
# 先平滑再量化 = 每块地形落进同一电位，分带边界才成为连续轮廓。笔画/边缘链走另一条 DoG
# （`edges`）不受影响 ⇒ 抹掉的只是噪声。
# 档位是**在原生分辨率看局部裁片**定的（`hs_sigma.png`，四格 × σ0/1.6/2.5/3.5）：σ=1.6 时
# 四格的椒盐已经全部收平（山脊的小暗岛只剩三块、长椅横档成实心条、穹顶锯齿变直边），
# 再往上就开始吃内容 —— σ=2.5 把黑狗的暗毛啃成中灰斑块、狗眼失去硬边，σ=3.5 把穹顶的
# 尖饰并成一坨。**先前落 2.5 是在 470px 缩略板上看的，那一档看不见"糊"只看得见"平"。**
FACE_SMOOTH = _envf("MEDAL_FACE_SMOOTH", 1.6)


def _face_field_smooth(a):
    """分带前的场地平滑。K=0 时**不调** `_gauss_arr` —— 它会把 0~1 浮点重新量化成 uint8，
    关掉时必须逐字节回到改前，否则 A/B 板的差值里混着取整噪声。"""
    return _gauss_arr(a, FACE_SMOOTH) if FACE_SMOOTH > 0 else a

# 轮廓墨色（HS 轮第三支杠杆）：**实测不成立，默认关死（0.0）**。设计意图是把 DoG 边缘从
# "加亮"翻成"压暗"（真实蚀刻的落刀是凹槽，亮只出现在受光一侧、那一侧已由 `_emboss` 负责）。
# 原生分辨率四格归因板（`hs_attr.png` + 压在轮廓上的 `hs_rim.png`）读数：
# ① ink 单独开 = 与改前逐像素几乎同图（椒盐一颗没少、轮廓处也没有出现暗线）；
# ② ink 与平滑同时开 = 在山坡那格的大片平涂场里画出一张浅色虫纹网（`both` 有、`sm` 无）——
#    平滑把场地抹平后，`edges` 里剩下的高频全被 ink 逐条描了出来，再经浮雕提亮成网。
# 即：**这一项的收益在放大后不存在，代价在放大后确实存在** ⇒ 归零。
# 保留常量的唯一理由：后续若要让落刀成暗线，正确做法是给 ink 喂**同一 σ 平滑过**的边缘图
# （而不是原始 `edges`），这条杠杆就是它的入口；届时先过原生分辨率目检再抬非零值。
FACE_INK = _envf("MEDAL_FACE_INK", 0.0)

# ===== N-11 徽记化（上岗）：主体内的明暗由**线宽**承载，不由灰阶承载 =====
# 六轮连负的共性判语 = 官方章面是设计过的图形词汇（平涂块 + 排线填充），我们的是打了抖的照片
# （照片连通域 + 四级灰阶）。量化之后做任何整理都造不出词汇（N-3/N-9/N-10），把照片区域并成常量块
# 只得到低分辨率照片（N-7）⇒ 这一支不动电平、不动形状，改的是**承载明暗的物理量**：
# 真实蚀刻用线的疏密刻画深浅，同一块金属上没有"灰"。
# 回退口径：GAIN=0 时新增代码一行都不执行 ⇒ 逐字节回到改前（㊵）。
EMBLEM_HOLD = _envf("MEDAL_EMBLEM_HOLD", 0.20)   # 主体内保留的照片电平结构比例（0=全平涂）
EMBLEM_GAIN = _envf("MEDAL_EMBLEM_GAIN", 0.34)   # >0 = 排线改由**压平前**的照片场驱动，值为调制幅度
# 平底板落点**必须分档**：官方两极本来就是反的 —— 银档 = 深石墨主体压在近白底上（低落点），
# 金档 = 浅色主体压在暖金底上（高落点）。单一绝对电平必然输掉一档（N-11c 金档整枚压成暗铜）。
# 0.15 / 0.60 由 N-11d（金档 0.15/0.28/0.40/0.52 对照官方条）+ N-11g（0.52/0.60/0.68 上扫）
# 在原生分辨率板上判出，N-11e/h 两轮全池复判（72 张 ×2）确认。env 设 ≥0 = 全档同一落点的 A/B 口。
EMBLEM_BASE = _envf("MEDAL_EMBLEM_BASE", -1.0)
EMBLEM_BASE_T = {"ef_silver": 0.15, "ef_gold": 0.60}
EMBLEM_BASE_FLAT = 0.55      # 表外档：≈ 该档底板电平 ⇒ 压平几乎不动对比（保守兜底）

# 主体内线间距单独取档：`MEDAL_ENG_PERIOD`（5.0）是 `_engrave_ink` 每次调用都读的**全局量**，
# 粗档借给它会把满铺支（照片本就平铺到章缘）一起加粗 —— 粗条纹在那里读作划痕而不是蚀刻，
# 作用面硬闸也会因此失去牙。⇒ 只在剪影支的调用点传这一条（0 = 跟随全局，即改前行为）。
EMBLEM_PERIOD = _envf("MEDAL_EMBLEM_PERIOD", 10.0)

# 作用档：上岗只发**银档**。金档两条路在眼睛下互斥（§六十八 的复扫账）—— BASE 抬高 = 保住
# 官方极性（浅图元压在暖金上）但主体身份被抹平；BASE 压低 = 身份回来但整枚读作暗铜牌。
# 压平机制本身给不出"又浅又有身份"的那一档，缺的是设计几何（= 路线岔口，另案）。
# env 传逗号表 = 把金档接回来做 A/B；传空串 = 全档不接线。
EMBLEM_TONES = set(t.strip() for t in os.environ.get("MEDAL_EMBLEM_TONES",
                                                     "ef_silver").split(",") if t.strip())


def _emblem_base(tone):
    return EMBLEM_BASE if EMBLEM_BASE >= 0.0 else EMBLEM_BASE_T.get(tone, EMBLEM_BASE_FLAT)


# ===== 停线门限（N-12，上岗档 p=4）=====
# N-11 上岗后**唯一没消失的事**：整块主体从头到尾都上线，没有一块真正的静（官方有大片安静平涂）。
# 机制账：`_engrave_ink` 的线宽只吃 `t2d` 的**电平**（`depth = FLOOR + (1−t2d)·DARK_K`），
# 而剪影支喂给它的是**已分带**的场 ⇒ 同一条带内线宽恒定 ⇒ 照片里本来没内容的地方（天空、墙、
# 无光布面）照样被刻满平行线。`ENGRAVE_FLOOR=0.22` 又保证电平再高也留线 ⇒ 从算式上就**没有**
# "静"这个解。这一支不动线宽、不动电平，动的是**哪里有资格被刻**：给调制乘一张幅度图 amp∈[0,1]，
# amp 由**连续**照片场（分带前）的局部斜率在邻域内的均值给出 ⇒ 平的地方 amp→0。
# 零均值改成按 amp 加权（`c = amp·(ink − 加权均值)`）：amp=0 处 `exp(0)=1` ⇒ **逐字节不动**，
# 而不是被全局补偿抬亮（那会是一片"静"其实是一次电平搬移）。amp≡1 时回到 N-11 的算式。
# 作用面：amp 只在主体内生效（主体外置 1.0）⇒ 背景那一段与改前同。LINESTOP=0 一行都不执行（㊵）。
# 取档账（`output/_n12_linestop/final_scan.log`，12 张全池）：方向闸 0/12 违反、塌陷闸 0/12 违反、
# 满铺支与金档绝缘闸 6/6 逐字节同。p=4 是四臂里唯一在眼睛下赢的一档（N-12e 5 张 3× 板 → N-12f 全池）。
# **诚实账**：全池 12 张里 3 张（`landscape_mtn`/`landscape_river`/`object_arch`）停线**空转**
# （满铺型照片主体没有可判为静的平区，`g2` 与 `cand` 逐字节相同）⇒ 那三张的收益只来自颗粒减半。
LINESTOP = _envf("MEDAL_LINESTOP", 4.0)              # 0 = 不接线；>0 = 幂次 p（越大静得越狠）
LINESTOP_WIN = _envf("MEDAL_LINESTOP_WIN", 22.0)    # 活动性邻域窗（章面像素，≈ 2 条线间距）
LINESTOP_Q = _envf("MEDAL_LINESTOP_Q", 0.55)        # 满幅门限 = 主体内活动性的这一分位（自归一）
LINESTOP_FLOOR = _envf("MEDAL_LINESTOP_FLOOR", 0.0)  # amp 下限：>0 = 静区仍留几根线（A/B 口）
# ===== 满铺支（抠图回退）自己的停线资格（FB-8，上岗档 p=4）=====
# N-12 上岗时留了一条**诚实账**：全池 12 张里三张满铺型照片（`landscape_mtn`/`landscape_river`/
# `object_arch`）停线**空转** —— 因为 amp 只发给剪影支的主体，而这一支整幅都是主体、且 `lamp`
# 被显式清成 None（绝缘）。fb7 的 2× 放大板现证其后果：这三张上**除了最暗那一带，全章没有一块
# 不带 5 px 平行线的金属**，而官方银档是"大片平涂金属 + 少数几块排线填充的图元"。
# 机制账与剪影支逐字相同：这一支走 `else` 那一次 `_engrave_shade(rgb, field, edges)`，线宽只吃
# **已分带**的电平 ⇒ 同一条带内线宽恒定 ⇒ 照片里本来没内容的地方（天空、水面、雪坡）照样刻满线。
# ⇒ 把 amp 也发给这一支，门限吃**分带前**的连续照片场 `l`（主体掩膜传 None：满铺型没有"主体外"）。
# 作用面：只在 `a_min>200 and span_ok`（满铺开火）那一段里算 amp ⇒ 九张 ai 路线与 line/icon/facet
# 档逐字节不变（fb9 全池扫现证：九张 ai 与生产树逐字节相同 + 满铺调用点拿不到 amp）。
# 旋钮单立（㊾）：不许借 `MEDAL_LINESTOP` —— 那是剪影支的取档，两条路线的取档必须互不绑架。
# 取档实测：s4 = 三张平均"变静"33.1%、
# `e_p05` 3.56/2.85/4.61 → 1.39/1.38/2.06（≈ 只剩自家颗粒地板）；s6 只多 +0.7~1.0 pp、
# 眼睛上不可辨 ⇒ 取与剪影支同档的 4.0；`s4q4`（q 0.40）判负（arch 上反而变忙 10.3%）。
FB_STOP = _envf("MEDAL_FB_STOP", 4.0)                 # 0 = 不接线；>0 = 幂次 p（越大静得越狠）
FB_STOP_WIN = _envf("MEDAL_FB_STOP_WIN", 0.0)         # 0 = 跟随 `LINESTOP_WIN`
FB_STOP_Q = _envf("MEDAL_FB_STOP_Q", 0.55)            # 满幅门限分位（自归一，跨照片免调）
FB_STOP_FLOOR = _envf("MEDAL_FB_STOP_FLOOR", 0.0)     # amp 下限：>0 = 静区仍留几根线
# ===== 收尾细颗粒幅度（N-12b/12g，上岗档 ±2）=====
# 归因来自 `output/_n12_linestop/n12_noise_floor.py`：±4 均匀整数颗粒过带通尺后 e_p05 = 2.35
# （iid 均匀 ±4 的解析 σ = 2.582，已知答案档见 `n12e_amp2.py`），而**官方取证条同尺 e_p05 只有
# 0.49–0.60** ⇒ 官方静区是"干净金属 + 无线"，我方静区哪怕把排线整开关关掉也压在 2.5 的自家地板上。
# 为什么是 2 而不是 0：g0（完全去颗粒）在眼睛下长出**真条带**（N-12c 判负）；±2 把地板压到 1.41
# （已知答案 ±2 = 1.288，贴着它）而游程尺几乎不动（3→4）⇒ 既让静区真的静下来、又不长台阶。
# 越界面已补：`GRAIN_K` 是**全局量**（endfield 收尾那一次加法，`compose_endfield` 唯一读数点），
# 满铺支 `mode="line"` 银/金两档 12 格 × 两闸 0 违反、三块板目检"更干净或持平、无条带"
# （`output/_n12_linestop/line_grain.log`）。⇒ 全局改 2 成立，网页 `applyGrain(canvas,7,·)` 同步镜像。
GRAIN_K = _envf("MEDAL_GRAIN", 2.0)                  # ±k 均匀整数颗粒；0 = 完全去颗粒（判负，别抬）
# ===== 轮廓棱的停线门限（N-13b/13c，上岗档 1.0）=====
# 暗部里那些**亮等高线**不是排线调制画的，而是 `edge_t` 加进底板电平的轮廓棱（`inner = 板 + 棱`）
# ⇒ `LINESTOP` 那类"停线"杠杆按构造管不到它（N-13 首跑实测 `blob%` 只动 +0.03~+0.10 pp）。
# 本支把同一张 amp（`lamp`）也发给棱。取档以全池实测为准
# （g05/g1/g2 全池 12 张 × 三列量测 + 识图终判 ⇒ g1）。作用面只在银档剪影支（`EMBLEM_TONES`）。
EDGE_GATE = _envf("MEDAL_EDGE_GATE", 1.0)             # 0 = 不接线（棱全额加回，逐字节同改前）


def _box_mean(a, r):
    """可分离箱式均值，**纯 float64**。这里不能用 `_gauss_arr`：它把输入 `astype(uint8)` 重新
    量化成 255 级，而逐像素斜率量级只有 1e-3，量化噪声（3.9e-3）比信号还大 ⇒ 门限会量到仪器。"""
    k = max(int(round(r)), 1)
    w = 2 * k + 1
    b = np.pad(np.asarray(a, dtype=np.float64), ((0, 0), (k, k)), mode="edge")
    c = np.zeros((b.shape[0], b.shape[1] + 1), dtype=np.float64)
    np.cumsum(b, axis=1, dtype=np.float64, out=c[:, 1:])
    a = (c[:, w:] - c[:, :c.shape[1] - w]) / w
    b = np.pad(a, ((k, k), (0, 0)), mode="edge")
    c = np.zeros((b.shape[0] + 1, b.shape[1]), dtype=np.float64)
    np.cumsum(b, axis=0, dtype=np.float64, out=c[1:, :])
    return (c[w:, :] - c[:c.shape[0] - w, :]) / w


def _linestop_amp(cont, sel, p=None, win=None, q=None, floor=None):
    """连续照片场（分带前）+ 主体掩膜 → 排线幅度图 amp∈[0,1]。0 = 这块金属该是静的。

    门限从**主体自身的活动性分位**取（同 `_posterize` 的 QBAND 口径）：逐像素斜率的绝对量级
    跨照片差好几倍（逆光剪影 vs 满铺纹理），钉死一个绝对阈值必然在一类照片上恒开、另一类恒关。
    `p/win/q/floor` 默认取 N-12 那组全局档 ⇒ 剪影支的调用点算式与改前逐字相同（fb8 闸② 数组恒等）；
    满铺支（FB-8）传自己那一组，两条路线的取档互不绑架（㊾）。
    """
    p = LINESTOP if p is None else p
    win = LINESTOP_WIN if win is None else win
    q = LINESTOP_Q if q is None else q
    floor = LINESTOP_FLOOR if floor is None else floor
    f = np.asarray(cont, dtype=np.float64)
    # 单边差 + 末位复制：中心差（edge 填充）会把首末列的斜率算成**半值** ⇒ 数组四边长出一圈
    # 假静区；复制最内侧那条差分就没有这个偏差（斜坡格 A7b 整幅恒 1 就是这么来的）。
    dy = np.pad(np.abs(np.diff(f, axis=0)), ((0, 1), (0, 0)), mode="edge")
    dx = np.pad(np.abs(np.diff(f, axis=1)), ((0, 0), (0, 1)), mode="edge")
    act = _box_mean(_box_mean(np.hypot(dy, dx), win / 2.0), win / 2.0)
    v = act[sel] if sel is not None and sel.any() else act.ravel()
    th = float(np.percentile(v, 100.0 * min(max(q, 0.0), 1.0)))
    if th <= 1e-9:
        return np.ones_like(act, dtype=np.float32)      # 场没有可分的活动性 ⇒ 不动（= N-11）
    amp = np.clip(act / th, 0.0, 1.0) ** p
    return np.clip(amp + floor, 0.0, 1.0).astype(np.float32)


# 双色轮（配分布）：官方章面读作"浅图形压深底"的**双色纹章**，我们读作"一张照片铺在金属上"。
# 前两轮的两次尝试都被自家数据否掉了：PT 极性支把主体**整段搬进窗口** ⇒ 金档章面 dark 掉到
# 0.01/0.18%、目检"瞳孔塌成浅灰坑"（判语"比改前更不像"）；TX 轮想用一个**全局标量** γ 命中
# 官方暗部占比 ⇒ 跨照片 τ 的 CV = 金 1.127 / 银 1.223，散布是照片自带的。⇒ 这两条排除了
# "搬中心"和"单标量"，剩下的自由度只有**分布形状**：本支把章面场的**三个自身分位**
# （p12/p50/p88，逐照片现读 = 自标定）单调分段线性地搬到官方同档中央块的同一秩靶点
# （档常数 = `output/_visible/dual_cal.py` 在 95 张 crop 池上现读的中位，非手设）：
#   官方中央块 gold  dark 15.05% / 谷深 0.236 / 双峰(51 张中位)   →  t = 0.025 / 0.579 / 1.078
#   官方中央块 silver dark 26.58% / 谷深 0.614 / 双峰(17 张中位)  →  t = 0.149 / 0.724 / 0.870
# 金档的顶钉换算出 1.078 > 1 ⇒ **按 t=1.0 饱和**，坡道顶端本身不动（那是 PT 轮收顶的账）。
# 映射是单调的 ⇒ 只摊开中段、聚拢两头，不做窗口位移也不夹掉行程（DY-2 就是盯着这一条）。
# 默认 **1.0 = 启用**（双色守卫落地）。启用与否不是"分布命中靶值"而是**成图目检**：
# 全池 24 格里门开 7 格，其中 animal_bigcat/pet_dog/portrait_girl 三格是肉眼可辨的收益，
# 另 4 格（pet_pug 两档、portrait_woman 金）读数动 1.4–4.0pp 但肉眼近乎无差 ⇒ 算"不亏"不算"赢"；
# 17 格门不开 ⇒ 逐字节 = 改前。`MEDAL_DUALITY=0` 是回退档（A/B 对比的 B 侧就用它）。
DUALITY_K = _envf("MEDAL_DUALITY", 1.0)
# 整图入章支单独一支开关：生产主路径（抠图成功的剪影支）先过目检，回退支不搭车 ——
# 早先只落在整图支的覆盖面就是要避免的反面。
DUALITY_FB = _envf("MEDAL_DUALITY_FB", 0.0)
DUALITY_R = (12.0, 50.0, 88.0)
DUALITY_TGT = {"ef_gold": (0.025, 0.579, 1.000),
               "ef_silver": (0.149, 0.724, 0.870)}
# 全池扫（12 张真照片 × 2 档；权威复扫 = `dual_guard3.log`，`dual_sweep.log` /
# `dual_guard.log` / `dual_guard2.log` 是三本旧账：未加门、以及只要求"严格变小"那一版）目检账：分位对齐在
# **过暗剪纸**上是收益（pet_dog 银 58.0%→22.0%，黑剪纸裂成亮暗两层、五官读得出），
# 在本来就在官方带内的照片上是**伤害**（portrait_man 银 30.6%→6.3%，深色外套抬成一片灰糊）。
# ⇒ 上岗形态 = 只治两种病，其余一律不动：
#   A 过暗剪纸：暗部占比 > 1.3 × 官方带上沿；
#   B 太平且偏亮：暗部 < 官方带下沿 且 p95−p5 跨度 < 0.85 × 官方同档中位跨度。
# **判病必须量在成图上，不能量在场上**：`dual_calib.log`（n=24）先把门写在照片裁片的场上，
# 结果与预测不同面 —— 整片预测暗部占比 vs 成图中央块渲染值只有 r=0.663 / 斜率 0.384，
# 取中央半幅更差（r=0.798 / 中位残差 −18pp，object_arch 银预测 88.2% 而渲染 18.6%）。
# 场→成图之间隔着 抠图落位、坡道、`_plate_level_lock`、浮雕、装饰层四道搬运，没有一个现读的
# 换算能用 ⇒ 门的读数一律来自**第一趟成图本身**（`_block_reads`，口径与预测逐字相同），
# 病格再花第二趟重跑同一条链。代价 = 只有病格多渲一趟，换来的是"不推离带"这条真的可测。
# 靶值 = 官方 95 枚裁片池中央块现读（`dual_cal.json`：金 n=51、银 n=17 的中位与 p25/p75 带）。
DUALITY_GUARD = {"ef_gold": (9.39, 18.68, 151.0),
                 "ef_silver": (20.58, 33.86, 172.0)}
# 标定档（只打印、不改行为）：判病行不行、判了哪几格，要能在日志里查到，不许只看成图猜。
DUALITY_DBG = _envf("MEDAL_DUALITY_DBG", 0.0)
# 对照臂（**只给 A/B 用，默认关**）：>0 时不判病、每一格都开支 = 闸门前的老行为，
# 用来现读"闸门到底救回了哪几格"。生产路径永远走两趟闸门。
DUALITY_FORCE = _envf("MEDAL_DUALITY_FORCE", 0.0)
# 第二趟的最低收益门限（百分点）：省不下这么多就不换图（见 `_dual_gate`）。
DUALITY_GAIN_MIN = _envf("MEDAL_DUALITY_GAIN", 1.0)
DUALITY_DARK_L = 110.0


def _block_reads(img):
    """成图**中央块**的渲染读数，口径与 PT/H 两轮那把尺逐字相同：
    `n = w//2`，方块 `[n//2 : n+n//2, n//2 : n+n//2]` ∩ `alpha > 128`，灰阶 `convert("L")`。"""
    w, _h = img.size
    n = w // 2
    sub = img.crop((n // 2, n // 2, n + n // 2, n + n // 2)).convert("RGBA")
    a = np.asarray(sub.getchannel("A"), dtype=np.uint8)
    l = np.asarray(sub.convert("L"), dtype=np.float64)
    v = l[a > 128]
    if v.size < 64:
        return None
    q = np.percentile(v, (5.0, 95.0))
    return float((v < DUALITY_DARK_L).mean()) * 100.0, float(q[1] - q[0])


def _dual_band_dist(dark, band):
    return 0.0 if band[0] <= dark <= band[1] else max(band[0] - dark, dark - band[1])


def _dual_disease(reads, tone):
    """第一趟成图读数的病征：A 过暗剪纸 / B 太平且偏亮。没病 ⇒ 这一格一个字都不改。"""
    band = DUALITY_GUARD.get(tone)
    if band is None or reads is None:
        return False
    dark, spread = reads
    return bool(dark > 1.3 * band[1] or (dark < band[0] and spread < 0.85 * band[2]))


def _dual_gate(out, render, tone, k):
    """两趟闸门的判语：第一趟（k=0 渲的默认臂）量成图中央块 ⇒ 没病原样交回；
    有病才花第二趟 `render(k)`，且只有**暗部离官方同档带明显更近**才留下第二趟。
    "明显"= 至少省下 `max(DUALITY_GAIN_MIN, 10% × 原距离)`：全池扫现读三格
    （landscape_canyon 金 8.51→8.41、银 19.59→18.46、object_desk 金 7.07→7.04）
    在"严格变小"规则下被收下，但那三格改完仍远在带外（dark 1–2%）⇒ 白花一趟、白改像素。
    ⇒ 保护账不靠肉眼逐格数：凡闸门没开的格成图逐字节 = 默认臂，开了又没足够收益的格亦然。
    返回 (成图, 一行决策日志)。"""
    band = DUALITY_GUARD[tone]
    r0 = _block_reads(out)
    if r0 is None:
        return out, "keep=off reads=None"
    if not _dual_disease(r0, tone):
        return out, "keep=off dark=%.2f spread=%.1f disease=no" % r0
    cand = render(k)
    r1 = _block_reads(cand)
    if r1 is None:
        return out, "keep=off dark=%.2f/%.1f disease=yes second=None" % r0
    d0, d1 = _dual_band_dist(r0[0], band), _dual_band_dist(r1[0], band)
    need = d0 - max(DUALITY_GAIN_MIN, 0.10 * d0)
    if d1 > need:
        return out, ("keep=off dark=%.2f/%.1f disease=yes second=%.2f/%.1f "
                     "gain %.2f<%.2f") % (r0 + r1 + (d0 - d1, d0 - need))
    return cand, ("keep=dual dark=%.2f/%.1f disease=yes second=%.2f/%.1f "
                  "gain %.2f>=%.2f") % (r0 + r1 + (d0 - d1, d0 - need))


def _dual_knots(tone, off=0.0, mul=1.0):
    """把坡道域 t 的靶钉换算到某一支自己的场域：整图支的 `field_t = 0.10 + 0.90*l` ⇒ off/mul 传入。"""
    t = DUALITY_TGT.get(tone)
    if t is None:
        return None
    return ((t[0] - off) / mul, (t[1] - off) / mul, (t[2] - off) / mul)


def _duality_map(field, knots, sel=None, k=None):
    """三钉单调分段线性重排。开关为 0 / 档不在白名单 / 样本不足 ⇒ **原样返回**（逐字节回退）。
    该不该动由 `generate()` 的两趟闸门判（本函数只管搬，不管判）。"""
    k = DUALITY_K if k is None else k
    if k <= 0.0 or knots is None:
        return field
    v = field if sel is None else field[sel]
    if v.size < 64:
        return field
    q = np.percentile(v.astype(np.float64), DUALITY_R)
    q = np.maximum.accumulate(np.clip(q, 0.0, 1.0))
    t = np.clip(np.asarray(knots, dtype=np.float64), 0.0, 1.0)
    x = np.array([0.0, q[0], max(q[1], q[0] + 1e-3), max(q[2], q[1] + 1e-3), 1.0])
    y = np.array([0.0, t[0], max(t[1], t[0] + 1e-3), max(t[2], t[1] + 1e-3), 1.0])
    out = np.interp(field, x, y).astype(np.float32)
    return out if k >= 1.0 else (field + (out - field) * k).astype(np.float32)


def _plate_top(tone, mid, bright):
    """照片亮度驱动的两支坡道（剪影 / 整图）的顶端落点。金档收到 mid（暖金高光）——
    `bright=(252,250,240)` 的近白在官方只出现在**蚀刻笔画**上，章面本体最亮处仍是暖金，
    一路推上去章面上半就读作一张白纸。银档与其余档不动（那里的 bright 是金属高光）。"""
    if tone not in PLATE_TOP_TONES:
        return bright
    return bright if PLATE_TOP_K >= 1.0 else mid + (bright - mid) * PLATE_TOP_K


def _plate_level_lock(l, tone, lo_c, hi_c, bands=RELIEF_BANDS):
    """整图入章支的电平锚：把照片明度场整体平移，使章面**暗部占比**落到官方同档中位。

    在**分带后的坡道空间**里解，不在连续亮度里解 —— 「暗」是"落在第 0 带"这件事，带界是
    台阶；按连续分位解会系统性抬过头（银档实测暗部 13% 而非目标 20%）。`frac(o)` 对 o 单调
    不增 ⇒ 二分。均值不闭环：凑均值会把暗照片整场抬成一片白（五臂板现证）。
    金档此处无从下手并**如实不动**：它的坡道最低带已在阈值之上（lo_l≈101 ⇒ 带 0 的 luma≈113），
    章面里 <110 的像素全来自章体压边与五金件，不在照片坡道手里（覆盖面账见计划 PT-6L）。

    `bands` 必须与**下游最终分带用同一把带数**：锚量的是"落在第 0 带"这件事，带边一动锚就跟着漂，
    只给下游换带数而锚不知道 ⇒ L1 的效果会被锚补偿掉（fb4 当年就踩在"锚在杠杆之前"这条上）。
    """
    want = PLATE_DARK.get(tone)
    if want is None or PLATE_LCL_K <= 0.0:
        return l
    lo_l = float(0.299 * lo_c[0] + 0.587 * lo_c[1] + 0.114 * lo_c[2])
    hi_l = float(0.299 * hi_c[0] + 0.587 * hi_c[1] + 0.114 * hi_c[2])
    if hi_l <= lo_l:
        return l
    t_dark = (PLATE_DARK_LUMA - lo_l) / (hi_l - lo_l)
    if t_dark <= 0.10:
        return l

    def frac(o):
        return float(np.mean(0.10 + 0.90 * _posterize(np.clip(l + o, 0.0, 1.0), bands) < t_dark))

    a, b = -1.0, 1.0
    if frac(a) < want or frac(b) > want:
        return l              # 落不进可达区间 ⇒ 不锚
    for _ in range(24):
        m = 0.5 * (a + b)
        if frac(m) > want:
            a = m
        else:
            b = m
    return np.clip(l + PLATE_LCL_K * 0.5 * (a + b), 0.0, 1.0)


# 落地面只开这两档（纹理白名单）：官方只有银/金两档的章面纹理量测过并目检过，
# 其余档（arknights 三档、ef_irid、ef_dark/bronze、industrial、candy、pearl）没有对应证据，
# 也不许被这一改法顺带动到 —— 全矩阵 A/B 里它们必须逐字节不变。
ENGRAVE_TONES = ("ef_gold", "ef_silver")


def engrave_enabled(tone=None):
    """`MEDAL_ENGRAVE=0` 整开关（逐字节回到改前）；给了 tone 则再过档位白名单。"""
    v = os.environ.get("MEDAL_ENGRAVE")
    if v is not None and v == "0":
        return False
    return tone is None or tone in ENGRAVE_TONES


def _ridge_core(edges, tau, radius):
    """`edges`（DoG 带通）→ 线中心脊 → 摊成有宽的笔画芯（0~1）。返回 (core, 脊像元占比)。

    细化 = 四邻域极大（含同值）：一条线只留中心那一列，之后笔画宽只由 `radius` 决定，
    不与带通响应自身的过渡带混在一起（LN-1 已知答案档量过：1px 栅格细化后笔宽 0.99、
    未细化 5.73 ⇒ 两档分得开）。摊开走 `_box_mean`（纯 float64）而不是 `_gauss_arr`：
    后者把输入量化成 uint8，而细脊芯的峰值只有百分之几，量化会吃掉笔画本身。
    """
    e = np.asarray(edges, dtype=np.float32)
    ref = max(float(np.percentile(e, 99.0)), 1e-6)
    m = e >= tau * ref
    k = m & (e >= np.roll(e, 1, 0)) & (e >= np.roll(e, -1, 0)) \
        & (e >= np.roll(e, 1, 1)) & (e >= np.roll(e, -1, 1))
    core = k.astype(np.float64)
    r = max(int(round(radius)), 1)
    for _ in range(2):
        core = _box_mean(core, r)
    peak = float(core.max())
    return np.clip(core / max(peak, 1e-6), 0.0, 1.0).astype(np.float32), float(k.mean())


def _engrave_ink(t2d, edges, period=None, angle_deg=None,
                 soft=None, dark_k=None, floor=None, ridge=None, mix=0.0):
    """返回 0~1 的"这里该被刻一道线"掩膜（线中心 1、线间 0）。"""
    period = ENGRAVE_PERIOD if period is None else period
    angle_deg = ENGRAVE_ANGLE if angle_deg is None else angle_deg
    soft = ENGRAVE_SOFT if soft is None else soft
    dark_k = ENGRAVE_DARK_K if dark_k is None else dark_k
    floor = ENGRAVE_FLOOR if floor is None else floor
    h, w = t2d.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    th = math.radians(angle_deg)
    phase = ((xx * math.sin(th) + yy * math.cos(th)) / period) % 1.0
    tri = 1.0 - np.abs(phase - 0.5) * 2.0                       # 线中心三角波
    depth = np.clip(floor + (1.0 - t2d) * dark_k, 0.0, 1.0)     # 越暗线越宽
    ink = np.clip((tri - (1.0 - depth)) / max(soft, 1e-3), 0.0, 1.0)
    a2 = _envf("MEDAL_ENG_ANGLE2", 0.0)
    if a2:
        # 交叉排线只在暗区长出来：蚀刻用「线的密度」表暗，官方章面的暗部是两向线、
        # 亮部是单向线。两向恒开会把亮区也压成网格（读作织物，不是金属）。
        th2 = math.radians(a2)
        ph2 = ((xx * math.sin(th2) + yy * math.cos(th2)) / period) % 1.0
        tri2 = 1.0 - np.abs(ph2 - 0.5) * 2.0
        depth2 = np.clip(floor + (1.0 - t2d) * dark_k, 0.0, 1.0)
        ink2 = np.clip((tri2 - (1.0 - depth2)) / max(soft, 1e-3), 0.0, 1.0)
        cross = np.clip((0.62 - t2d) / 0.34, 0.0, 1.0)          # 阈值以下才交叉
        ink = np.maximum(ink, ink2 * cross)
    ink = ink * np.clip(1.0 - edges * ENGRAVE_EDGE_SUPPRESS, 0.0, 1.0)
    if ridge is not None and mix > 0.0:
        # LN-2：脊线**不做**上面那条"强边让路"抑制 —— 它本身就长在强边上（让路会把它自己抹掉）。
        # 明暗→线宽的算式与平行排线同一条（`depth` 门控 `core`），只是笔迹来源换了。
        rink = np.clip((ridge - (1.0 - depth)) / max(soft, 1e-3), 0.0, 1.0)
        ink = ink * (1.0 - mix) + rink * mix
    return ink


def _engrave_shade(rgb, t2d, edges, gain=None, period=None, amp=None, ridge=None, mix=0.0):
    """把排线压进已上色 + 已浮雕的章面：**围绕本色做零均值乘性调制**（线槽压暗、线脊提亮）。

    旧写法是单边朝 lo_c 拉：`rgb + (lo_c-rgb)*ink*gain`。纹理确实长出来了，电平也跟着塌 ——
    隔离树实测（整枚章口径）章面暗部占比一格能从 13.3% 涨到 40.6%（+27.3pp）、
    均值掉 11.7 灰阶，把「电平是档位常数」这条直接打掉，且银档两格判 REGRESS。
    蚀刻的线是同一块金属上的明暗起伏，不是往底色上盖墨 ⇒ 减掉图案均值再走指数调制：
    暗下去多少就把线间提回来多少，几何均值不动，加的是**方差不是电平**。

    `amp`（N-12 停线门限）= 逐像素的调制资格：均值改按 amp 加权，`c = amp·(ink − 加权均值)`
    ⇒ amp=0 处调制恰好为零（**真静**，不是被补偿抬亮）。`amp=None` 走改前算式。
    """
    gain = ENGRAVE_GAIN if gain is None else gain
    ink = _engrave_ink(t2d, edges, period=period, ridge=ridge, mix=mix)
    if amp is None:
        c = ink - float(ink.mean())
    else:
        a = np.clip(amp, 0.0, 1.0).astype(np.float64)
        sw = float(a.sum())
        mu = float((a * ink).sum()) / sw if sw > 1e-6 else float(ink.mean())
        c = a * (ink - mu)
    return rgb * np.exp(-gain * c)[..., None]


# 分带强度（DY-18 上岗）：0 = 均匀台阶（改前行为，逐字节回得去），1 = 带边纯分位。
QBAND_LAM = _envf("MEDAL_QBAND", 0.7)


def _posterize(t, bands=RELIEF_BANDS):
    """把连续电平场切成 `bands` 级。带边位置由 `MEDAL_QBAND`（λ）插值：
    λ=0 ⇒ 均匀台阶 `[0,1]`（老写法），λ=1 ⇒ 带边完全落在场自身的分位上。

    现链的问题不是带数（§9 的反面证据），是**均匀台阶**：照片场的质量集中在高端，
    于是中间调整段被并进同一级 ⇒ 章面糊成"看不出刻了什么"。带边挪到分位后
    中间调被拆开（全池 24 格里 16 格目检明确更好）。
    **λ 不是 1**：四等分质量 ⇒ 最低一级独占 25% 像素，λ=1 把本来就暗的主体压成黑剪影
    （pet_dog 银暗部 50.86%）、把亮主体的肩部推成白纸。0.7 = 8 格代表板目检取到的拐点
    （双色守卫实测）。
    """
    if QBAND_LAM <= 0.0 or bands <= 1:
        return np.round(np.clip(t, 0.0, 1.0) * (bands - 1)) / (bands - 1)
    v = np.clip(np.asarray(t, dtype=np.float64), 0.0, 1.0)
    q = np.maximum.accumulate(
        np.percentile(v.ravel(), np.linspace(0.0, 100.0, bands + 1)[1:-1]))
    u = (np.arange(bands - 1) + 0.5) / (bands - 1)
    return np.searchsorted((1.0 - QBAND_LAM) * u + QBAND_LAM * q, v) / (bands - 1)


# ===== FB-18 满铺支的带数与并块（2026-10-14 上岗）=====
# 病不在电平，在**带图的连通性**：照片量化后带界两侧全是几像素大的岛，`_emboss` 又在每条岛界
# 上补棱 ⇒ 章面读作马赛克/中灰迷彩。官方银档是"少数几块连续平涂"（LN-1 尺：平涂 50.9% 对比
# 我方满铺面 21.3%，`output/_linenote/ln1_norm202.log`）。
# fb1/fb2 当年判负的理由「并完还是刻满线的块」已经不再成立：那之后上岗了 `FB_STOP`（块可以真的
# 静）与 `LA_*` 脊线墨迹（构成由线承载），所以带数/并块重新变成结构性杠杆。
# 取档 = 12 张真照片全池扫（`output/_fb18/fb18_pool.log`）：b3c2 中位平涂 42.9%→57.8%、
# 细脊 2.37%（官方 2.07%）、暗带 15.7%→16.5%；判负臂 b2（带 2）平涂 77.0% 但细脊 1.29% ⇒ 线被并没了。
FB_BANDS = int(_envf("MEDAL_FB_BANDS", 3.0))    # 0 = 跟随全局 RELIEF_BANDS（= 改前档）
FB_CLEAN = int(_envf("MEDAL_FB_CLEAN", 2.0))    # 0 = 不并块
# 两档同时归 0 ⇒ 逐字节回到改前（FB18-2 硬闸：off 臂 24 格与改前树逐字节相同）。
# bands=1 会走进 `_posterize` 的 `(x*(bands-1))/(bands-1)`：numpy 的浮点除零只给 Warning + nan，
# **不抛异常** ⇒ 非法档必须在这里拦住，不能指望下游响。
assert FB_BANDS == 0 or 2 <= FB_BANDS <= 8, "MEDAL_FB_BANDS 只允许 0 或 2..8"


def _band_collapse(p, radius, bands=RELIEF_BANDS):
    """对**分带索引图**做圆盘多数表决，把碎斑并进邻域主体；平票保持自身带。

    平票口径 = 票数×2 + 自身 1 票 ⇒ 严格多数才翻盘，带界不会被往任一侧推。
    邻域一律从 `np.pad` 之后的数组取（`r+dy ≥ 0` 恒成立）：裸 `p[dy:dy+h]` 在 `dy<0` 时
    切出空数组，会死在批量中途（本机坑 ㊴）。
    """
    r = int(radius)
    if r <= 0 or bands <= 1:
        return p
    idx = np.rint(np.clip(p, 0.0, 1.0) * (bands - 1)).astype(np.int16)
    h, w = idx.shape
    pad = np.pad(idx, r, mode="edge")
    cnt = np.zeros((bands, h, w), dtype=np.int32)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy * dy + dx * dx > r * r:
                continue
            win = pad[r + dy:r + dy + h, r + dx:r + dx + w]
            for k in range(bands):
                cnt[k] += (win == k)
    for k in range(bands):
        cnt[k] *= 2
        cnt[k] += (idx == k)
    return cnt.argmax(0).astype(np.float64) / (bands - 1)


# ===== 章体厚斜边（N-1，2026-10-12 章体结构轮上岗）=====
# 靶值 = 官方金 51 / 银 17 枚**零渲染现读**：
# 外缘亮脊占半径 0.8–3.8%（峰 +7%）、向内暗槽占 6.1–10.6%（金 −11%、银 −4.5%），
# 两条带的电平都按**同扇深场**归一 ⇒ 比值里不含章体自身的大梯度，剩下的就是倒角。
# 扇号与量测口径同源：0=右、1=右下、2=左下、3=左、4=左上、5=右上（法向角，y 轴向下）。
# 取档 = 12 张真照片 × 两档 × 三臂全池目检：`rim` 在 24/24 格上都是肉眼可见的收益
# （银档最明显：边缘从「贴纸」变成「板」）——但用户多轮裁定"左+左下立体感条状=画蛇添足"
# （rim=0 对照确认条状来源即本层），默认 0.15（1/6 幅度，条状不可察觉；回归要求非恒等）；`MEDAL_RIM=1` 复现旧观感。
RIM_AMP_DEFAULT = 0.15
RIM_AMP = _envf("MEDAL_RIM", RIM_AMP_DEFAULT)
RIM_TGT = {
    "ef_gold": ((1.022, 1.049, 1.127, 1.114, 1.005, 1.059),
                (0.984, 0.882, 0.925, 0.960, 0.974, 1.016)),
    "ef_silver": ((0.972, 0.950, 0.896, 0.797, 1.050, 1.052),
                  (1.007, 0.955, 0.713, 0.860, 1.004, 0.995)),
}
RIM_PEAK_U, RIM_PEAK_S = 0.018, 0.020        # 亮脊峰位 / 高斯宽（÷R）
RIM_TROUGH_U, RIM_TROUGH_S = 0.078, 0.040    # 暗槽槽位 / 宽（÷R）
RIM_BANDS = ((0.008, 0.038), (0.061, 0.106))  # = 量测 k∈[1,5) / [8,14)（÷等效半径 132）
RIM_CANVAS = (1000, 1240, 500, 620, 470)     # compose_endfield 的章体几何，网页镜像同底
_RIM_GEOM_CACHE = {}


def _rim_geom(cw, ch, cx, cy, R):
    """像元 → (法向扇号, 到最近那条边的**垂直**距离 ÷ R)。pointy-top 六边的外法向在 0/60/…/300°。"""
    key = (cw, ch, cx, cy, R)
    if key not in _RIM_GEOM_CACHE:
        yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
        dx, dy = xx - cx, yy - cy
        ap = R * math.sqrt(3.0) / 2.0
        dn = None
        for i in range(6):
            th = math.radians(60.0 * i)
            d = ap - (dx * math.cos(th) + dy * math.sin(th))
            dn = d if dn is None else np.minimum(dn, d)
        ang = (np.degrees(np.arctan2(dy, dx)) + 360.0) % 360.0
        _RIM_GEOM_CACHE[key] = (((ang + 30.0) % 360.0) // 60.0,
                                np.clip(dn, 0.0, None) / R)
    return _RIM_GEOM_CACHE[key]


def _rim_basis(u):
    """两条高斯杠杆 + 两条量测带（带定义 = 量测的 k 区间，不另发明口径）。"""
    ridge = np.exp(-(((u - RIM_PEAK_U) / RIM_PEAK_S) ** 2)).astype(np.float32)
    groove = np.exp(-(((u - RIM_TROUGH_U) / RIM_TROUGH_S) ** 2)).astype(np.float32)
    b1 = (u >= RIM_BANDS[0][0]) & (u < RIM_BANDS[0][1])
    b2 = (u >= RIM_BANDS[1][0]) & (u < RIM_BANDS[1][1])
    return ridge, groove, b1, b2


def rim_coeffs(tone, cw, ch, cx, cy, R):
    """扇号 → (亮脊系数, 暗槽系数)。纯几何 2×2 解、零随机、零渲染 ⇒ 可作为网页镜像的
    单一事实源（网页与引擎解的是同一个方程）。
    """
    if tone not in RIM_TGT:
        return {}
    ridge_t, groove_t = RIM_TGT[tone]
    sec, u = _rim_geom(cw, ch, cx, cy, R)
    ridge, groove, b1, b2 = _rim_basis(u)
    out = {}
    for s in range(6):
        m = (sec == s) & (u < 1.0)
        sel1, sel2 = (b1 & m), (b2 & m)
        if sel1.sum() < 50 or sel2.sum() < 50:
            continue
        A = np.array([[ridge[sel1].mean(), groove[sel1].mean()],
                      [ridge[sel2].mean(), groove[sel2].mean()]], dtype=np.float64)
        b = np.array([ridge_t[s] - 1.0, groove_t[s] - 1.0], dtype=np.float64)
        a1, a2 = np.linalg.solve(A, b)
        out[s] = (float(a1), float(a2))
    return out


def _ef_rim_gain(tone, cw, ch, cx, cy, R):
    """厚斜边增益图。峰位/槽位是几何（两档同位同高 ⇒ 常数），**幅度按法向扇逐扇解 2×2**
    （亮脊与暗槽两条高斯在两条带里互渗，单解一条会偏），使两条带的像元均值正好落在实测比值上。
    """
    coef = rim_coeffs(tone, cw, ch, cx, cy, R)
    if not coef:
        return None
    sec, u = _rim_geom(cw, ch, cx, cy, R)
    ridge, groove, _, _ = _rim_basis(u)
    g = np.ones((ch, cw), dtype=np.float32)
    for s, (a1, a2) in coef.items():
        m = (sec == s) & (u < 1.0)
        g[m] = np.clip(1.0 + RIM_AMP * (a1 * ridge[m] + a2 * groove[m]), 0.0, 4.0)
    return g


def _emboss(out_rgb, t2d, hi_c, lo_c, strength=1.0):
    """按电平场 t2d 的方向斜率给已上色的章面补高光/阴影两侧。"""
    raw = -(np.gradient(t2d, axis=1) * EMBOSS_LX + np.gradient(t2d, axis=0) * EMBOSS_LY)
    scale = float(np.percentile(np.abs(raw), EMBOSS_NORM_PCT))
    if scale < 1e-5:
        return out_rgb
    sh = _gauss_arr(np.clip(raw / scale * strength, -1.0, 1.0), 0.9)
    hi = (hi_c[None, None, :] - out_rgb) * np.clip(sh, 0, 1)[..., None] * EMBOSS_HI
    lo = (lo_c[None, None, :] - out_rgb) * np.clip(-sh, 0, 1)[..., None] * EMBOSS_LO
    return out_rgb + hi + lo


def _luma_span(img):
    """Rec.601 明度的极差（灰阶 0~255）：章面「自己有没有拉开」的量。"""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    luma = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    return float(luma.max() - luma.min())


# 回退支自动色阶的跨度门限（灰阶）。实测：平坦类输入（纯色/雾天）章面跨度 3.9~8.0，
# 真实照片输入 36.2~107.5，官方章面跨度 p1 锚 162.2 —— 取平坦间隙几何平均并受 p1 封顶。
# （这组跨度由本地一次性实测得出，量测脚本不随包发布。）
FALLBACK_POLISH_SPAN_MIN = 17.0


# 色板（取自官方素材色值，经视觉复核校准）
PALETTES = {
    # ===== 明日方舟 =====
    # 标准晋升系列：中灰蓝哑光底上银白线描
    "silver":     ((64, 74, 84), (190, 202, 209), (247, 250, 251)),
    # 活动金章：浅乳白珐琅底上深金线描（对标 KAZIMIERZ 明亮鎏金语言）
    "gold":       ((214, 186, 124), (200, 156, 76), (148, 110, 44)),
    # 镀层基底（再叠全息虹彩镀膜）
    "plated":     ((70, 81, 92), (196, 208, 215), (250, 252, 253)),
    # ===== 终末地（阳极氧化金属：亮金属面 + 深色蚀刻线稿）=====
    # 银色·初期：缎面银白金属，深灰阴刻线
    "ef_silver":  ((52, 56, 60), (150, 154, 158), (240, 240, 238)),
    "ef_gold_pure": ((196, 150, 70), (240, 228, 190), (244, 236, 205)),   # R-10 回退 R-4（用户裁定 R-5 起一直退步）
    # 金色·加工：暖金铜面，深棕蚀刻线
    "ef_gold":    ((206, 158, 74), (240, 228, 190), (244, 236, 205)),
    # 炫彩·特殊镀层：亮基底上白色线稿（虹彩由镀膜层负责）
    "ef_irid":    ((150, 136, 114), (212, 202, 190), (255, 255, 255)),
    # 深灰排名章：近黑场 + 白蚀刻（#N 角标）
    "ef_dark":    ((45, 47, 49), (180, 182, 184), (248, 248, 246)),
    # 铜阶（与深灰共场、去排名角标）
    "ef_bronze":  ((45, 47, 49), (180, 182, 184), (248, 248, 246)),
    # 虹彩珠光镀层：白珠光场 + 深灰蚀刻
    "ef_pearl":   ((228, 232, 236), (118, 124, 130), (42, 46, 52)),
    # 社区主流：浅银金属底 + 深蚀刻线（dark-on-light 极性用）
    "steel":      ((214, 219, 224), (120, 128, 136), (40, 47, 54)),
    # 糖果贴纸：焦糖描边 + 粉彩面 + 奶油高光
    "candy":      ((185, 122, 86), (244, 198, 196), (255, 253, 246)),
}
FIELD_COLORS = {
    "silver": ((96, 108, 118), (76, 87, 97)),         # 官方实测中灰蓝（#4a5560 邻域）
    "gold": ((243, 236, 216), (222, 208, 178)),       # 浅乳白珐琅
    "plated": ((152, 164, 172), (124, 136, 144)),     # 镀层基于银白银面
    "steel": ((214, 219, 224), (172, 180, 188)),      # 社区主流：浅银金属底+深蚀刻线
}


def etch_face(rgba, tone="silver", line_strength=1.0, detail=1.0, face_px=FACE_PX,
              mode="line", duality_k=None):
    """mode: line=蚀刻线稿 | silhouette=剪影纹章 | facet=分面平涂

    `duality_k` 只给双色轮的**两趟闸门**用（同一张 `subject` 分别按开/关渲一趟）；
    省略 = 读 `DUALITY_K` 默认值，既有调用方逐字节不变。"""
    sub = crop_to_subject(rgba)
    ratio = face_px / max(sub.size)
    sub = sub.resize((max(1, int(sub.width * ratio)), max(1, int(sub.height * ratio))),
                     Image.LANCZOS)
    g = _gray_arr(sub)
    h, w = g.shape
    sigma = max(0.5, 1.1 / max(detail, 0.05))
    g1 = _gauss_arr(g, sigma)
    g2 = _gauss_arr(g, sigma * 1.9)
    edges = np.abs(g1 - g2)
    emax = max(float(edges.max()), 1e-5)
    edges = np.clip(edges / (emax * 0.55), 0.0, 1.0)
    tone_map = 1.0 - _gauss_arr(g, 5.0)

    ls = min(1.8, max(0.3, line_strength))

    # 各色板明暗极性不同：剪影填充值按色调指定（保证"深色剪影/浅色剪影"正确）
    SILO_FILL = {"silver": 0.66, "gold": 0.60, "plated": 0.66,
                 "ef_silver": 0.84, "ef_gold": 0.84, "ef_irid": 0.92,
                 "industrial": 0.66}
    fill_t = SILO_FILL.get(tone, 0.62)
    # 剪影/整图两支走「暗金属→亮金属」直连坡道（见下方 relief_ramp 处注释），
    # 线稿/分面/图标三支仍走色板三段式 pivot。
    relief_ramp = False
    eng_src = None   # N-11：非 None = 排线的深浅来源被换成「压平前」的照片场
    lamp = None      # N-12：非 None = 排线的**资格**逐点受停线门限调制
    fb_amp = None    # FB-8：非 None = 满铺支自己的停线资格图（只在满铺开火那一段里算）
    fb_ridge = None  # LN-2：非 None = 满铺支自己的脊线笔画芯（同上，只在满铺开火那一段里算）

    if mode == "silhouette":
        # 剪影纹章：外形按素材那样是实心块，但块内保留照片自身的明暗起伏。
        # 旧写法块内是一整片 fill_t 平涂 ⇒ 真人照片进来只剩一张白剪纸（五官、
        # 长椅、毛发全丢），这是「做出来的是一坨」的主要来源。
        g8 = (g * 255).astype(np.uint8)
        av = np.asarray(sub.getchannel("A"), dtype=np.float32) / 255.0
        # 色阶参考直方图只取**块内**像素。整帧统计时逆光照的亮天会把高光顶到
        # 255，autocontrast 后块内仍是一片白 ⇒ 金档纹章渲成过曝奶油。
        lut = np.asarray(_stretch_lut(
            np.bincount(g8[av > 0.5].ravel(), minlength=256)[:256]), dtype=np.uint8)
        ga = lut[g8].astype(np.float32) / 255.0
        solid = _gauss_arr(av, 2.0)
        # 不再垫 0.34 地板：坡道是 lo_c→hi_c 全行程，垫高会把暗的一半扔掉，
        # 金档（lo_c≈(128,98,46)）实测因此只走到 190→250，纹章糊进底色场。
        bg_t = max(0.10, fill_t - 0.42)
        # 双色轮：映射在**平滑之后、分带之前**（顺序理由 = HS 轮已证平滑治椒盐，
        # 而映射是单调的，放在分带之后只会搬台阶、不会改形状）。
        # 判病不在这里做：`generate()` 先按 k=0 渲第一趟，量成图中央块，病了才开这支重跑。
        # `field`（照片明暗）与 `edge_t`（轮廓那一圈抬上去的棱）分开算：下面的压平只吃前者，
        # 棱在压平**之后**加回。拆之前二者相加就是 `inner`。
        edge_t = edges * (0.16 + FACE_INK) * ls
        cont = _duality_map(_face_field_smooth(ga), _dual_knots(tone), av > 0.5, k=duality_k)
        field = _posterize(cont)
        inner = np.clip(field + edge_t, 0.0, 1.0)
        if SILO_POLAR_K > 0.0 and tone in SILO_POLAR:
            # 官方的明暗极性是**设计**出来的，不是照片给的：金档 = 浅色主体压在暖金底上，
            # 银档 = 深色石墨主体压在近白板上。直接搬照片极性时，黑毛狗在银档把整枚章压成
            # 暗牌（mean 125 vs 官方 158），金档又读作一张棕色照片而不是蚀刻金属。
            # 块内亮度先归一到满量程、再整体搬进该档目标窗口（窗口只占坡道一小段，
            # 不平涂 —— 平涂就是上面注释里那张"白剪纸"老病，五官/毛发全丢）。
            bg_t, sub_t = SILO_POLAR[tone]
            inside = ga[av > 0.5]
            lo_q, hi_q = (np.percentile(inside, [5.0, 95.0]) if inside.size else (0.0, 1.0))
            norm = np.clip((ga - lo_q) / max(float(hi_q - lo_q), 1e-3), 0.0, 1.0)
            # 分带**先于**落位：先把块内亮度归一后量化成满量程 4 带，再把 4 带整体搬进
            # 该档的目标窗口。反过来（先压缩再 `_posterize`）会把 4 带里的两级挤到窗口外，
            # 现读 face spread 135→91（五官/毛发明显发糊），比"台阶数"这个量更能指到病。
            half = SILO_POLAR_SPAN / 2.0
            cont = _face_field_smooth(norm)
            field = sub_t - half + _posterize(cont) * SILO_POLAR_SPAN
            edge_t = edges * 0.16 * ls
            inner = np.clip(field + edge_t, 0.0, 1.0)
        if EMBLEM_GAIN > 0.0 and tone in EMBLEM_TONES and engrave_enabled(tone):
            # 先留一份「压平前」的主体场给排线当深浅来源，再把主体压成平底板 ⇒ 同一处明暗只以
            # 线宽出现一次。与 `engrave_enabled` 取**与**：排线开关被关掉时不能只留平涂块。
            # 压平只吃 `field`（照片明暗），轮廓棱 `edge_t` 压完再加回：`HOLD` 若乘在含棱的
            # `inner` 整体上，`0.20 × edge` 只给那一圈留 0.032 的行程（离板越远还被 clip 削到
            # 0.010），而单独加回是全额 0.160 ⇒ 主体外缘就糊了，正是 §六十七 那条
            # 「边界靠线密不靠块」的来源。
            eng_src = np.clip(inner, 0.0, 1.0).astype(np.float32)
            _b = _emblem_base(tone)
            lamp = None
            if LINESTOP > 0.0 or EDGE_GATE > 0.0:
                # 只给主体内发资格（主体外置 1.0 ⇒ 背景那一段与 N-11 同）。
                _sel = solid > 0.45
                lamp = np.where(_sel, _linestop_amp(cont, _sel), 1.0).astype(np.float32)
            if EDGE_GATE > 0.0:
                edge_t = edge_t * np.power(lamp, EDGE_GATE)
            inner = np.clip(_b + (field - _b) * EMBLEM_HOLD + edge_t, 0.0, 1.0).astype(np.float32)
        t = np.where(solid > 0.45, inner, bg_t).astype(np.float32)
        if eng_src is not None:
            # 主体外用当前场 ⇒ 背景那一段的排线行为与改前同（这一支只动主体）。
            eng_src = np.where(solid > 0.45, eng_src, t).astype(np.float32)
        t = np.clip(t, 0.0, 1.0)
        relief_ramp = True
    elif mode == "facet":
        # 分面平涂：直方图均衡强制多层级（天空等平滑区也能分带）+ 细轮廓
        from PIL import ImageOps
        g_img = Image.fromarray((g * 255).astype(np.uint8), "L")
        g_img = ImageOps.autocontrast(g_img, cutoff=2)
        g_img = ImageOps.equalize(g_img)
        g_eq = np.asarray(g_img, dtype=np.float32) / 255.0
        tb = _gauss_arr(g_eq, max(1.0, 1.6 / max(detail, 0.05)))
        lv = np.digitize(tb, [0.25, 0.50, 0.75]).astype(np.float32)
        t = 0.18 + lv * 0.19
        t = np.clip(t + edges * 0.38 * ls, 0.0, 1.0)
    elif mode == "icon":
        # 经典图标化兜底：强分面 + 形态学清洗 + 均匀粗轮廓（尽力靠近"图案感"）
        from PIL import ImageOps as _IO2
        g_s = Image.fromarray((g * 255).astype(np.uint8), "L")
        g_s = _IO2.autocontrast(g_s.filter(ImageFilter.MedianFilter(7))
                                .filter(ImageFilter.GaussianBlur(1.2)), cutoff=1)
        gs = np.asarray(g_s, dtype=np.float32) / 255.0
        lv = np.digitize(gs, [0.35, 0.68]).astype(np.float32)
        t = 0.28 + lv * 0.30
        t = np.clip(t + edges * 0.45 * ls, 0.0, 1.0)
    else:
        # 蚀刻线稿（默认）：多尺度轮廓 + 局部对比增强（保住五官等细节）
        s_fine = max(0.4, sigma * 0.55)
        f1 = _gauss_arr(g, s_fine)
        f2 = _gauss_arr(g, s_fine * 1.8)
        edges_fine = np.abs(f1 - f2)
        edges = np.clip(edges * 0.55
                        + edges_fine / max(float(edges_fine.max()), 1e-5) * 0.45,
                        0.0, 1.0)
        local = np.clip((g - _gauss_arr(g, 6.0)) * 1.6 + 0.5, 0.0, 1.0)
        tone_map = 1.0 - _gauss_arr(g, 5.0)
        ht = _hatch(h, w, period=max(7.0, 12.0 / max(detail, 0.05)))
        hatch = ht * np.clip(tone_map * 1.3 - 0.4, 0, 1) * 0.22
        hatch = hatch * (1.0 - np.clip(edges, 0, 1) * 0.75)   # 轮廓优先：强边处排线让路
        t = np.clip(0.30 + (1.0 - local) * 0.26 + edges * 0.62 * ls
                    + hatch * 0.6 * ls, 0.0, 1.0)

    pal = PALETTES[tone]
    dark, mid, bright = [np.asarray(c, dtype=np.float32) for c in pal]
    # 照片亮度驱动的两支坡道（剪影 / 整图）顶端落点：金档默认停在 mid（暖金高光）而非
    # bright（近白）。line 支不受影响 —— 那里的近白是**蚀刻笔画**，不是照片的高光区。
    hi_c = _plate_top(tone, mid, bright)
    tt = t[..., None]
    if relief_ramp:
        # 色板三段式 pivot 是给蚀刻线稿的：金档 mid=(240,228,190) 与 bright=(252,250,240)
        # 几乎同色，剪影/整图沿用会把一半动态范围渲成白，人像五官与毛发全糊。
        # 直连坡道并把暗端压一档（ef_gold 的 dark=(206,158,74) 仍是亮金，
        # 素材侧章面暗端实测到古铜 ~150,105,35）。
        lo_c = dark * 0.62
        out_rgb = lo_c + (hi_c - lo_c) * tt
    else:
        lo = dark + (mid - dark) * np.clip(tt * 2.0, 0, 1)
        hi = mid + (bright - mid) * np.clip(tt * 2.0 - 1.0, 0, 1)
        out_rgb = np.where(tt < 0.5, lo, hi)
        lo_c = dark * 0.62

    face = Image.fromarray(np.clip(out_rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    fa = sub.getchannel("A").filter(ImageFilter.GaussianBlur(0.5))
    # 整图入章（抠图回退）：大圆角 + 宽羽化 + 边缘压暗，画面融进章面金属底
    a_min, a_max = fa.getextrema()
    # 跨度门限只判 line 档。根本理由：A1 的病料是「引擎自己的排线」，而 `_hatch()` 只在
    # line 支被调用 ⇒ 其余档没有可被刻深的线；实测理由：门限一并管到别的档时，
    # 83 张全矩阵 A/B 出现一张真照片差分行（landscape/ef_gold/silhouette）—— silhouette
    # 的平涂是设计意图，不该被当成"输入没信息"而关掉抛光。这条间隙本来就只在 line 支
    # 量过（当初逐行复刻同一套章面电平的本地脚本，不随包发布）。
    span_ok = mode != "line" or _luma_span(face) >= FALLBACK_POLISH_SPAN_MIN
    if a_min > 200 and span_ok:
        # 整图入章：铺满章面做「金属浮雕」，不是往金属上贴一张照片。
        # 旧写法（圆角 + 宽羽化 + 边缘压暗 + 自动色阶）在暗照片上必崩：自动色阶把
        # 夜景的黑天拉到 0，边缘压暗再乘 0.72 ⇒ 章心一块黑方牌，与素材任何一档都对不上。
        # 现改为把**照片自身亮度**重映射进色板全坡道（0.10~1.00）：暗部落在金属本色
        # （金档=古铜、银档=石墨）而非黑色，整枚章读作一块蚀刻金属浮雕。
        from PIL import ImageOps as _IO
        l = np.asarray(_IO.autocontrast(sub.convert("RGB"), cutoff=1)
                       .convert("L"), dtype=np.float32) / 255.0
        l = _gauss_arr(l, 0.6 + FACE_SMOOTH)
        lo_c = dark * 0.62
        # FB-18：两支杠杆都只在这**一段**里接线（㊾：作用面靠调用点，不靠 env 值）。
        # `bands_fb` 同时喂锚与最终分带 ⇒ 二者用同一把带边，锚不会把带数的效果补偿掉。
        bands_fb = FB_BANDS if FB_BANDS > 0 else RELIEF_BANDS
        l = _plate_level_lock(l, tone, lo_c, hi_c, bands=bands_fb)
        # 双色轮（回退支，单独开关 `MEDAL_DUALITY_FB`）：这一支的 `field_t = 0.10 + 0.90*带`
        # ⇒ 靶钉要先换算回 l 域（off=0.10 / mul=0.90）再映射，映射仍在分带之前。
        l = _duality_map(l, _dual_knots(tone, 0.10, 0.90), k=DUALITY_FB)
        # 墨线只在 FACE_INK≠0 时进加法：`edges` 是 float32，无脑相加会把整条坡道抬成
        # float64，`astype(uint8)` 前的截断位置随之改变 ⇒ 关掉开关时做不到逐字节回到改前。
        p_fb = _posterize(l, bands_fb)
        if FB_CLEAN > 0:
            p_fb = _band_collapse(p_fb, FB_CLEAN, bands=bands_fb)
        field_t = 0.10 + 0.90 * p_fb
        if FACE_INK != 0.0:
            field_t = field_t + edges * FACE_INK
        t2 = np.clip(field_t, 0.0, 1.0)[..., None]
        # 浮雕坡道走「暗金→亮金」直连，且暗端要再压一档：
        # ① 不用色板 mid pivot —— 那是给蚀刻线稿的三段式用的，金档 mid/bright
        #    几乎同色（(240,228,190)/(252,250,240)），沿用会把一半动态范围渲成白。
        # ② 不用 dark 本身 —— ef_gold 的 dark=(206,158,74) 仍是亮金，整块浮雕明度
        #    只走 162→250，读起来是过曝奶油照而不是金属；素材侧暗端实测到古铜 (~150,105,35)。
        rgb = lo_c + (hi_c - lo_c) * t2
        rgb = _emboss(rgb, t2[..., 0], hi_c, lo_c, EMBOSS_STRENGTH.get(mode, 1.0))
        field = t2[..., 0]
        # 满铺支（抠图回退）走自己那条电平链，剪影支算出的 `eng_src` 在这里是**废值** ⇒ 必须清掉，
        # 否则 N-11 的杠杆顺手套进满铺支，「只动主体」这条口径就破了。
        eng_src = None
        lamp = None      # 同上：N-12 的幅度图也不许漏进满铺支
        # FB-8：这一支自己的停线资格。门限吃**分带前**的连续场 `l`（不是已分带的 `field`——
        # 带内线宽恒定正是病根本身），主体掩膜传 None：满铺型照片整幅都是主体，没有"主体外"。
        if FB_STOP > 0.0:
            fb_amp = _linestop_amp(np.clip(l, 0.0, 1.0), None, p=FB_STOP,
                                   win=(FB_STOP_WIN or None), q=FB_STOP_Q,
                                   floor=FB_STOP_FLOOR)
        # LN-2：脊线也只在这**一段**里算（㊾ 的调用点口径）。首版把 `LA_FB` 的脊算在下面的
        # 共享调用点上 ⇒ `mode=line/icon/facet` 这些**同样走 `eng_src is None`** 的路线也吃到
        # 了脊，而 12 张池照只有满铺/剪影两张面 ⇒ 池 A/B 天生看不见这个越界。
        # 与 `fb_amp` 同一处初始化。
        if LA_FB > 0.0 and LA_TAU > 0.0:
            fb_ridge, LA_STAT[("fb", tone)] = _ridge_core(edges, LA_TAU, LA_WIDTH)
        fa = Image.new("L", sub.size, 255)
    else:
        rgb = _emboss(out_rgb, t, hi_c if relief_ramp else bright, lo_c,
                      EMBOSS_STRENGTH.get(mode, 1.0))
        field = t
    # 排线纹理在**浮雕之后**压上去：让它参与 `_emboss` 的话，高频线会把斜率分位归一
    # 的预测顶大、把主棱边冲淡。放在后面 = 关掉时逐字节回到改前。
    if engrave_enabled(tone):
        if eng_src is not None:
            # N-11：坡道吃**压平后**的场、排线吃**压平前**的照片场 ⇒ 明暗只以线宽承载一次。
            # 线间距走 `EMBLEM_PERIOD`（0 = 跟随全局），加粗只发给剪影支，满铺支逐字节不变。
            # N-12：`lamp`=逐点"这块金属有没有资格被刻"，None 时算式与 N-11 完全一致。
            # LN-2：脊线只由**本支自己的开关** `LA_SILO` 发（㊾：满铺支的旋钮不在这条路上）。
            # 默认档 `LA_SILO=0` ⇒ 这一支恒 `ridge=None`，剪影面逐字节回到改前。
            ridge = None
            if LA_SILO > 0.0 and LA_TAU > 0.0:
                ridge, LA_STAT[("silo", tone)] = _ridge_core(edges, LA_TAU, LA_WIDTH)
            rgb = _engrave_shade(rgb, eng_src, edges, gain=EMBLEM_GAIN,
                                 period=(EMBLEM_PERIOD or None), amp=lamp,
                                 ridge=ridge, mix=LA_MIX)
        else:
            # FB-8 的 `fb_amp` 与 LN-2 的 `fb_ridge` 只可能由满铺支那一段填上
            # （其余路线恒 None ⇒ 算式逐字回到改前；隔离靠调用点，不靠 env 值，㊾）
            rgb = _engrave_shade(rgb, field, edges, amp=fb_amp, ridge=fb_ridge, mix=LA_MIX)
    face = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    face.putalpha(fa)
    return face


# ----------------------------------------------------------------------------
# 三、明日方舟模板 v5（参照公开官方素材）
# ----------------------------------------------------------------------------

def _hex_pts(cx, cy, r, rot_deg=0.0):
    """pointy-top 默认（顶点在正上方）"""
    pts = []
    for i in range(6):
        ang = math.radians(rot_deg + 60 * i - 90)
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _hex_halfwidth(r, dy):
    """pointy-top 六边形在竖直偏移 dy 处的半宽"""
    d = abs(dy)
    if d >= r:
        return 0.0
    return (r - d) / r * (r * math.sqrt(3) / 2.0)


def _halftone_tile(period=7, dot=1.4, color=(0, 0, 0), alpha=30, offset=True, ss=1):
    """规则网点抖动瓦片（模拟官方亚光金属网点）

    `ss`>1：按 ss× 超采样画圆再 `Image.BOX` 面积均缩回，占空比 = 声明值
    π·dot²/period²。默认 1 保持旧画法（方舟/糖果侧渲染字节不变）。旧画法在 dot 小
    于一个像元量级时不可信：`period=5, dot=1.6` 声明 32.2% 占空、Pillow 实画 **84.0%**
    ⇒「网点」变成「整片暗膜上留针孔」。
    """
    s = period
    if ss > 1:
        n = s * ss
        m = Image.new("L", (n, n), 0)
        md = ImageDraw.Draw(m)
        r = dot * ss
        if offset:
            for qx, qy in ((0, 0), (n, 0), (0, n), (n, n)):
                md.ellipse([qx - r, qy - r, qx + r, qy + r], fill=alpha // 2)
        md.ellipse([n / 2 - r, n / 2 - r, n / 2 + r, n / 2 + r], fill=alpha)
        tile = Image.new("RGBA", (s, s), color + (0,))
        tile.putalpha(m.resize((s, s), Image.BOX))
        return tile
    tile = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    r = dot
    d.ellipse([s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r], fill=color + (alpha,))
    if offset:
        d.ellipse([-r, -r, r, r], fill=color + (alpha // 2,))
        d.ellipse([s - r, -r, s + r, r], fill=color + (alpha // 2,))
        d.ellipse([-r, s - r, r, s + r], fill=color + (alpha // 2,))
        d.ellipse([s - r, s - r, s + r, s + r], fill=color + (alpha // 2,))
    return tile


def _iridescent_overlay(size, alpha=88, edge_mask=None):
    """镀层全息虹彩：随形箔片光泽——只在高光边缘与边框环带附着"""
    w, h = size
    grad = Image.new("RGB", (w, 1))
    px = grad.load()
    n_steps = 7
    stops = [(0.53, 0.83, 0.89), (0.83, 0.48, 0.78), (0.39, 0.72, 0.65),
             (0.93, 0.93, 0.95), (0.53, 0.83, 0.89)]
    for x in range(w):
        t = x / max(w - 1, 1) * (n_steps) % 1.0
        seg = int(t * (len(stops) - 1))
        tt = t * (len(stops) - 1) - seg
        c0, c1 = stops[seg], stops[min(seg + 1, len(stops) - 1)]
        r0, g0, b0 = [min(255, int(v * 255 * 1.15)) for v in colorsys.hsv_to_rgb(*c0)]
        r1, g1, b1 = [min(255, int(v * 255 * 1.15)) for v in colorsys.hsv_to_rgb(*c1)]
        px[x, 0] = (int(r0 + (r1 - r0) * tt), int(g0 + (g1 - g0) * tt), int(b0 + (b1 - b0) * tt))
    grad = grad.resize((w, h)).rotate(24, expand=False)
    ov = grad.convert("RGBA")
    if edge_mask is not None:
        a = np.asarray(edge_mask.resize((w, h)), dtype=np.float32) / 255.0 * alpha
    else:
        a = np.full((h, w), alpha, dtype=np.float32)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        mod = np.sin(xx / w * math.pi * 3 + yy / h * math.pi * 1.2) * 0.5 + 0.5
        mod = mod ** 1.6 * 0.85 + 0.15
        a = a * mod
    ov.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L"))
    return ov


def _edge_alpha(img_rgba, gain=2.2):
    """提取轮廓缘 alpha（用于随形镀层附着与落刀描边）"""
    a = img_rgba.getchannel("A").filter(ImageFilter.GaussianBlur(1))
    hi = a.filter(ImageFilter.MaxFilter(3))
    lo = a.filter(ImageFilter.MinFilter(3))
    edge = np.asarray(hi, dtype=np.float32) - np.asarray(lo, dtype=np.float32)
    return Image.fromarray(np.clip(edge * gain, 0, 255).astype(np.uint8), "L")


def _star(draw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        ang = math.radians(-90 + i * 36)
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    draw.polygon(pts, fill=fill)



# ---- FB-37 R-1 杠杆开关（默认开；=0 单关，便于归因与回退）----
import os as _os
def _fb37(name):
    return _os.environ.get("MEDAL_FB37_" + name, "1") != "0"
FB37_RIM    = _fb37("RIM")     # 外缘宽深 tone 带（唯一硬靶）
FB37_FRAME  = _fb37("FRAME")   # 双层粗框（替代四细线）
FB37_BANDS  = _fb37("BANDS")   # 底场 8 级明度带
FB37_MIRROR = _fb37("MIRROR")  # 左右非对称偏置
FB37_RAYS   = _fb37("RAYS")    # 放射线增强
FB37_SEAT   = _fb37("SEAT")    # 纹章座圈环
FB37_DARK   = _fb37("DARK")    # 深底亮线极性（官方 pair01 型：深场+亮纹样）
FB37_BAND   = _fb37("BAND")    # 缎带收敛


def _ring_text(canvas, cx, cy, r, chars, font, fill, a0=0.0, a1=360.0,
               jitter=6, seed=7):
    """环形文字（官方 E6 词汇）：字符沿弧排布、各自旋转贴回、位置带受控错落"""
    rng = np.random.default_rng(seed)
    n = max(1, len(chars))
    for i, c in enumerate(chars):
        if c == " ":
            continue
        a = math.radians(a0 + (a1 - a0) * (i + 0.5) / n)
        bb = font.getbbox(c)
        cw, ch = bb[2] - bb[0] + 10, bb[3] - bb[1] + 10
        tile = Image.new("RGBA", (cw + 10, ch + 10), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((5 - bb[0], 5 - bb[1]), c, font=font, fill=fill)
        tile = tile.rotate(-(math.degrees(a) + 90), expand=True,
                           resample=Image.BICUBIC)
        jx = rng.uniform(-jitter, jitter)
        jy = rng.uniform(-jitter, jitter)
        px = cx + r * math.cos(a) - tile.width / 2 + jx
        py = cy - r * math.sin(a) - tile.height / 2 + jy
        canvas.paste(tile, (int(px), int(py)), tile)


def compose_arknights(face, text, subtitle="", serial="", tone="silver",
                      number="") -> Image.Image:
    CW, CH = 1000, 1150
    canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    cx, cy, R = CW // 2, 560, 500

    if tone == "gold":
        line_hi, line_mid, line_lo = (239, 228, 192), (201, 162, 79), (138, 106, 47)
        outline_c = (32, 27, 20, 255)
    elif tone == "steel":
        # 社区主流：浅银金属底上的深蚀刻线
        line_hi, line_mid, line_lo = (96, 104, 112), (66, 74, 82), (40, 47, 54)
        outline_c = (40, 47, 54, 255)
    elif tone == "stamp":
        # 朱砂印章路线：纸面底 + 朱红线
        line_hi, line_mid, line_lo = (226, 108, 72), (178, 62, 36), (118, 32, 18)
        outline_c = (118, 32, 18, 255)
    elif tone == "plated":
        line_hi, line_mid, line_lo = (240, 245, 247), (174, 190, 199), (96, 110, 122)
        outline_c = (28, 33, 40, 255)
    else:
        line_hi, line_mid, line_lo = (232, 238, 240), (169, 179, 187), (96, 108, 120)
        outline_c = (43, 50, 58, 255)

    field_top, field_bot = FIELD_COLORS.get(tone, ((235, 228, 214), (216, 208, 190)))
    if FB37_DARK and tone in ("ef_gold_pure", "ef_gold", "ef_silver"):
        # 深底亮线极性（官方 pair01 型）：深场 + 亮纹样线；rim 带转近黑
        _isg = tone != "ef_silver"
        field_top, field_bot = ((74, 58, 38), (32, 26, 18)) if _isg             else ((46, 56, 70), (22, 28, 38))
        line_hi, line_mid = ((244, 234, 200), (208, 172, 96)) if _isg             else ((238, 242, 246), (176, 184, 192))
        line_lo = (150, 128, 82) if _isg else (120, 130, 140)

    # ---- 底场：垂直渐变 →（FB-37）8 级明度台阶 + 左右非对称偏置 ----
    hex_mask = Image.new("L", (CW, CH), 0)
    ImageDraw.Draw(hex_mask).polygon(_hex_pts(cx, cy, R), fill=255)
    field = Image.new("RGB", (CW, CH))
    dfd = ImageDraw.Draw(field)
    steps = 8 if FB37_BANDS else 1
    for y in range(CH):
        t = max(0.0, min(1.0, (y - (cy - R)) / (2 * R)))
        c0, c1 = field_top, field_bot
        col = tuple(c0[i] + (c1[i] - c0[i]) * t for i in range(3))
        if steps > 1:
            q = round(t * (steps - 1)) / (steps - 1)
            q = q * 0.60 + 0.40                            # 亮端偏置（场=亮金，深色留给 rim/框/纹线）
            col = tuple(c0[i] + (c1[i] - c0[i]) * q for i in range(3))
        dfd.line([(0, y), (CW, y)], fill=tuple(int(v) for v in col))
    if FB37_MIRROR:
        # 左右非对称：左亮右暗（官方 mirror 0.148；幅度 8%）
        bias = Image.new("L", (CW, CH), 0)
        bd = ImageDraw.Draw(bias)
        for x in range(0, CW, 4):
            v = int(255 * max(0.0, min(1.0, 0.5 + (cx - x) / CW * 0.55)))
            bd.rectangle([x, 0, x + 3, CH], fill=v)
        bias = bias.filter(ImageFilter.GaussianBlur(40))
        bright = Image.new("RGB", (CW, CH), (255, 255, 255))
        dark = Image.new("RGB", (CW, CH), (12, 14, 18))
        field = Image.composite(bright, field, bias.point(lambda v: v * 45 // 100))
        field = Image.composite(field, dark, bias.point(lambda v: (255 - v) * 10 // 100))
    canvas.paste(field, (0, 0), hex_mask)

    # ---- 多层同心环（FB-37：rim 深带 + 双粗框 + 保留中细线）----
    d = ImageDraw.Draw(canvas)
    if FB37_RIM:
        # 官方唯一硬靶：外缘宽 tone 带（apothem 口径 ≈0.103R=51px，外沿贴 R）
        rim_col = (14, 15, 17) if (FB37_DARK and tone in ("ef_gold_pure", "ef_gold", "ef_silver"))             else tuple(int(c * 0.52) for c in line_lo)
        d.polygon(_hex_pts(cx, cy, R - 35), outline=rim_col + (235,), width=70)
    if FB37_FRAME:
        # 双层粗框（官方 E1：外粗框 + 内粗框，中间隔 rim 带）
        d.polygon(_hex_pts(cx, cy, R - 56), outline=line_hi + (255,), width=9)
        d.polygon(_hex_pts(cx + 2, cy + 3, R - 60),
                  outline=tuple(int(c * 0.45) for c in line_hi) + (170,), width=9)
        d.polygon(_hex_pts(cx, cy, R - 108), outline=line_mid + (255,), width=8)
        d.polygon(_hex_pts(cx, cy, R - 128), outline=line_lo + (220,), width=2)
    else:
        rings = [(R - 4, 3, line_hi),
                 (R - 26, 2, line_mid),
                 (R - 44, 2, line_mid),
                 (R - 60, 2, line_lo)]
        for r, wd, col in rings:
            d.polygon(_hex_pts(cx + 2, cy + 3, r),
                      outline=tuple(int(c * 0.45) for c in col) + (170,), width=wd)
            d.polygon(_hex_pts(cx, cy, r), outline=col + (255,), width=wd)
            d.polygon(_hex_pts(cx - 2, cy - 2, r),
                      outline=tuple(min(255, int(c * 1.35)) for c in col) + (150,), width=wd)

    if tone == "gold":
        # 活动金章：内圈细线上的等距五角星环
        rs = R - 112
        d.polygon(_hex_pts(cx, cy, rs), outline=line_mid + (200,), width=2)
        for i in range(14):
            ang = math.radians(-90 + i * (360 / 14))
            sx = cx + rs * math.cos(ang)
            sy = cy + rs * math.sin(ang)
            _star(d, sx, sy, 9, line_hi + (240,))

    # ---- 放射细线密纹（官方满版语言：从中心向外的太阳纹；印章路线收弱）----
    apothem = R * math.sqrt(3) / 2
    if tone == "stamp":
        ray_c, ray_alpha = (160, 90, 60), 40
    else:
        ray_c = line_mid if (tone != "gold" and FB37_RAYS) else (line_lo if tone != "gold" else (186, 146, 68))
        ray_alpha = (115 if FB37_RAYS else 110) if tone != "gold" else 140
    rays_lim = (R - 195) if (FB37_RIM and FB37_FRAME) else apothem - 20  # 让位环形文字带
    for i in range(72):
        ang = math.radians(i * 5)
        r1 = min(rays_lim, (apothem - 20) if i % 2 == 0 else (apothem - 84))
        x0, y0 = cx + 92 * math.cos(ang), cy - 10 + 92 * math.sin(ang)
        x1, y1 = cx + r1 * math.cos(ang), cy - 10 + r1 * math.sin(ang)
        a = ray_alpha
        if FB37_RAYS and FB37_MIRROR:
            a = int(ray_alpha * (1.22 if math.cos(ang) < 0 else 0.85))  # 左亮右暗偏置
        d.line([(x0, y0), (x1, y1)], fill=ray_c + (max(0, min(255, a)),),
               width=6 if FB37_RAYS else 4)

    # ---- 全章网点抖动（垫在主体之下，只做底场质感）----
    tile = _halftone_tile(period=4, dot=2.0,
                          color=(120, 90, 60) if tone == "stamp" else
                          ((16, 19, 24) if tone != "gold" else (120, 100, 62)),
                          alpha=70 if tone != "gold" else 78, offset=False)
    tile_l = _halftone_tile(period=4, dot=1.0,
                            color=(226, 232, 238) if tone != "gold" else (255, 246, 220),
                            alpha=30)
    tw, th2 = tile.size
    big = Image.new("RGBA", (CW, CH))
    for yy in range(0, CH, th2):
        for xx in range(0, CW, tw):
            big.paste(tile, (xx, yy), tile)
    canvas.alpha_composite(big)

    # 亮点层（网点对偶，stipple 更完整）
    tw2, th3 = tile_l.size
    big2 = Image.new("RGBA", (CW, CH))
    for yy in range(0, CH, th3):
        for xx in range(0, CW, tw2):
            big2.paste(tile_l, (xx, yy), tile_l)
    canvas.alpha_composite(big2)

    # ---- 边缘暗角（金属冲压的深度感）----
    yy_, xx_ = np.mgrid[0:CH, 0:CW].astype(np.float32)
    dist = np.sqrt((xx_ - cx) ** 2 + (yy_ - cy) ** 2)
    vig_a = np.clip((dist - apothem * 0.50) / (apothem * 0.50), 0, 1) * 60
    vig = Image.new("RGBA", (CW, CH), (10, 13, 18, 255))
    vig.putalpha(Image.fromarray(vig_a.astype(np.uint8), "L"))
    canvas.alpha_composite(vig)
    # ---- 细颗粒（哑光金属微噪；幅度收小保持网点阵列规整）----
    rng_g = np.random.default_rng(13)
    n_g = rng_g.integers(-3, 4, (CH, CW, 1), dtype=np.int16)
    arr_g = np.asarray(canvas.convert("RGB"), dtype=np.int16) + n_g
    grain = Image.fromarray(np.clip(arr_g, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    grain.putalpha(canvas.getchannel("A"))
    canvas = grain
    # ---- 极轻冷蓝偏光（金属冷色泛光，非光泽）----
    sheen = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ds2 = ImageDraw.Draw(sheen)
    for i in range(-CW, CW, 260):
        ds2.line([(i, CH), (i + CH, 0)], fill=(205, 222, 240, 12), width=60)
    sheen = sheen.filter(ImageFilter.GaussianBlur(26))
    canvas.alpha_composite(sheen)
    d = ImageDraw.Draw(canvas)

    # ---- 中央纹章（照片主体蚀刻像，满版占比）----
    f = face.copy()
    fr = min(650 / max(f.size), 1.0)
    f = f.resize((max(1, int(f.width * fr)), max(1, int(f.height * fr))), Image.LANCZOS)
    fx0, fy0 = cx - f.width // 2, cy - f.height // 2 - 40
    # 主体底衬：仅在"整图回退"（全不透明矩形）时铺场色垫底；
    # 设计纹章路径不垫板——让章体放射纹/网点正常从纹章镂空处透出
    fa_min = f.getchannel("A").getextrema()[0]
    if fa_min > 200:
        fld_top, fld_bot = FIELD_COLORS.get(
            "gold" if tone == "gold" else ("plated" if tone == "plated" else
                                           ("stamp" if tone == "stamp" else "silver")),
            ((235, 228, 214), (216, 208, 190)))
        fld_mid = tuple(int((fld_top[i] + fld_bot[i]) // 2) for i in range(3)) + (255,)
        pad = 10
        backing = Image.new("RGBA", (f.width + pad * 2, f.height + pad * 2), (0, 0, 0, 0))
        ImageDraw.Draw(backing).rounded_rectangle(
            [0, 0, backing.width - 1, backing.height - 1],
            radius=max(28, int(min(f.size) * 0.10)), fill=fld_mid)
        canvas.alpha_composite(backing, (fx0 - pad, fy0 - pad))
    outline_col = (38, 45, 53, 235) if tone != "gold" else (104, 76, 30, 235)
    edge_a = _edge_alpha(f, gain=1.7).point(lambda v: min(v, 220))
    ol = Image.new("RGBA", f.size, outline_col)
    canvas.paste(ol, (fx0, fy0), edge_a)
    canvas.alpha_composite(f, (fx0, fy0))
    if FB37_DARK and tone in ("gold", "silver"):
        # 环形文字（官方 E6）：装饰假字符沿内框弧排布（固定 seed，非对称错落）
        ring_chars = "ALRKAZWUVDKRAL" * 2
        ring_font = load_font(FONT_EN_BLACK or FONT_EN_ROUND or FONT_CN, 26)
        d.polygon(_hex_pts(cx, cy - 40, R - 122), outline=line_hi + (110,), width=2)
        d.polygon(_hex_pts(cx, cy - 40, R - 178), outline=line_hi + (90,), width=2)
        _ring_text(canvas, cx, cy - 40, R - 150, ring_chars, ring_font,
                   line_hi + (210,), 0.0, 360.0, jitter=4, seed=11)
    if FB37_SEAT:
        # 纹章座圈：围绕纹章外缘的双环（官方中心区环栈词汇；升级为主攻，见 findings §6）
        seat_r = max(f.width, f.height) * 0.56
        for sr, sw, sc, sa in ((seat_r, 11, line_hi, 255),
                               (seat_r + 26, 4, line_hi, 210)):
            d.polygon(_hex_pts(cx, cy - 40, sr), outline=sc + (sa,), width=sw)
        for i in range(24):
            ang = math.radians(i * 15)
            sr = seat_r + 13
            d.ellipse([cx - 40 + sr * math.cos(ang) - 3, cy - 40 + sr * math.sin(ang) - 3,
                       cx - 40 + sr * math.cos(ang) + 3, cy - 40 + sr * math.sin(ang) + 3],
                      fill=line_hi + (230,))

    if tone == "plated":
        # 虹彩只附着在两处：主体轮廓缘 + 边框环带（严格随形）
        face_edge = _edge_alpha(f, gain=2.6)
        face_mask = Image.new("L", (CW, CH), 0)
        face_mask.paste(face_edge, (fx0, fy0))
        rim_band = Image.new("L", (CW, CH), 0)
        ImageDraw.Draw(rim_band).polygon(_hex_pts(cx, cy, R - 8), outline=255, width=30)
        combined = Image.fromarray(np.maximum(np.asarray(rim_band),
                                              np.asarray(face_mask)).astype(np.uint8), "L")
        canvas.alpha_composite(_iridescent_overlay((CW, CH), alpha=110,
                                                   edge_mask=combined))

    # 把网点等效果裁回六边形内（保持透明外沿干净）
    clean = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    clean.paste(canvas, (0, 0), hex_mask)
    canvas = clean
    d = ImageDraw.Draw(canvas)

    # 重画最外圈描边保证边缘锐利
    d.polygon(_hex_pts(cx, cy, R), outline=line_hi + (255,), width=3)

    # ---- 嵌入式文字（与纹章同层的横字带，非外贴铭牌）----
    f_en = load_font(FONT_EN_BLACK or FONT_CN, 50)
    f_cn = load_font(FONT_CN, 54)
    f_cn_bold = load_font(FONT_CN_BOLD, 54)
    f_tag = load_font(FONT_EN_BLACK or FONT_MONO or FONT_CN, 23)

    if tone == "gold":
        # 浅乳白底上用深铜金文字
        txt_col = (96, 72, 28, 255)
        tag_col = (140, 106, 44, 240)
        band_bg = (255, 250, 236, 170)
        band_bd = line_mid + (230,)
        top_bg = (250, 244, 226, 150)
    elif tone == "stamp":
        # 朱红纸面印文
        txt_col = (150, 48, 26, 255)
        tag_col = (178, 62, 36, 240)
        band_bg = (255, 252, 246, 165)
        band_bd = line_mid + (230,)
        top_bg = (250, 244, 234, 150)
    else:
        txt_col = line_hi + (255,)
        tag_col = line_hi + (235,)
        band_bg = (52, 62, 72, 200) if tone != "plated" else (56, 66, 76, 200)
        band_bd = line_mid + (220,)
        top_bg = (46, 55, 64, 170)

    # 底部缎带字带（端部收角 + 双细线 + 压印阴影，文字长在章体里）
    bw = min(int(_hex_halfwidth(R, 292) * 2 * (0.86 if FB37_BAND else 0.92)), 500)
    bh = 72 if FB37_BAND else 84
    by = cy + 292 - bh // 2
    notch = 22
    band_pts = [(cx - bw // 2 + notch, by), (cx + bw // 2 - notch, by),
                (cx + bw // 2, by + bh // 2), (cx + bw // 2 - notch, by + bh),
                (cx - bw // 2 + notch, by + bh), (cx - bw // 2, by + bh // 2)]
    d.polygon([(x + 3, y + 4) for x, y in band_pts],
              fill=(8, 10, 14, 120) if tone != "gold" else (110, 80, 30, 110))
    d.polygon(band_pts, fill=band_bg, outline=band_bd, width=3)
    rule_col = band_bd[:3] + (150,)
    d.line([(cx - bw // 2 + notch + 12, by + 12), (cx + bw // 2 - notch - 12, by + 12)],
           fill=rule_col, width=2)
    d.line([(cx - bw // 2 + notch + 12, by + bh - 12), (cx + bw // 2 - notch - 12, by + bh - 12)],
           fill=rule_col, width=2)
    # 菱形分隔符
    for dx2 in (-bw // 2 + notch + 3, bw // 2 - notch - 3):
        dd_ = 7
        d.polygon([(cx + dx2, by + bh // 2 - dd_), (cx + dx2 + dd_, by + bh // 2),
                   (cx + dx2, by + bh // 2 + dd_), (cx + dx2 - dd_, by + bh // 2)],
                  fill=band_bd[:3] + (200,))
    label = text if not number else f"{text} · {number}"
    font_main = f_en if all(ord(c) < 128 for c in label) else f_cn_bold
    while (sum(d.textlength(c, font=font_main) for c in label)
           + 6 * (len(label) - 1)) > bw - 76 and len(label) > 2:
        label = label[:-1]
    sh_c = (0, 0, 0, 130) if tone != "gold" else (120, 92, 40, 120)
    draw_tracked_text(d, label, cx, by + bh / 2, font_main, txt_col,
                      tracking=6, shadow=sh_c)

    # 顶部窄框标签：副文本或编号（字距跟踪 + 精确居中 + 端部菱形饰）
    top_label = subtitle or serial or ""
    if top_label:
        top_label = top_label.upper() if all(ord(c) < 128 for c in top_label) else top_label
        hw_top = _hex_halfwidth(R, 372)
        tbw = min(int(hw_top * 2 * 0.9), 460)
        tbh = 46
        tby = cy - 372 - tbh // 2
        d.rounded_rectangle([cx - tbw // 2, tby, cx + tbw // 2, tby + tbh], radius=9,
                            fill=top_bg, outline=line_mid + (190,), width=2)
        ft = f_tag
        while (sum(d.textlength(c, font=ft) for c in top_label)
               + 3 * (len(top_label) - 1)) > tbw - 40 and len(top_label) > 2:
            top_label = top_label[:-1]
        for dx2 in (-tbw // 2 + 6, tbw // 2 - 6):
            dd_ = 5
            d.polygon([(cx + dx2, tby + tbh // 2 - dd_), (cx + dx2 + dd_, tby + tbh // 2),
                       (cx + dx2, tby + tbh // 2 + dd_), (cx + dx2 - dd_, tby + tbh // 2)],
                      fill=line_mid + (200,))
        draw_tracked_text(d, top_label, cx, tby + tbh / 2, ft, tag_col, tracking=3)

    return canvas


# ----------------------------------------------------------------------------
# 四、终末地模板 v11（依据 2026-09 游戏内截图考据，DESIGN_SPEC v2 §七：
#     品阶 = 银/金/深灰排名/虹彩珠光镀层；形制家族 = story 剧情陈列 / combat 计数；
#     共通元素：角部工程注记、顶部铭牌框、底部接口触点、网点渐隐、拉丝渐变）
# ----------------------------------------------------------------------------

# 终末地品阶场色（渐变 stops，沿拉丝轴）与蚀刻色
EF_TONE_V2 = {  # 色值取自 2026-09 游戏内截图程序化采样（见 MATERIAL_INDEX）
    "ef_silver": {  # 停点取自 2026-09 的色场采样（旧 v2 深冷灰档 lum≈80）。
                   # 装饰四层（描边/网点/角部注记/铭牌面板）**不再**由这三个停点线性派生，
                   # 改读 ef_layer_measured.json 的实测色（已知答案自证过）；
                   # 现在它们只驱动章面底色场与 `_metal_ramp` 兜底路径。
        "field": [(70, 74, 78), (94, 96, 97), (52, 58, 62)],
        "band": (190, 194, 198),
        "engrave": (238, 238, 236),
        "accent": (111, 184, 168),
    },
    "ef_gold_pure": {  # 纯金（剧情金章）：R-12 原色直采网格（resample_goldpure.py）p8/p50/p92
        "field": [(100, 63, 25), (141, 103, 36), (239, 230, 181)],
        "band": (250, 245, 220),
        "engrave": (252, 250, 240),
        # (200,40,50) 是无出处的自造红：官方金章 3× 放大目检全幅无红。
        "accent": (170, 134, 52),
    },
    "ef_gold": {   # 实测 顶#DCD38E 侧#DC6107(亮橙) 底#98B020(黄绿)
        "field": [(220, 97, 7), (220, 211, 142), (152, 176, 32)],
        "band": (250, 245, 220),
        "engrave": (250, 247, 235),
        # 同上，红是造的；这里吃 showcase/gold 的实测暗笔画色。
        "accent": (170, 134, 52),
    },
    "ef_dark": {   # R-9 重采（153730 武陵工业先驱·I 20×24，resample_dark.py）p8/p50/p92
        "field": [(63, 64, 60), (66, 66, 66), (66, 67, 71)],   # R-13 场区压暗对齐官方（d0.5=67）
        "band": (140, 143, 145),
        "engrave": (240, 240, 238),
        "accent": (200, 202, 204),
    },
    "ef_bronze": {  # 铜阶：与 dark 共场（面板计数 铜14=深灰观感），无 #N 角标；点缀取铜色
        "field": [(63, 64, 60), (66, 66, 66), (66, 67, 71)],   # R-13 场区压暗对齐官方（d0.5=67）
        "band": (140, 143, 145),
        "engrave": (240, 240, 238),
        "accent": (196, 130, 72),
    },
    "ef_pearl": {  # 实测 上#BBC2B1 侧#CDC2BC
        "field": [(203, 194, 188), (228, 226, 214), (196, 210, 202)],
        "band": (250, 250, 250),
        "engrave": (52, 56, 60),
        "accent": (150, 186, 172),
    },
}


_EF_GRIDS = None


def _ef_grids():
    """采样自游戏内截图的 2D 色场网格（engine/ef_field_grids.json，8×9 控制点）"""
    global _EF_GRIDS
    if _EF_GRIDS is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ef_field_grids.json")
        with open(p, encoding="utf-8") as f:
            _EF_GRIDS = json.load(f)
    return _EF_GRIDS


def _metal_field(arr):
    """把采样网格投影成「纯金属渐变」：保留亮度结构，色度取全表中位。

    素材页里金章与彩色「奇想奖章」混排，采样网格因此夹带橙/绿控制点
    （gold 表末行 (149,204,23)、(247,108,7)），插值后章面渲成日落色斑块。
    金属章的色相由色板决定，不该由页面上邻座的彩绘章决定。
    """
    import colorsys
    a = np.asarray(arr, dtype=np.float32) / 255.0
    h, w, _ = a.shape
    lum = 0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]
    flat = a.reshape(-1, 3)
    med = np.median(flat, axis=0)
    mh, ms, _mv = colorsys.rgb_to_hsv(*[float(c) for c in med])
    # 采样网格是页面上「一枚枚章的中位色」，章与章之间互相抵消掉了单枚章内部的明暗坡道
    # ⇒ 直接插值出来的场是平的（旧稿渲出来像一张卡纸）。按中位明度把坡道拉开，
    # 拉开量随档位自身亮度缩放，深灰章不会被抬成银章。
    m = float(np.median(lum))
    spread = max(m - float(np.percentile(lum, 4)), float(np.percentile(lum, 96)) - m, 1e-3)
    gain = min(2.6, max(0.16, min(0.30, 0.62 * m)) / spread)
    out = np.empty_like(a)
    for y in range(h):
        for x in range(w):
            l = float(np.clip(m + (lum[y, x] - m) * gain, 0.04, 0.99))
            # 金属受光提亮时同时去饱和：恒定饱和的 HSV 坡道渲出来是塑料黄，
            # 素材侧高光区是乳白（(240,232,185)，S≈0.23）而非纯黄。
            s = ms * (1.0 - 0.72 * np.clip((l - 0.58) / 0.41, 0.0, 1.0))
            out[y, x] = colorsys.hsv_to_rgb(mh, float(s), l)
    return np.clip(out * 255.0, 0, 255).astype(np.uint8)


_HW_DARK_CACHE = {}


def _ef_grid_key(tone):
    key = tone[3:] if tone.startswith("ef_") else tone   # ef_gold -> gold
    return {"bronze": "dark"}.get(key, key)              # 铜阶与排名章共用场网格


def _hw_metal_dark(tone, q=8.0):
    """五金件暗端配色：只许从**去彩绘后的章面金属**取色。

    旧值 `EF_TONE_V2[tone]["field"][0]` 的 ef_gold 那格是 (220,97,7) 亮橙（sat 0.968）—— 2026-09 采样时
    把页面上邻座彩绘章的侧色当成了金章侧色，而官方金章四格实测饱和橙占比 0.00000。`_metal_field()` 已把
    色度压到全表中位 ⇒ 从它的暗端取色，结构上渲不出章面本身没有的色相。
    """
    key = _ef_grid_key(tone)
    ck = (key, q)
    v = _HW_DARK_CACHE.get(ck)
    if v is None:
        g = _ef_grids().get(key)
        if not g:
            v = (60, 62, 66)
        else:
            a = np.asarray(_metal_field(np.asarray(g, dtype=np.uint8)),
                           dtype=np.float32) / 255.0
            flat = a.reshape(-1, 3)
            lum = flat.mean(1)
            row = flat[int(np.argmin(np.abs(lum - float(np.percentile(lum, q)))))]
            v = tuple(int(round(float(c) * 255.0)) for c in row)
        _HW_DARK_CACHE[ck] = v
    return v


def _hsv_sat_boost(field, s_mult, s_lift, edge_gain, CW, CH, cx, cy, R):
    """HSV 空间饱和增强：色相严格保持（RGB-mean 法在 g>r>b 非对称像元上会把 hue 压向黄）。
    s_mult 饱和乘数 / s_lift 饱和抬升 / edge_gain 边缘附加。输入输出均为 RGBA Image。"""
    import math as _math
    _f = np.asarray(field.convert("RGB"), dtype=np.float32) / 255.0
    _mx = _f.max(-1); _mn = _f.min(-1); _d = np.maximum(_mx - _mn, 1e-6)
    _h = np.where(_mx == _f[..., 0], (60 * ((_f[..., 1] - _f[..., 2]) / _d)) % 360,
          np.where(_mx == _f[..., 1], 60 * ((_f[..., 2] - _f[..., 0]) / _d) + 120,
                   60 * ((_f[..., 0] - _f[..., 1]) / _d) + 240))
    _s = np.where(_mx > 0, _d / np.maximum(_mx, 1e-6), 0)
    _neargray = _s < 0.08   # 近灰像元：hue 除零不稳定 ⇒ 跳过增强保留原色（珠光白基底防花）
    _yyg, _xxg = np.mgrid[0:field.height, 0:field.width].astype(np.float32)
    _edge = np.clip(np.sqrt(((_xxg - cx) / (R * 0.98)) ** 2 +
                            ((_yyg - cy) / (R * 1.08)) ** 2), 0, 1.15) ** 1.6
    _s2 = np.clip(_s * s_mult + s_lift * _edge, 0, 1.0)
    _v2 = np.clip(_mx * (1.0 + 0.05 * edge_gain * _edge), 0, 1.0)
    _d2 = _s2 * _v2; _m2 = _v2 - _d2
    _hx = _h / 60.0
    _i = np.floor(_hx).astype(int) % 6
    _f2 = _d2 * (1 - np.abs(_hx % 2 - 1))
    # 标准 HSV→RGB：max 通道 = _v2（value），中通道 = _m2+_f2，min 通道 = _m2
    # （旧表误用 _d2（色度）占 _v2 位 ⇒ 输出整体塌暗，珠光右半黑块根因）
    _rr = np.select([_i == 0, _i == 1, _i == 2, _i == 3, _i == 4, _i == 5],
                    [_v2, _m2 + _f2, _m2, _m2, _m2 + _f2, _v2])
    _gg = np.select([_i == 0, _i == 1, _i == 2, _i == 3, _i == 4, _i == 5],
                    [_m2 + _f2, _v2, _v2, _m2 + _f2, _m2, _m2])
    _bb = np.select([_i == 0, _i == 1, _i == 2, _i == 3, _i == 4, _i == 5],
                    [_m2, _m2, _m2 + _f2, _v2, _v2, _m2 + _f2])
    _rgb = np.stack([_rr, _gg, _bb], -1)
    _orig = (_f * 255.0)
    _rgb = np.where(_neargray[..., None], _orig, _rgb * 255.0)   # 近灰保留原色(0-255)；增强分支同步 ×255（0-1 混尺会整片变黑）
    return Image.fromarray((np.clip(_rgb, 0, 255)).astype(np.uint8), "RGB").convert("RGBA")


def _ef_field(tone, CW, CH):
    """网格 → 双三次插值的非对称色场（多方向渐变 1:1 复刻素材）"""
    key = _ef_grid_key(tone)
    g = _ef_grids().get(key)
    if not g:
        return None
    arr = np.asarray(g, dtype=np.uint8)
    # 珠光/炫彩的虹彩是设计意图，色度原样保留；其余档一律走纯金属渐变
    if key not in ("pearl", "pearl_blobs", "irid"):
        arr = _metal_field(arr)
    # 去团斑：网格先高斯平滑（单元格中值受纹章遮挡扰动，平滑保留渐变趋势、消除色斑）
    m = max(arr.shape[0], arr.shape[1])
    # 平滑分档：粗网格重抹去团斑；超细网格在采样端已 σ2.2 格平滑，这里只轻抹去残噪
    sigma = 1.1 if m <= 16 else (0.7 if m <= 24 else (0.9 if m <= 48 else 0.55))
    # 行间中值平滑：74×86 等高密度网格的行采样偏差会形成水平条带
    if m > 48:
        _flt = np.asarray(arr, dtype=np.float32).copy()
        for r in range(1, arr.shape[0] - 1):
            _flt[r] = (arr[r-1] + arr[r] * 2 + arr[r+1]) / 4.0
        arr = np.clip(_flt, 0, 255).astype(np.uint8)
    smooth = Image.fromarray(arr, "RGB").filter(ImageFilter.GaussianBlur(sigma))
    arr = np.asarray(smooth)
    # 边缘保持：首末行列各复制一次，防止插值把素材的陡峭边缘色带稀释
    arr = np.concatenate([arr[:, :1], arr, arr[:, -1:]], axis=1)
    arr = np.concatenate([arr[:1], arr, arr[-1:]], axis=0)
    small = Image.fromarray(arr, "RGB")
    # 场级扩散模糊：素材的虹彩是"色块自然扩散+模糊过渡"，插值噪声则呈条状——
    # 上采样后做一次与色块尺度相当的低通，复刻素材的柔和扩散
    field = small.resize((CW, CH), Image.BICUBIC)
    blur_px = {"ef_pearl": 48}.get(tone, 20)
    return field.filter(ImageFilter.GaussianBlur(blur_px))


_EF_LAYERS = None


def _ef_layers():
    """装饰四层实测色（engine/ef_layer_measured.json，由本地量测脚本生成、不随包发布）

    缺品阶/缺组/缺层一律 raise：兜底默认值会把「漏登记」变成静默错档（纪律 ⑨）。
    """
    global _EF_LAYERS
    if _EF_LAYERS is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ef_layer_measured.json")
        with open(p, encoding="utf-8") as f:
            _EF_LAYERS = json.load(f)
    return _EF_LAYERS


def _ef_group(tone):
    """该品阶借用的素材组（`meta.render_tone`，与量测口径同一张表）"""
    L = _ef_layers()
    key = tone[3:] if tone.startswith("ef_") else tone
    grp = L["meta"]["render_tone"].get(key)
    if grp is None or grp not in L["groups"]:
        raise KeyError(f"ef_layer_measured: 品阶 {tone} 的素材组 {grp!r} 未登记")
    return L["groups"][grp]


_EF_FEED_LAYERS = ("plate", "corner", "lowdot")   # 这三层按笔画极性判定决定喂不喂


def _ef_fed(tone, layer):
    """这一层这一组**有没有实测可喂**：装饰三层判为不可单常数化/仪器不可见时
    `feed_rgb` 是 null ⇒ 返回 None（调用方保持现常数，并据此知道「这次不是照实喂的」）。
    描边/章面/环带没有极性之争，`rgb` 就是实测值。
    """
    e = _ef_group(tone).get(layer)
    if e is None:
        raise KeyError(f"ef_layer_measured: 缺层 {layer}")
    if layer in _EF_FEED_LAYERS:
        return tuple(e["feed_rgb"]) if e.get("feed_rgb") else None
    return tuple(e["rgb"])


def _ef_measured(tone, layer, fallback=None):
    """一层实测色的绝对 RGB；`_ef_fed` 为 None 时返回 fallback"""
    return _ef_fed(tone, layer) or fallback


def _ef_plate_lift(tone):
    """铭牌面板**这块区域**的去梯度电平（plate − 同高两侧金属）。

    素材 6 组里 5 组判 `flat`（|d_ref| 落进空读数 +0.016 内）⇒ 返回
    None = 面板与周围金属齐平，不许提亮；只有 `lift` 才返回偏移量。
    """
    p = _ef_group(tone)["plate"]
    return p["d_ref"] if p.get("d_ref_verdict") == "lift" else None


def _ef_corner_delta(tone):
    """corner 层的素材**反差** `Δ = feed_rgb − base_rgb`（相对电平喂法）

    旧写法把素材的**绝对**笔画色直接搬到我们的章面上，而素材那块地皮比我们的亮
    （silver 素材底 213 vs 我们 163.6）⇒ 落地深度只剩素材的 11%（现跑 −6.3 / −56.1）。
    改成搬「比脚下暗多少」：两个端点都在实测表里 ⇒ 没有新造常数。
    未喂色的组返回 None ⇒ 调用方改走 `_ef_corner_fallback_delta`：
    「按绝对色兜底」那条支自本笔退出渲染路径。
    """
    e = _ef_group(tone).get("corner")
    if e is None:
        raise KeyError("ef_layer_measured: 缺层 corner")
    if not e.get("feed_rgb"):
        return None
    if not e.get("base_rgb"):
        raise KeyError("ef_layer_measured: corner 喂了色却没有 base_rgb ⇒ 反差无从算起")
    return tuple(int(f) - int(b) for f, b in zip(e["feed_rgb"], e["base_rgb"]))


def _ef_annot_font(size=13):
    """注记字体：与 `ef_layer_geom._corner_font()` 同一支、同一字号（掩膜与落笔同底）"""
    return load_font(FONT_MONO or FONT_EN_BLACK or FONT_CN, size or 14)


def _ef_annot_bg(rgb_arr, keep_arr, x, y, text, font):
    """一条注记**落笔之前**脚下那圈环带的逐通道中位 RGB（「局部背景」）

    墨迹用与 `_ef_corner_annotation` 同一支字体、同一锚点画出来，环带几何走
    `ef_layer_geom.annot_ring`（= 深度尺读的那张圈）。`keep_arr` = 章体掩膜：画布到这一段
    已铺满不透明 alpha，章体外是黑底，不剔掉环带中位就被黑边拉偏。
    环带像元不足（计划里深度尺的同一条线 = 50）一律 raise，不许静默退回绝对色。
    """
    ink = Image.new("L", (rgb_arr.shape[1], rgb_arr.shape[0]), 0)
    ImageDraw.Draw(ink).text((x, y), text, font=font, fill=255)
    ring = _ef_annot_ring(np.asarray(ink) > 127) & keep_arr
    px = rgb_arr[ring]
    if len(px) < 50:
        raise ValueError("注记 %r 的背景环带只剩 %d 像元 ⇒ 局部电平取不到，不许兜底"
                         % (text, len(px)))
    return tuple(float(v) for v in np.median(px, axis=0))


def _ef_corner_fallback_delta(tone):
    """兜底支（借用组未喂色）的反差 Δ —— c_dark×255 三通道同减的那条式子。

    素材侧「笔画比脚下暗多少」在实测表里只有 `corner.c_dark` 一个 luma 数，
    ×255 换成灰阶、三通道同减 ⇒ 零新字面 RGB。近似代价（饱和微升）已实测。
    乘式（`base_rgb × c_dark`）没被实测验过 ⇒ 明文不用。
    喂了色的组返回 None ⇒ 调用方走 `_ef_corner_delta`；两条都拿不到时**不许**退回绝对色。
    """
    e = _ef_group(tone).get("corner")
    if e is None:
        raise KeyError("ef_layer_measured: 缺层 corner")
    if e.get("feed_rgb"):
        return None
    cd = e.get("c_dark")
    if cd is None:
        raise KeyError(f"ef_layer_measured: 品阶 {tone} 的借用组未喂色又没有 c_dark "
                       "⇒ 兜底电平无从取得，不许静默退回 engrave 绝对色")
    d = int(round(float(cd) * 255))
    return (d, d, d)


def _ef_corner_rel(bg, delta):
    """落笔色 `S = clip(局部背景 + Δ, 0, 255)`（四舍五入后取整，与网页同口径）"""
    return tuple(int(max(0, min(255, round(b + d)))) for b, d in zip(bg, delta))


def _ef_corner_annotation(d, x, y, text, color, size=13):
    """角部工程注记：如 +001-E-1908 / ×××/＋｜ 式散布符号"""
    f = _ef_annot_font(size)
    d.text((x, y), text, font=f, fill=color + (235,))


def _ef_ports(d, cx, bottom_y, color):
    """底部接口触点：两颗螺丝孔 + 一条触点条"""
    for dx in (-52, 52):
        d.ellipse([cx + dx - 7, bottom_y - 7, cx + dx + 7, bottom_y + 7],
                  outline=color + (200,), width=3)
    d.rounded_rectangle([cx - 26, bottom_y + 12, cx + 26, bottom_y + 24], radius=6,
                        fill=color + (90,))


def _ef_industry_hardware(d, cx, cy, R, outline, engrave, tp, tone):
    """industry 家族五金件（素材 153730 复核修正：章体为正六边形，无切角无挂耳）：
    左上圆盘表扣 + 贴边侧接口 + 角区内六角螺丝 + 底部双箭 + L 形角码"""
    # 暗端一律从「去彩绘后的章面金属」取，禁止吃 tp["field"][0]
    # （ef_gold 那格 (220,97,7) 是 2026-09 采样时邻座彩绘章的侧色，官方金章饱和橙占比实测 0.00000）。
    f_dark = _hw_metal_dark(tone)
    # ---- 左上圆盘：蚀刻在金属里的盘（盘内不整盘填色，露章面自身金属）----
    px, py = cx - int(R * 0.42), cy - int(R * 0.26)
    pr = int(R * 0.16)
    d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=None,
              outline=f_dark + (255,), width=10)
    ir = int(pr * 0.72)
    d.ellipse([px - ir, py - ir, px + ir, py + ir], outline=engrave + (120,), width=2)
    for k in (-2, -1, 0, 1, 2):     # 盘内排线（蚀刻语言：亮线压在金属底上，不是白贴纸）
        off = k * int(pr * 0.22)
        half = int(max(0, math.sqrt(max(pr * pr - off * off, 0))) * 0.82)
        d.line([(px - half, py + off + half // 3), (px + half, py + off - half // 3)],
               fill=engrave + (165,), width=3)
    d.polygon([(px - ir // 2, py + ir // 2), (px + ir // 3, py + ir // 6),
               (px + ir // 2, py + ir // 2)], fill=tp["band"] + (215,))
    for tx in (-8, 8):       # 顶部双刻度
        d.line([(px + tx, py - pr - 12), (px + tx, py - pr + 2)], fill=outline, width=4)
    # ---- 侧边接口（左右贴边内嵌矩形接插件，不凸出六边形轮廓）----
    for sx in (-1, 1):
        sx0 = cx + sx * int(R * 0.865)
        x0 = sx0 - 24 if sx > 0 else sx0
        d.rounded_rectangle([x0, cy - 26, x0 + 24, cy + 26], radius=5,
                            fill=f_dark + (235,), outline=outline, width=3)
        d.line([(x0 + 8, cy - 14), (x0 + 8, cy + 14)], fill=engrave + (140,), width=2)
    # ---- 角区内六角螺丝（右上/左下区）----
    for sx, sy in ((1, -1), (-1, 1)):
        bx, by = cx + sx * int(R * 0.70), cy + sy * int(R * 0.60)
        d.polygon(_hex_pts(bx, by, 12, rot_deg=30), fill=f_dark + (200,), outline=outline, width=3)
        d.ellipse([bx - 4, by - 4, bx + 4, by + 4], fill=(18, 20, 22, 255))
    # ---- 底部双箭形接口（深色三角楔块 + 内描线，位于底部两侧斜边上）----
    for sx in (-1, 1):
        ax, ay = cx + sx * int(R * 0.52), cy + int(R * 0.62)
        d.polygon([(ax - 26, ay - 14), (ax + 26, ay - 14), (ax, ay + 22)],
                  fill=f_dark + (235,), outline=outline, width=3)
        d.line([(ax - 14, ay - 8), (ax, ay + 10)], fill=engrave + (150,), width=2)
        d.line([(ax + 14, ay - 8), (ax, ay + 10)], fill=engrave + (150,), width=2)
    # ---- L 形角码（内角轻量标记）----
    L = 34
    for sx, sy in ((1, -1), (-1, -1), (1, 1), (-1, 1)):
        bx, by = cx + sx * int(R * 0.74), cy + sy * int(R * 0.78)
        d.line([(bx, by), (bx - sx * L, by)], fill=engrave + (110,), width=3)
        d.line([(bx, by), (bx, by - sy * L)], fill=engrave + (110,), width=3)
    # ---- 右上环形进度弧（半透明 accent，素材右上角圆弧）----
    ar = int(R * 0.66)
    d.arc([cx - ar, cy - ar, cx + ar, cy + ar], start=-85, end=-15,
          fill=tp["accent"] + (60,), width=5)


def _ef_nameplate(d, cx, cy, R, outline, field_mid, tone="ef_gold_pure"):
    """顶部铭牌框 v2：车牌式圆角矩形 + 四角铆钉 + 顶点空心三角指示
    几何按素材实测（154413/153659 放大 3 倍测量，×2.9 映射到 R=470 画布）：
    板宽 ≈ 0.21×章宽(168px)、高 ≈ 99px、板顶距顶点 ≈ 72px、描边 ≈ 6px、
    四角铆钉空心小圆 r≈8、空心三角宽 30×高 42 于顶点。
    **落笔坐标取自 `engine/ef_layer_geom.py` 的 `PLATE`（单一事实源，纪律 ⑬）**：
    量测要按同一张表算「笔画有没有活进检测 bin」，写死在这里就会两边各说各话。"""
    p = EF_PLATE
    x0, y0, x1, y1 = cx + p["dx0"], cy + p["dy0"], cx + p["dx1"], cy + p["dy1"]
    # 面板**这块区域**的电平走实测 `d_ref`（plate − 同高两侧金属，去打光梯度）：素材 6 组
    # 里 5 组判 `flat` ⇒ 只画框和铆钉、不填色（旧值 `field_mid+(60,)` 与奶油色 (244,236,200)
    # 都是手设提亮，无素材依据）。面板里的刻字另走笔画极性判定，六组全是不可单常数化 ⇒ 保持现值。
    lift = _ef_plate_lift(tone)
    d.rounded_rectangle([x0, y0, x1, y1], radius=p["radius"],
                        fill=None if lift is None
                        else tuple(int(round(c * (1.0 + lift))) for c in field_mid) + (60,),
                        outline=outline, width=p["stroke"])
    # 四角铆钉（小实心点，对照素材）
    half_w, half_h = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    ins, rr = p["rivet_inset"], p["rivet_r"]
    for sx in (-1, 1):
        for sy in (-1, 1):
            rx = cx + sx * (half_w - ins)
            ry = y0 + half_h + sy * (half_h - ins)
            d.ellipse([rx - rr, ry - rr, rx + rr, ry + rr], fill=outline)
    # 顶点空心三角指示
    aw = p["tri_half_w"]
    apex = cy + p["apex_dy"]
    tri = [(cx, apex), (cx - aw, apex + p["tri_h"]), (cx + aw, apex + p["tri_h"])]
    d.polygon(tri, outline=outline, width=p["tri_width"])



# ---- TB-31 纯金档方向打光（EF38；跨度 0 = 不接线，逐字节回退）----
# 定档以官方纯金章面实测为准。
# 场形改口（纯金方位打光回归）：
# 原两侧均值归一形制会把已经亮的顶端整体抬过 8-bit 顶 ⇒ 坡被挤出可见量程；现形制单侧、
# 亮端锚定（t=1 严格 ×1.00），坡全部由暗端变暗长出来，且行程归一到章面自身的支撑区间。
# TB-33 R-6 装饰落笔门（用户点名「右上角多出了错误的深棕色线条和方框」）：官方靶 3× 目检
# （tb33_off_tight_x3.png）显示金系几何词汇在**受光侧**一律是奶白浅笔，暗笔只出现在**背光侧的
# 空金属**上 ⇒ 旧注释「深色斜纹 = 金系官方词汇」是错靶产物，予以作废。GATE=0 时逐字节回退。
# TB-33 R-5 加轴（尺 tb33_r4e v2 / tb33_r4f v1 现读）：亮端锚定使 `light4 ≤ 1` 恒成立 ⇒
# 「贴角比今日更亮」在原乘性形制内**不可表示**（r7a 量程尺 D-c 证实：tt=1 处 light4 ≡ 1.0，
# 全池顶带 med 恒 206.9，LUX/EXP 结构上抬不动亮端）。OV = 贴角过冲：tt 越过 KNEE 后线性加到
# ×(1+OV)，KNEE 以下恒等 ⇒ OV=0 时表达式逐字回到 R-4 形制（逐字节回退闸可验）。
# TB-33 R-6 换机制（尺 tb33_r5c/r5d/r5e 现读）：乘子族画不出「角上继续变亮 + 转奶白」，
# screen 向白有界加亮 ⇒ 不撞 255 顶、越亮越脱饱和（官方奶白同型）。
EF38_GOLD_LUX = _envf("MEDAL_EF38_GOLD_LUX", 0.78)   # 亮/暗电平比（顶端恒 ×1.00，底端 ×1/LUX；1.0 = 无梯度，0 = 不接线）
EF38_GOLD_DEG = _envf("MEDAL_EF38_GOLD_DEG", 69.0)  # 受光方位，上为正（官方靶 b622_r0c0 同尺实测）
EF38_GOLD_EXP = _envf("MEDAL_EF38_GOLD_EXP", 3.0)   # 暗端下拉沿行程的幂（>1 把变暗推向下半程）
EF38_GOLD_OV = _envf("MEDAL_EF38_GOLD_OV", 0.10)    # 贴角过冲幅度（0 = 不过冲 ⇒ 逐字节回退）
EF38_GOLD_KNEE = _envf("MEDAL_EF38_GOLD_KNEE", 0.75)  # 过冲起点（归一行程 tt，尺 r4e/r4f 同值）
EF38_GOLD_SK = _envf("MEDAL_EF38_GOLD_SK", 0.50)    # 贴角 screen 幅度（0 = 不接线 ⇒ 逐字节回退）
EF38_GOLD_KNEE_S = _envf("MEDAL_EF38_GOLD_KNEE_S", 0.75)  # screen 起点（归一行程 tt；判赢档 C2 现读）
EF38_GOLD_SP = _envf("MEDAL_EF38_GOLD_SP", 1.2)     # screen 贴角集中度幂
EF38_GOLD_DARKAMP = _envf("MEDAL_EF38_GOLD_DARKAMP", 15.0)  # 上岗取档 P2（用户目检通过）；0 = 不接线逐字节回退
EF38_GOLD_SHELFAMP = _envf("MEDAL_EF38_GOLD_SHELFAMP", 20.0)  # 上岗取档 P2；与 DARKAMP 同门同进同退
EF38_DECO_GATE = _envf("MEDAL_EF38_DECO_GATE", 1.0)  # 装饰落笔门（0 = 不接线，逐字节回退）
EF38_DECO_TTMAX = _envf("MEDAL_EF38_DECO_TTMAX", 0.45)  # 受光/背光分界（归一行程 tt，高于此落奶白浅笔）


def _ef38_pchip(x, y, xq):
    # 单调保形三次 Hermite（Fritsch-Carlson，C1）；numpy 无 scipy。R12 用其替代 np.interp 折线以消除斜率突变过渡线。
    x = np.asarray(x, dtype=np.float64); y = np.asarray(y, dtype=np.float64)
    xq = np.asarray(xq, dtype=np.float64)
    h = np.diff(x); delta = np.diff(y) / h; n = x.size
    m = np.zeros(n, dtype=np.float64)
    for k in range(1, n - 1):
        if delta[k - 1] * delta[k] <= 0.0:
            m[k] = 0.0
        else:
            w1 = 2.0 * h[k] + h[k - 1]; w2 = h[k] + 2.0 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / delta[k - 1] + w2 / delta[k])
    def edge(d0, d1, h0, h1):
        v = ((2.0 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if np.sign(v) != np.sign(d0):
            return 0.0
        if np.sign(d0) != np.sign(d1) and abs(v) > abs(3.0 * d0):
            return 3.0 * d0
        return v
    if n == 2:
        m[0] = m[1] = delta[0]
    else:
        m[0] = edge(delta[0], delta[1], h[0], h[1]); m[-1] = edge(delta[-1], delta[-2], h[-1], h[-2])
    xqc = np.clip(xq, x[0], x[-1])
    idx = np.clip(np.searchsorted(x, xqc, side="right") - 1, 0, n - 2)
    hk = h[idx]; t = (xqc - x[idx]) / hk; t2 = t * t; t3 = t2 * t
    return ((2 * t3 - 3 * t2 + 1) * y[idx] + (t3 - 2 * t2 + t) * hk * m[idx]
            + (-2 * t3 + 3 * t2) * y[idx + 1] + (t3 - t2) * hk * m[idx + 1])


def _ef38_additive(tt, darkamp, shelfamp):
    # R12 平滑形制：抬起摊到 [0.16,0.30]、归零摊到 [0.58,0.70]，中段缓平台回落；暗端 tt<=0.16 恒 -darkamp、亮端 tt>=0.70 恒 0。
    dark = _ef38_pchip((0.0, 0.16, 0.28, 1.0), (1.0, 1.0, 0.0, 0.0), tt)
    shelf = _ef38_pchip((0.0, 0.16, 0.30, 0.42, 0.50, 0.58, 0.64, 0.70, 1.0),
                        (0.0, 0.0, 0.80, 0.95, 0.50, 0.80, 0.55, 0.0, 0.0), tt)
    return (shelfamp * shelf - darkamp * dark).astype(np.float32)


def _ef38_tt(CW, CH, cx, cy, R, deg):
    """EF38 归一受光行程 tt∈[0,1]（1 = 最亮端）。打光与装饰落笔门共用同一张行程图，
    避免同式在两处各写一遍而漂开。行程归一：tt 的 0/1 端在章外（t=1 对应投影
    d=R·1.1/2=258.5 > 章面支撑），章面沿 DEG 轴的实际支撑是顶/底顶点 ±(R-3)·sin(DEG)
    ⇒ 不归一则顶端抬不满、中位附近已用掉大半行程（TB-33 R-0 归因，尺 tb33_r0b）。"""
    yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32)
    cs, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    t = np.clip(((xx - cx) * cs + (yy - cy) * -sn) / (R * 1.1) / 2 + 0.50, 0, 1)
    span = (R - 3) * sn / (R * 1.1) / 2
    return np.clip((t - (0.50 - span)) / (2 * span), 0, 1)


# ---- EF-RESTORE 杠杆开关（终末地还原度，默认开）----
def _efr(name):
    return os.environ.get("MEDAL_EFR_" + name, "1") != "0"
EFR_ALL = _efr("ALL")


def compose_endfield(face, text="", subtitle="", serial="", tone="ef_silver",
                     number="", fam="story") -> Image.Image:
    CW, CH = 1000, 1240
    canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    cx, cy = CW // 2, 620
    R = 470
    fam = fam if fam in ("story", "combat", "industry") else "story"
    tp = EF_TONE_V2.get(tone, EF_TONE_V2["ef_silver"])
    f_dark, f_mid, f_end = tp["field"]

    apothem = R * math.sqrt(3) / 2
    outline_pts = _hex_pts(cx, cy, R - 3)
    hex_mask = Image.new("L", (CW, CH), 0)
    ImageDraw.Draw(hex_mask).polygon(outline_pts, fill=255)

    outline_c = _ef_measured(tone, "edge") + (255,)
    engrave_c = tp["engrave"]

    # ---- 场：素材采样网格的多方向非对称渐变（珠光走 v12 基准参数）----
    axis = 55 if fam == "story" else 35
    _hp_field = None
    if tone == "ef_gold" and EFR_ALL:
        _hp = _ef_grids().get("gold_plated_field")
        if _hp:
            _t = Image.new("RGB", (len(_hp[0]), len(_hp)))
            _t.putdata([tuple(v) for row in _hp for v in row])
            _hp_field = _t.resize((CW, CH), Image.BICUBIC).filter(
                ImageFilter.GaussianBlur(3))    # R-26d：网格自带中值+均值平滑，blur 3 足够
    if tone == "ef_gold_pure":
        # 官方金色 hue 随亮度 52°→28° 漂移、val 233→71 大跨度（8 段剖面实测），
        # _metal_field 恒定色相投影结构性抹掉这两者 ⇒ 纯金改吃原色直采网格（resample_goldpure.py）
        _hp = _ef_grids().get("gold_pure_field")
        if _hp:
            _t = Image.new("RGB", (len(_hp[0]), len(_hp)))
            _t.putdata([tuple(v) for row in _hp for v in row])
            _hp_field = _t.resize((CW, CH), Image.BICUBIC).filter(
                ImageFilter.GaussianBlur(18))   # R-13：单元噪声斑驳 → 加大场级融合
    field = _hp_field if _hp_field is not None else _ef_field(tone, CW, CH)
    if field is not None:
        from PIL import ImageEnhance
        soft = tone == "ef_gold_pure"
        if tone == "ef_pearl":   # R-27 珠光回退夜前状态（用户裁定 HSV 增强导致过渡染色）
            field = ImageEnhance.Color(field).enhance(1.45)      # R-16：用户裁定"颜色不够猛"——用户眼睛为准，向浓烈方向拉
        else:
            field = ImageEnhance.Color(field).enhance(1.02 if soft else 1.06)
            if tone == "ef_gold":
                field = ImageEnhance.Color(field).enhance(1.06 / 1.06)   # R-24：净 1.06
        fa = np.asarray(field.convert("RGB"), dtype=np.float32)
        yy2, xx2 = np.mgrid[0:CH, 0:CW].astype(np.float32)
        edge_f = np.clip(np.sqrt(((xx2 - cx) / (R * 0.98)) ** 2 +
                                 ((yy2 - cy) / (R * 1.08)) ** 2), 0, 1.15) ** 1.6
        if tone == "ef_pearl":
            boost = 1 + 0.35 * edge_f                            # 珠光：轻补偿（新网格色度已足）
        elif soft:
            boost = 1 + 0.30 * edge_f                            # 纯金：哑光
        elif tone == "ef_gold":
            boost = 1 + 0.0 * edge_f                             # R-24 镀彩金：已用 HSV 空间增强（色相保持），此处不再叠加
        else:
            boost = 1 + 0.35 * edge_f                            # 金属：边缘略提色
        mean3 = fa.mean(2, keepdims=True)
        lowest = fa.min(2)
        # R-27 珠光回退 R-16c：cap 系 R-24 加入，珠光按 R-16c 无 cap 路径
        # 修正：穿零判定是"增强后最低通道 <0"（原写法 lowest<0 永假=cap 永不触发）
        cap = np.where(tone == "ef_pearl", boost, np.where(mean3[:, :, 0] + (lowest - mean3[:, :, 0]) * boost < 0, mean3[:, :, 0] / np.maximum(mean3[:, :, 0] - lowest, 1e-3), boost))
        boost = np.minimum(boost, cap)
        fa = np.clip(mean3 + (fa - mean3) * boost[..., None], 0, 255)
        field = Image.fromarray(fa.astype(np.uint8), "RGB")
        field = ImageEnhance.Contrast(field).enhance(1.05)
        field = field.convert("RGBA")
        field.alpha_composite(_brushed_streaks((CW, CH), axis, 230, 13))
        if tone in ("ef_dark", "ef_bronze"):
            # R-15：官方深灰章面拉丝纹理能量 14 vs 我方 12（高通实测）——2px 线 + 后模糊成哑光缎面
            # （直绘 2px 线读作'雨丝'，用户视角机械感重；软化后能量保持、质感对齐官方拉丝）
            _dk = _brushed_streaks((CW, CH), axis, 420, 18, width=1).filter(
                ImageFilter.GaussianBlur(0.8))
            field.alpha_composite(_dk)
        elif tone == "ef_silver":
            # R-16：官方银章拉丝能量 12.7 vs 我方 10.9——亮底上要暗划痕为主（白线在银底不可见）
            field.alpha_composite(_brushed_streaks((CW, CH), axis, 420, 30, width=1, dark_ratio=0.8))
        # 旧版硬编码"右上橙+底部绿"flow 椭圆已删：金橙/绿结构由 gold_plated_field 网格
        # （154402 白纹章章 20×24 重采）原样承载，叠椭圆会和网格真实结构打架
            field = _hsv_sat_boost(field, 1.30, 0.06, 0.30, CW, CH, cx, cy, R)   # R-25 HSV 强饱和（色相保持）
        canvas.paste(field, (0, 0), hex_mask)
        if os.environ.get("MEDAL_STAGE_DUMP"):
            canvas.convert("RGB").save(os.path.join(
                os.environ["MEDAL_STAGE_DUMP"], "s1_field.png"))
    else:
        ramp = _metal_ramp((CW, CH), axis, f_dark, f_mid, tp["band"],
                           band_pos=0.40, band_w=0.16).convert("RGBA")
        ramp.alpha_composite(_brushed_streaks((CW, CH), axis, 240, 15))
        canvas.paste(ramp, (0, 0), hex_mask)

    # ---- 官方厚斜边亮环（仅深灰/铜阶；径向剖面实测）----
    # 官方排名章 r0c3 径向 luma：r<0.65 平坦 80，r 0.65→1.0 均匀攀升至 173（×2.16）——
    # 物理章的倒角亮边沿周边均匀（rim 层错在方向性脊槽，已降 0.15）。
    # 三枚官方章边界距离分箱剖面一致：外 ~0.42 apothem 内 luma 75→140-167（×1.9-2.2），指数 ~1.1。
    # 色场网格采样自官方章、已含官方打光，此层只是沿实测亮向的轻度强化，跨度=官方实测 1.03~1.18。
    # 旧版 1.64 跨度（0.55→1.15）是双重叠加，被用户判"打光渐变方向和强度都有问题"。
    # 方向角（0°=右，-90°=上）：gold -29° / gold_pure -87° / dark -44° / silver -103° / pearl -167°
    yy3, xx3 = np.mgrid[0:CH, 0:CW].astype(np.float32)
    _lux = {  # tone: (方向单位向量(dx,dy), 跨度) —— 官方章统计分档
        "ef_gold":      ((0.87, -0.48), 1.12),
        "ef_gold_pure": ((0.80, -0.60), 1.16),   # R-10 回退 R-4 全局打光（右上-37°，0.92→1.07 全局式的章内等效）
        "ef_dark":      ((0.70, 0.71), 1.35),   # R-15 内场实测（三枚一致，d>0.55 apothem 分象限）：亮向右下
        "ef_bronze":    ((0.70, 0.71), 1.35),   # 下/上 1.25、右/左 1.39；旧 -44° 是近平场+含环带掩码的噪声角
        "ef_silver":    ((0.80, -0.60), 1.16),   # R-10 回退 R-4 全局打光（与纯金同式，用户认可的均匀观感）
        "ef_pearl":     ((-0.97, -0.22), 1.06),
    }
    (_ldx, _ldy), _span = _lux.get(tone, ((0.87, -0.48), 1.12))
    t_dir = np.clip(((xx3 - cx) * _ldx + (yy3 - cy) * _ldy) / (R * 1.1) / 2 + 0.5, 0, 1)
    light_lo = 2.0 / (1.0 + _span)
    light_hi = _span * light_lo
    light = light_lo + (light_hi - light_lo) * (t_dir ** 1.1)
    if tone != "ef_gold_pure":   # 纯金回退 R-4 全画布打光（见纹章合成之后），场层不打避免双重
        _arr = np.asarray(canvas.convert("RGB"), dtype=np.float32) * light[..., None]
        canvas = Image.fromarray(np.clip(_arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(canvas)
    if os.environ.get("MEDAL_STAGE_DUMP"):
        canvas.convert("RGB").save(os.path.join(
            os.environ["MEDAL_STAGE_DUMP"], "s3_light.png"))

    # ---- 底部网点渐隐（章面下缘特征）----
    # 实测的 `feed_rgb` 就是素材网点**笔画像元**自己的电平（极性判定后的暗/亮
    # 元中位色），所以照实喂时必须满不透明；旧常数 alpha=90 会把笔画朝底色场稀释掉
    # ~2/3，量测在 lowdot bin 里连样本都取不到。未照实喂的组保持 90。
    # `ss=8` 是同一个坑的另一半：不超采样时画出来的不是 32% 网点而是 84% 暗膜。
    dot_measured = _ef_fed(tone, "lowdot")
    dot = _halftone_tile(period=5, dot=1.6, ss=8,
                         color=dot_measured or tuple(int(c * 0.5) for c in f_mid),
                         alpha=255 if dot_measured else 90, offset=False)
    fade = Image.new("L", (CW, CH), 0)
    fd = ImageDraw.Draw(fade)
    # 190 仍是**未实测**常数，但先前实测量过它值不值得抬：可算的子带里「要压到素材那个压暗比
    # 所需的不透明度」全部 ≥1.0（本地 fade 档实测，量测脚本不随包发布）
    # ⇒ 坡道抬满到 255 也到不了素材，真瓶颈在点色与网点占空，不在这条坡道上。
    for yy in range(int(cy + apothem * 0.45), int(cy + apothem)):
        t = (yy - (cy + apothem * 0.45)) / (apothem * 0.55)
        fd.line([(0, yy), (CW, yy)], fill=int(190 * t))
    big = Image.new("RGBA", (CW, CH))
    tw, th2 = dot.size
    for yy in range(0, CH, th2):
        for xx in range(0, CW, tw):
            big.paste(dot, (xx, yy), dot)
    big.putalpha(ImageChops.multiply(big.getchannel("A"), fade))
    canvas.alpha_composite(big)

    # ---- 中央纹章（整图入章时铺满章面，随金属一起被打光坡道扫过）----
    f = face.copy()
    fa_min, _fa_max = f.getchannel("A").getextrema()
    full_bleed = fa_min > 200
    if full_bleed:
        fr = max((apothem * 2 - 20) / f.width, (2 * R - 34) / f.height)
    else:
        fr = min(EMBLEM_CAP / max(f.size), 1.0)
    f = f.resize((max(1, int(f.width * fr)), max(1, int(f.height * fr))), Image.LANCZOS)
    fx, fy = cx - f.width // 2, cy - f.height // 2 - (0 if full_bleed else 10)
    # 落影：素材的纹章是「贴在金属面上的凸起件」，右下永远有一条硬边暗影。
    # 没有这条影，浅色纹章就化进色场里看不见（旧稿的主要失分点）。
    # 铺满档不投影：它本身就是金属面，不是贴在面上的凸起件。
    if not full_bleed:
        sh = f.getchannel("A").filter(ImageFilter.GaussianBlur(6.0))
        if SILO_SHADE_K >= 1.0:
            sc = tuple(int(round(float(c))) for c in
                       np.asarray(PALETTES[tone][0], dtype=np.float32) * SILO_SHADE_MUL)
            shadow = Image.new("RGBA", f.size, sc + (0,))
            shadow.putalpha(sh.point(lambda v: int(v * SILO_SHADE_A)))
        else:
            shadow = Image.new("RGBA", f.size, tp["engrave"] + (0,))
            shadow.putalpha(sh.point(lambda v: int(v * 0.80)))
        canvas.alpha_composite(shadow, (fx + 6, fy + 7))
    canvas.alpha_composite(f, (fx, fy))

    # ---- 纯金档方向打光（EF38；场层对纯金维持排除 ⇒ 不与色场网格双重叠加）----
    # 方位取官方靶同尺实测 +69.0：`_lux` 现值 (0.80,-0.60)=+36.87 若接进场层会把合成立体角
    # 从 71.4 拽到 60.3（尺 tb31_r37_gold_lux KA7 三向对照），+69.0 只拽 −0.2°。
    # 只动 RGB、alpha 原样（末尾 keep_mask 的半透明笔画合成口径不许变，同 RIM_AMP 层）。
    if tone == "ef_gold_pure" and EF38_GOLD_LUX > 0.0:
        tt4 = _ef38_tt(CW, CH, cx, cy, R, EF38_GOLD_DEG)
        light4 = 1.0 - (1.0 - 1.0 / EF38_GOLD_LUX) * ((1.0 - tt4) ** EF38_GOLD_EXP)
        if EF38_GOLD_OV > 0.0:
            light4 = light4 + EF38_GOLD_OV * np.clip(
                (tt4 - EF38_GOLD_KNEE) / max(1.0 - EF38_GOLD_KNEE, 1e-9), 0, 1)
        rgba4 = np.asarray(canvas, dtype=np.float32).copy()
        rgba4[..., :3] = np.clip(rgba4[..., :3] * light4[..., None], 0.0, 255.0)
        if EF38_GOLD_DARKAMP != 0.0 or EF38_GOLD_SHELFAMP != 0.0:
            offset4 = _ef38_additive(tt4, EF38_GOLD_DARKAMP, EF38_GOLD_SHELFAMP)
            rgba4[..., :3] = np.clip(rgba4[..., :3] + offset4[..., None], 0.0, 255.0)
        if EF38_GOLD_SK > 0.0:
            w4 = np.clip((tt4 - EF38_GOLD_KNEE_S) / max(1.0 - EF38_GOLD_KNEE_S, 1e-9), 0, 1) ** EF38_GOLD_SP
            rgb4 = rgba4[..., :3]
            lite4 = np.clip(rgb4 + EF38_GOLD_SK * (255.0 - rgb4) * w4[..., None], 0.0, 255.0)
            rgba4[..., :3] = np.where(rgba4[..., 3:4] > 0, lite4, rgb4)
        canvas = Image.fromarray(rgba4.astype(np.uint8), "RGBA")

    # ---- 描边：贴着章体边缘向内的**实心带**，不是居中在边界上的细线 ----
    # 旧写法 `polygon(_hex_pts(R), width=5)` 的线宽是**居中**在路径上的（跨 R±2.5），
    # 而末尾 keep_mask 按半径裁 ⇒ 垂直于边只剩 2.7px；量测的 `edge` bin 却是
    # 「边缘向内 3+R//120 = 6px」，于是 6px 里 3.3px 仍是色场，描边比读不回实测电平
    # （5 组里 4 组 |Δ| 0.102~0.255）。带子按同一个 6px 口径画，多 1px
    # 余量给章体边界的抗锯齿。
    band_w = 3 + R // 120 + 1
    edge_band = Image.new("L", (CW, CH), 0)
    eb = ImageDraw.Draw(edge_band)
    eb.polygon(_hex_pts(cx, cy, R - 3), fill=255)
    eb.polygon(_hex_pts(cx, cy, R - 3 - band_w), fill=0)
    canvas.paste(Image.new("RGBA", (CW, CH), outline_c), (0, 0), edge_band)

    d = ImageDraw.Draw(canvas)
    d.polygon(_hex_pts(cx, cy, R - 16), outline=outline_c[:3] + (110,), width=2)


    # ---- 装饰簇落点/电平门（TB-33 R-6）----
    # 旧写法把暗笔**直接画在已上光的 canvas 上**，落点是硬编码坐标：既不看主体掩膜（于是圆角
    # 方块压在老虎耳上），也不看受光行程（于是 9 根斜纹横穿最亮的右上顶区，把打光凿回深棕）。
    # 官方靶 3× 目检（tb33_off_tight_x3.png）：金系几何词汇（点阵/三角/斜纹盘/别针/字形）在
    # 受光侧一律是**奶白浅笔**，暗笔只出现在背光侧的空金属上 ⇒ 本门两件事：
    #   落点 = 整簇 bbox 须在「章内 ∩ 边带外 ∩ 主体（凸起件）外」，否则整簇不落笔；
    #   电平 = bbox 平均 tt > TTMAX（受光侧）时笔画色从暗乘子换成 tp["engrave"] 奶白，alpha 不变。
    # 只作用于 ef_gold_pure（EF38 打光的作用面）；GATE=0 时 (True, False) 且色不换 ⇒ 逐字节回退。
    _dg = [None]

    def _deco_geo():
        if _dg[0] is None:
            g = Image.new("L", (CW, CH), 0)
            ImageDraw.Draw(g).polygon(_hex_pts(cx, cy, R - 3 - band_w), fill=255)
            ga = np.asarray(g) > 127
            subj = Image.new("L", (CW, CH), 0)
            subj.paste(f.getchannel("A"), (fx, fy))
            ga &= np.asarray(subj) < 8
            _dg[0] = (ga, _ef38_tt(CW, CH, cx, cy, R, EF38_GOLD_DEG))
        return _dg[0]

    def _deco(x0, y0, x1, y1):
        """→ (可落笔?, 落点在受光侧?)。GATE=0 或非纯金 ⇒ (True, False)，逐字节回退。"""
        if EF38_DECO_GATE <= 0.0 or tone != "ef_gold_pure":
            return True, False
        ga, tt = _deco_geo()
        xa, xb = max(0, int(min(x0, x1))), min(CW, int(max(x0, x1)) + 1)
        ya, yb = max(0, int(min(y0, y1))), min(CH, int(max(y0, y1)) + 1)
        if xa >= xb or ya >= yb:
            return False, False
        return (bool(ga[ya:yb, xa:xb].all()),
                float(tt[ya:yb, xa:xb].mean()) > EF38_DECO_TTMAX)

    def _deco_c(col, lit):
        return engrave_c + (col[3],) if lit else col

    # ---- 条纹簇装饰（金系；官方靶 3× 目检：暗笔只出现在背光侧空金属，受光顶区是奶白浅笔）----
    _deco_gold = tone in ("ef_gold", "ef_gold_pure")
    if fam == "story" and _deco_gold:
        def stripes(px, py, n, ln, gap, col, wid=2):
            for i in range(n):
                d.line([(px + i * gap, py), (px + i * gap + ln, py + ln)],
                       fill=col, width=wid)
        _sc = tuple(int(c * 0.55) for c in f_mid) + ((190,) if EFR_ALL else (60,))
        for (px, py, n, ln, gap, wid) in ((cx + 150, cy - R + 90, 9, 64, 10, 3),
                                          (cx - R + 90, cy + 60, 8, 56, 10, 3),
                                          (cx + apothem - 150, cy + 40, 7, 50, 9, 3),
                                          (cx - apothem + 60, cy - R + 200, 6, 44, 9, 2),
                                          (cx + 190, cy + R - 260, 6, 44, 9, 2)):
            ok, lit = _deco(px, py, px + (n - 1) * gap + ln, py + ln)
            if ok:
                stripes(px, py, n, ln, gap, _deco_c(_sc, lit), wid)
        # 加号点阵组 ×3（官方词汇：+ + + 十字点阵）
        def plus_grid(px, py, cols_, rows_, s, col):
            for rr in range(rows_):
                for cc in range(cols_):
                    x0, y0 = px + cc * s, py + rr * s
                    d.line([(x0 - s*0.3, y0), (x0 + s*0.3, y0)], fill=col, width=2)
                    d.line([(x0, y0 - s*0.3), (x0, y0 + s*0.3)], fill=col, width=2)
        _pc = tuple(int(c * 0.62) for c in f_mid)
        for (px, py, cols_, rows_, s, al) in ((cx - R + 90, cy - 130, 4, 3, 26, 170),
                                              (cx + apothem - 150, cy + 60, 3, 3, 24, 160),
                                              (cx - apothem + 100, cy + R - 240, 3, 2, 24, 150)):
            ok, lit = _deco(px - s * 0.3, py - s * 0.3,
                            px + (cols_ - 1) * s + s * 0.3, py + (rows_ - 1) * s + s * 0.3)
            if ok:
                plus_grid(px, py, cols_, rows_, s, _deco_c(_pc + (al,), lit))
        # 圆角方块散布（官方词汇）
        for (bx, by, bs) in ((cx + apothem - 190, cy - R + 210, 26),
                             (cx - apothem + 150, cy + 150, 20),
                             (cx + 60, cy + R - 230, 16)):
            ok, lit = _deco(bx, by, bx + bs, by + bs)
            if ok:
                d.rounded_rectangle([bx, by, bx + bs, by + bs], radius=5,
                                    outline=_deco_c(tuple(int(c * 0.6) for c in f_mid) + (150,), lit),
                                    width=2)

    # ---- 深褐有机斑块（金系专属；银/珠光的深斑属纹章内容不属场装饰）----
    if fam == "story" and tone in ("ef_gold", "ef_gold_pure"):
        blotch = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        bd2 = ImageDraw.Draw(blotch)
        bd2.polygon([(cx - R + 10, cy - 160), (cx - apothem + 30, cy - 240),
                     (cx - apothem + 40, cy + 60), (cx - R + 20, cy + 40)],
                    fill=(128, 96, 44, 115))
        bd2.polygon([(cx - apothem + 50, cy - 120), (cx - R + 60, cy - 60),
                     (cx - apothem + 60, cy - 20)], fill=(110, 84, 40, 95))
        blotch = blotch.filter(ImageFilter.GaussianBlur(22))
        canvas.alpha_composite(blotch)

    # ---- 剧情章装饰：斜插销钉 + 左侧点阵（对照 核心降落）----
    if fam == "story" and tone == "ef_gold_pure":
        pin = (74, 56, 22, 255) if EFR_ALL else (92, 74, 34, 255)
        for (px, py, ang) in ((cx - R + 70, cy - R + 130, 32),):
            L = 96
            dxp, dyp = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            ok, lit = _deco(px - dxp * L / 2 - 5, py - dyp * L / 2 - 5,
                            px + dxp * L / 2 + 5, py + dyp * L / 2 + 5)
            if not ok:
                continue
            pc = _deco_c(pin, lit)
            d.line([(px - dxp * L / 2, py - dyp * L / 2), (px + dxp * L / 2, py + dyp * L / 2)],
                   fill=pc, width=10)
            d.ellipse([px - dxp * L / 2 - 5, py - dyp * L / 2 - 5,
                       px - dxp * L / 2 + 5, py - dyp * L / 2 + 5], fill=pc)
        for r_ in range(4):
            for c_ in range(3):
                d.ellipse([cx - R + 52 + c_ * 16, cy - 20 + r_ * 16,
                           cx - R + 60 + c_ * 16, cy - 12 + r_ * 16],
                          fill=(250, 247, 235, 200))

    # ---- 两侧装饰轨：螺丝 + 字符列 / 点阵栅格（对照截图左右缘）----
    if fam == "story":
        lx, rx = cx - apothem + 16, cx + apothem - 16
        rail = engrave_c + (210,) if EFR_ALL else engrave_c + (120,)
        d.line([(lx, cy - R + 90), (lx, cy + R - 110)], fill=rail, width=2)
        d.line([(rx, cy - R + 90), (rx, cy + R - 110)], fill=rail, width=2)
        for sy in (cy - 150, cy, cy + 150):
            for sx in (lx, rx):
                d.ellipse([sx - 5, sy - 5, sx + 5, sy + 5], outline=rail, width=2)
        f_g = load_font(FONT_MONO or FONT_CN, 13)
        for i, gy in enumerate(range(cy - 110, cy + 120, 42)):
            d.text((lx - 6, gy), ("+" if i % 2 == 0 else "×"), font=f_g, fill=rail)
            d.text((rx - 4, gy), ("·" if i % 2 == 0 else "+"), font=f_g, fill=rail)
        for gy in range(cy - 130, cy + 130, 18):
            d.ellipse([rx + 4, gy, rx + 7, gy + 3], fill=rail)

    # ---- 顶部铭牌框（story/combat：车牌式 + 四角铆钉 + 空心三角）/ industry：五金件 ----
    if fam == "industry":
        _ef_industry_hardware(d, cx, cy, R, outline_c, engrave_c, tp, tone)
    else:
        _ef_nameplate(d, cx, cy, R, outline_c, f_mid, tone)
    # 四条注记的落点取自实测带（`ef_layer_geom.CORNER`，素材角部注记暗元 u/v 分位）：
    # 旧坐标有 3 条画在章体外被裁掉、第 4 条在章内但在检测 bin 外（存活率全 0.000）。
    # 角部注记一律走**相对电平**：喂色档吃 `_ef_corner_delta`，未喂色的借用组
    # 吃 `_ef_corner_fallback_delta`（= c_dark×255 三通道同减）。
    # 旧的「兜底就搬 engrave 绝对色」那条支自本笔退出渲染路径 —— 它把注记画在脚下之上
    # +79.8~+141.1 灰阶（现跑），而素材侧同一条笔画是暗的。
    corner_d = _ef_corner_delta(tone)
    if corner_d is None:
        corner_d = _ef_corner_fallback_delta(tone)
    annots = _ef_corner_origins(cx, cy, R)
    # 逐条注记各取自己脚下的环带（`d` 已是 ImageDraw ⇒ 数组另起名）
    rgb_arr = np.asarray(canvas.convert("RGB"), dtype=np.float64)
    keep_arr = np.asarray(hex_mask) > 127
    f_annot = _ef_annot_font(EF_CORNER_SIZE)
    for x, y, s in annots:
        bg = _ef_annot_bg(rgb_arr, keep_arr, x, y, s, f_annot)
        _ef_corner_annotation(d, x, y, s, _ef_corner_rel(bg, corner_d), EF_CORNER_SIZE)

    # ---- 底部接口触点 ----
    _ef_ports(d, cx, int(cy + apothem) - 34, engrave_c)

    # ---- 章面文字：排名角标（深灰章） / 数字层级 / HUD 注记 ----
    f_num = load_font(FONT_EN_BLACK or FONT_MONO or FONT_CN, 38)
    f_note = load_font(FONT_MONO or FONT_CN, 17)
    if tone == "ef_dark" and number:
        rk = f"#{number}"
        d.text((cx + R - 190, cy - 60), rk, font=load_font(FONT_EN_BLACK or FONT_CN, 44),
               fill=engrave_c + (230,))
    elif number and fam == "story" and tone in ("ef_gold", "ef_pearl"):
        f_big = load_font(FONT_EN_BLACK or FONT_CN, 64)
        wt = f"{number}"
        d.text((cx - R + 84, cy + 70), wt, font=f_big, fill=engrave_c + (225,))
    elif number and fam != "combat" and tone == "ef_silver":
        nw, nh = 138, 58
        nx, ny = cx - nw // 2 - 46, cy + R - 196
        d.rounded_rectangle([nx, ny, nx + nw, ny + nh], radius=9,
                            fill=(20, 22, 24, 215),
                            outline=(255, 255, 255, 110), width=2)
        tw = d.textlength(number, font=f_num)
        d.text((nx + nw / 2 - tw / 2, ny + nh / 2 - f_num.size / 2 - 2), number,
               font=f_num, fill=(245, 245, 240, 255))
    if fam == "combat" and number:
        f_cnt = load_font(FONT_EN_BLACK or FONT_CN, 46)
        cnt = f"{number} TIMES"
        d.text((cx - d.textlength(cnt, font=f_cnt) / 2, cy + R - 240), cnt,
               font=f_cnt, fill=engrave_c + (220,))
    note = f"EF-MEDAL SYS // {serial}" if serial else "EF-MEDAL SYS"
    while d.textlength(note, font=f_note) > 210 and len(note) > 4:
        note = note[:-1]
    nt = d.textlength(note, font=f_note)
    d.text((cx - nt / 2, cy - R + 190), note, font=f_note,
           fill=engrave_c[:3] + (160,) if tone != "ef_pearl" else (60, 64, 68, 170))

    # ---- 章体厚斜边（N-1）：外缘亮脊 + 向内暗槽，逐法向扇按实测比值取幅度 ----
    # 放在**所有层画完之后**乘：倒角是章体这块金属自己的受光起伏，铭牌/注记压在它上面时
    # 也该跟着暗下去，先画再乘才物理一致。只动 RGB、alpha 原样保留（末尾 keep_mask 的
    # 半透明笔画合成口径不许变）。
    if RIM_AMP > 0.0:
        rim = _ef_rim_gain(tone, CW, CH, cx, cy, R)
        if rim is not None:
            rgba = np.asarray(canvas, dtype=np.float32)
            rgba[..., :3] = np.clip(rgba[..., :3] * rim[..., None], 0.0, 255.0)
            canvas = Image.fromarray(rgba.astype(np.uint8), "RGBA")

    # ---- 纯金终段高光去饱和（R-30b）----
    # 官方整章（含纹章内容）V0.8+ S=0.39，我方两源一致 0.50~0.53；中带 S 差随源照片浮动
    # （r29b 源 +0.10 / portrait 源 -0.18）故不动中带。V>0.70 起坡、V0.90 收 0.74，
    # 绕 luma 缩放（亮度不变、色度回收），alpha 原样。近灰文字/刻线是 no-op。
    if tone == "ef_gold_pure":
        _fa = np.asarray(canvas.convert("RGB"), dtype=np.float32)
        _lum = _fa.mean(2)
        _vmx = _fa.max(2)   # 门控用 V（与 S-V 剖面口径一致；饱和金色 mean 远低于 max）
        _kv2 = np.where(_vmx <= 178.5, 1.0,
                        np.clip(1.0 - (_vmx / 255.0 - 0.70) * 1.30, 0.74, 1.0))
        _fa = _lum[..., None] + (_fa - _lum[..., None]) * _kv2[..., None]
        _rgba = np.asarray(canvas, dtype=np.float32).copy()
        _rgba[..., :3] = np.clip(_fa, 0.0, 255.0)
        canvas = Image.fromarray(_rgba.astype(np.uint8), "RGBA")

    # ---- 裁回章体 + 细颗粒 ----
    keep_mask = Image.new("L", (CW, CH), 0)
    kd = ImageDraw.Draw(keep_mask)
    kd.polygon(_hex_pts(cx, cy, R - 3), fill=255)   # 三家族轮廓统一正六边形，无外凸件
    clean = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    clean.paste(canvas, (0, 0), keep_mask)
    canvas = clean
    rng = np.random.default_rng(7)
    k_g = int(round(GRAIN_K))
    if k_g > 0:
        # 抽样区间随幅度变（`integers(-4,5)` = 改前逐字节），k=0 时**一次都不加**（㊵）。
        n = rng.integers(-k_g, k_g + 1, (CH, CW, 1), dtype=np.int16)
        arr = np.asarray(canvas.convert("RGB"), dtype=np.int16) + n
        noisy = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    else:
        noisy = canvas.convert("RGBA")
    # 章体剪影一律硬边正六边形。不能用 `canvas.getchannel("A")`：ImageDraw 画半透明笔画时
    # 是把 fill 的 alpha **写进** alpha 通道（不是叠加），内发丝线 (…,110) 因此在 R-16 处
    # 留下一条 <127 的「假透明缝」⇒ alpha 被切成外环 + 本体两块，量测 `alpha>127` 口径下
    # 的 `edge` bin 从 6px 变成 14px（逐次腐蚀前 6 圈各吃掉 7~9k 像元，本体周边只有 2.9k），
    # 于是描边电平永远读不回来。
    noisy.putalpha(keep_mask)
    if os.environ.get("MEDAL_STAGE_DUMP"):
        canvas.convert("RGB").save(os.path.join(
            os.environ["MEDAL_STAGE_DUMP"], "s9_final.png"))
    return noisy

def _hex_pts_stretched(cx, cy, rx, ry, rot_deg=0.0):
    pts = []
    for i in range(6):
        ang = math.radians(rot_deg + 60 * i - 90)
        pts.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
    return pts


def _metal_ramp(size, theta_deg, c_dark, c_mid, c_band, band_pos=0.42, band_w=0.13):
    """阳极氧化金属渐变：沿 theta 轴的暗-中-高光带-中-暗 ramp"""
    w, h = size
    th = math.radians(theta_deg)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = (xx * math.cos(th) + yy * math.sin(th))
    t = (t - t.min()) / max(t.max() - t.min(), 1e-6)
    stops = [(0.0, c_dark), (0.28, c_mid), (band_pos, c_band),
             (band_pos + band_w, c_mid), (1.0, c_dark)]
    img = np.zeros((h, w, 3), dtype=np.float32)
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        m = (t >= p0) & (t <= p1)
        f = np.where(m, (t - p0) / max(p1 - p0, 1e-6), 0)[..., None]
        img += np.where(m[..., None], np.array(c0) * (1 - f) + np.array(c1) * f, 0)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def _brushed_streaks(size, theta_deg, count=240, alpha=16, width=1, dark_ratio=0.45):
    """顺向拉丝纹理"""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = np.random.default_rng(11)
    th = math.radians(theta_deg)
    dx, dyv = math.cos(th), math.sin(th)
    px, py = -dyv, dx
    for _ in range(count):
        sx, sy = rng.uniform(0, w), rng.uniform(0, h)
        ln = rng.uniform(50, 190)
        off = rng.uniform(-6, 6)
        shade = 255 if rng.random() < (1.0 - dark_ratio) else 0
        a = int(alpha * rng.uniform(0.5, 1.0))
        d.line([(sx + px * off, sy + py * off),
                (sx + dx * ln + px * off, sy + dyv * ln + py * off)], width=width,
               fill=(shade, shade, shade, a))
    return layer.filter(ImageFilter.GaussianBlur(0.6))


def _spectral_film(size, alpha=100, theta_deg=35, sat_boost=1.0):
    """全息光谱镀膜（橙→黄绿→青绿→蓝紫→粉）：整面渐变后整体旋转"""
    w, h = size
    stops = [(0.96, 0.55, 0.10), (0.16, 0.78, 0.22), (0.15, 0.85, 0.80),
             (0.42, 0.34, 0.92), (0.94, 0.30, 0.56), (0.96, 0.55, 0.10)]
    xs = np.linspace(0, 1, w)
    img = np.zeros((h, w, 3), dtype=np.float32)
    tt = xs * (len(stops) - 1)
    for seg in range(len(stops) - 1):
        m = (tt >= seg) & (tt <= seg + 1)
        f = np.where(m, tt - seg, 0)
        c0 = np.clip(np.array(stops[seg]) * 255 * sat_boost, 0, 255)
        c1 = np.clip(np.array(stops[seg + 1]) * 255 * sat_boost, 0, 255)
        row = c0[None, :] * (1 - f[:, None]) + c1[None, :] * f[:, None]
        img += m.T[None, :, None] * row[None, :, :]
    grad = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").rotate(
        theta_deg, expand=False, resample=Image.BILINEAR)
    ov = grad.convert("RGBA")
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    mod = (np.sin(xx / w * math.pi * 2.4 + yy / h * math.pi) * 0.5 + 0.5) ** 1.15
    mod = mod * 0.45 + 0.55                      # 0.55~1.0
    a = (np.full((h, w), alpha, dtype=np.float32) * mod).astype(np.uint8)
    ov.putalpha(Image.fromarray(a, "L"))
    return ov


def apply_ak_plating(img, hue_shift=150):
    """明日方舟镀层后处理 v2（ak_pairs 成对素材校准）：
    镀层 = 同骨骼整体色相偏移（如 破阵子 铜青→粉青）+ 提亮 + 轻珠光膜（非整面光谱）"""
    from PIL import ImageEnhance
    base_alpha = img.getchannel("A")
    rgb = img.convert("RGB")
    hsv = rgb.convert("HSV")
    h, s, v = hsv.split()
    h = h.point(lambda v_: (v_ + hue_shift) % 256)
    out = Image.merge("HSV", (h, s, v)).convert("RGBA")
    out = ImageEnhance.Brightness(out).enhance(1.06)
    out = ImageEnhance.Color(out).enhance(1.05)
    # 轻珠光干涉（低透明度，保留骨骼可读性）
    out.alpha_composite(_spectral_film(out.size, alpha=70, theta_deg=35, sat_boost=0.8))
    band = Image.new("RGBA", out.size, (0, 0, 0, 0))
    db = ImageDraw.Draw(band)
    W, H = out.size
    for i in range(-W, W, 200):
        db.line([(i, H), (i + W, 0)], fill=(255, 255, 255, 26), width=24)
    band = band.filter(ImageFilter.GaussianBlur(20))
    out.alpha_composite(band)
    out.putalpha(base_alpha)
    return out


# ----------------------------------------------------------------------------
# 三·五、糖果贴纸章模板（对标小红书蚀刻章魔术贴模板）
# ----------------------------------------------------------------------------

def _rounded_poly(draw, pts, width, fill=None, outline=None, joint="curve"):
    """多边形描边线：原生 miter 尖角（顶点利落合拢、无凸起、无空隙）"""
    col = fill if fill is not None else outline
    draw.polygon(list(pts), outline=col, width=int(width))


def _stitch_hexagon(d, cx, cy, r, dash=11, gap=8, color=(205, 178, 138, 235), width=5):
    """连续相位缝线：沿六边形均匀走针（跨顶点不重置相位），内缩避免骑边"""
    pts = _hex_pts(cx, cy, r)
    edges = []
    cum = [0.0]
    total = 0.0
    for i in range(len(pts)):
        p0, p1 = pts[i], pts[(i + 1) % len(pts)]
        ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        edges.append((p0, p1, ln, total))
        total += ln
        cum.append(total)

    def point_at(s):
        s = s % total
        for p0, p1, ln, off in edges:
            if s <= off + ln:
                t = (s - off) / max(ln, 1e-6)
                return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
        return pts[0]

    s = 0.0
    while s < total:
        a = point_at(s)
        b = point_at(min(s + dash, total))
        d.line([a, b], fill=color, width=width)
        s += dash + gap


def compose_candy(subject_rgba, text="", subtitle="", number="",
                  field_color=None, pattern="radial") -> Image.Image:
    """糖果贴纸章 v3 · 规范化图层顺序：
    L0 悬浮投影 → L1 白胶边 → L2 粉彩底场(顶点圆角) → L3 底纹
    → L4 三色环+内高光 → L5 缝线 → L6 主体(裁剪到场内,防穿模)
    → L7 名字气泡 → L8 装饰 → L9 收口外环 → 整图裁回白胶边轮廓
    """
    CW, CH = 1000, 1180
    canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    cx, cy = CW // 2, 570
    R = 430

    field_color = field_color or ((249, 231, 224), (244, 216, 208))   # 淡粉
    gold_hi, gold_mid, gold_lo = (244, 205, 126), (226, 178, 96), (182, 130, 62)
    pink = (247, 168, 184)
    teal = (159, 224, 200)
    white = (255, 253, 250)
    cream = (255, 250, 240)
    wine = (150, 58, 48)

    # 外轮廓（最终裁切罩）
    outer_mask = Image.new("L", (CW, CH), 0)
    ImageDraw.Draw(outer_mask).polygon(_hex_pts(cx, cy, R + 30), fill=255)
    # 场底轮廓（顶点小圆角，不外凸到白胶边）
    field_mask = Image.new("L", (CW, CH), 0)
    dfm = ImageDraw.Draw(field_mask)
    dfm.polygon(_hex_pts(cx, cy, R - 6), fill=255)
    for vx, vy in _hex_pts(cx, cy, R - 6):
        dfm.ellipse([vx - 12, vy - 12, vx + 12, vy + 12], fill=255)

    # ---- L0 悬浮投影 ----
    sh_c = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(sh_c).polygon([(x + 6, y + 14) for x, y in _hex_pts(cx, cy, R + 34)],
                                 fill=(140, 100, 80, 70))
    canvas.alpha_composite(sh_c.filter(ImageFilter.GaussianBlur(10)))

    # ---- L1 白胶边 ----
    d0 = ImageDraw.Draw(canvas)
    d0.polygon(_hex_pts(cx, cy, R + 30), fill=white + (255,))

    # ---- L2 粉彩底场 ----
    field_img = Image.new("RGB", (CW, CH))
    dfp = ImageDraw.Draw(field_img)
    for y in range(CH):
        t = y / (CH - 1)
        col = tuple(int(field_color[0][i] + (field_color[1][i] - field_color[0][i]) * t)
                    for i in range(3))
        dfp.line([(0, y), (CW, y)], fill=col)
    canvas.paste(field_img.convert("RGBA"), (0, 0), field_mask)

    # ---- L3 底纹 ----
    dp = ImageDraw.Draw(canvas)
    if pattern == "radial":
        for i in range(20):
            ang = math.radians(i * 18)
            r1 = R - 170
            dp.line([(cx, cy), (cx + r1 * math.cos(ang), cy + r1 * math.sin(ang))],
                    fill=(191, 227, 242, 48), width=5)
    elif pattern == "dots":
        import random as _r
        _r.seed(5)
        for _ in range(90):
            ang = _r.uniform(0, math.pi * 2)
            rr = _r.uniform(40, R - 110)
            dp.ellipse([cx + rr * math.cos(ang) - 4, cy + rr * math.sin(ang) - 4,
                        cx + rr * math.cos(ang) + 4, cy + rr * math.sin(ang) + 4],
                       fill=(247, 168, 184, 110))

    # 衔接打磨：场底与白胶边交界的内阴影（die-cut 凹陷感）+ 纸质微纹理
    edge_sh = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(edge_sh).polygon(_hex_pts(cx, cy, R - 6),
                                    outline=(150, 110, 90, 70), width=6)
    canvas.alpha_composite(edge_sh.filter(ImageFilter.GaussianBlur(3)))
    rng_p = np.random.default_rng(21)
    n_p = rng_p.integers(-2, 3, (CH, CW, 1), dtype=np.int16)
    arr_p = np.asarray(canvas.convert("RGB"), dtype=np.int16) + n_p
    tex = Image.fromarray(np.clip(arr_p, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    tex.putalpha(canvas.getchannel("A"))
    canvas = tex
    d = ImageDraw.Draw(canvas)

    # ---- L4 三色可叠加环（场底之上，完整可见）+ 浮雕 ----
    d = ImageDraw.Draw(canvas)
    rings = [(R + 6, 22, cream), (R - 32, 15, gold_mid), (R - 64, 9, wine)]
    for rr, wd, col in rings:
        _rounded_poly(d, _hex_pts(cx + 3, cy + 4, rr), wd,
                      outline=tuple(int(c * 0.6) for c in col) + (150,))
        _rounded_poly(d, _hex_pts(cx, cy, rr), wd, outline=col + (255,))
    # 奶油环左上受光细线（衔接打磨：只在外缘一侧提亮）
    _rounded_poly(d, _hex_pts(cx - 3, cy - 3, R + 14), 5,
                  outline=(255, 255, 248, 170))
    _rounded_poly(d, _hex_pts(cx, cy, R - 80), 4, outline=(255, 244, 224, 200))

    # ---- L5 缝线（白胶边内 R+24，环与场之上、主体之下）----
    for pts in (_hex_pts(cx, cy, R + 24),):
        for i in range(len(pts)):
            p0, p1 = pts[i], pts[(i + 1) % len(pts)]
            seg = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            n = max(1, int(seg / 18))
            for k in range(n):
                if k % 2 == 0:
                    a = (p0[0] + (p1[0] - p0[0]) * k / n, p0[1] + (p1[1] - p0[1]) * k / n)
                    b = (p0[0] + (p1[0] - p0[0]) * (k + 0.55) / n,
                         p0[1] + (p1[1] - p0[1]) * (k + 0.55) / n)
                    d.line([a, b], fill=(205, 178, 138, 235), width=5)

    # ---- L6 贴纸主体（放大、上移、裁剪到场内 + 气泡上沿净空，防穿模）----
    sub = crop_to_subject(subject_rgba, pad_ratio=0.02)
    target = 620
    fr = target / max(sub.size)
    sub = sub.resize((max(1, int(sub.width * fr)), max(1, int(sub.height * fr))),
                     Image.LANCZOS)
    sx, sy = cx - sub.width // 2, cy - sub.height // 2 - 62
    if text:
        # 名字气泡上沿留 14px 净空：主体底部 12px 渐变羽化裁切（无生硬断口）
        cutoff_y = (cy + R - 236) - 14
        yy_c = np.arange(sub.height)[:, None].astype(np.float32) + sy
        sub_a = np.asarray(sub.getchannel("A"), dtype=np.float32)
        fade = np.clip((cutoff_y + 12 - yy_c) / 12.0, 0.0, 1.0)
        sub_a = np.where(yy_c < cutoff_y, sub_a, sub_a * fade)
        sub.putalpha(Image.fromarray(sub_a.astype(np.uint8), "L"))
    sh = Image.new("RGBA", (sub.width + 30, sub.height + 30), (0, 0, 0, 0))
    sh.paste(Image.new("RGBA", sub.size, (200, 150, 140, 80)), (15, 17),
             sub.getchannel("A"))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9)), (sx - 15, sy - 17))
    canvas.alpha_composite(sub, (sx, sy))

    # ---- L7 名字气泡（收窄上移：完全落在内环之内，不横跨边框环带）----
    if text:
        label = text if not number else f"{text} · {number}"
        f_name = load_font(FONT_CN_ROUND, 34) if any(ord(c) > 127 for c in label) \
            else load_font(FONT_EN_ROUND, 30)
        trk = 6
        bh = 74
        by = cy + R - 236
        # 该高度处六边形内宽（内环内）动态封顶
        d_c = (by + bh / 2) - cy
        hw_at = (R - d_c) / R * (R * math.sqrt(3) / 2)
        max_bw = int(2 * hw_at - 44)

        def _label_w(lb, fnt):
            return sum(max(d.textlength(c, font=fnt),
                           (fnt.getbbox(c)[2] - fnt.getbbox(c)[0]) * 1.1)
                       for c in lb) + trk * (len(lb) - 1)

        while _label_w(label, f_name) > max_bw - 70 and len(label) > 2:
            label = label[:-1]
        tw = _label_w(label, f_name)
        bw = min(int(tw + 72), max_bw)
        nb_sh = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        ImageDraw.Draw(nb_sh).rounded_rectangle(
            [cx - bw // 2 + 3, by + 7, cx + bw // 2 + 3, by + bh + 7], radius=30,
            fill=(160, 120, 90, 70))
        canvas.alpha_composite(nb_sh.filter(ImageFilter.GaussianBlur(5)))
        d.rounded_rectangle([cx - bw // 2, by, cx + bw // 2, by + bh], radius=30,
                            fill=(255, 253, 250, 242), outline=gold_mid + (255,), width=5)
        d.rounded_rectangle([cx - bw // 2 + 5, by + 5, cx + bw // 2 - 5, by + bh - 5],
                            radius=25, outline=pink + (180,), width=2)
        draw_tracked_text(d, label, cx, by + bh / 2, f_name, (90, 64, 34, 255),
                          tracking=trk, shadow=(150, 110, 60, 255))

    # ---- L8 装饰主次组织 ----
    fx, fy = cx + R * 0.50, cy - R * 0.50
    for k in range(4):
        ang = math.radians(k * 90 + 45)
        d.line([(fx - 26 * math.cos(ang), fy - 26 * math.sin(ang)),
                (fx + 26 * math.cos(ang), fy + 26 * math.sin(ang))],
               fill=(247, 168, 184, 250), width=9)
    for tx2, ty2, rr in [(fx + 26, fy + 22, 9), (fx + 42, fy + 32, 6),
                         (fx + 54, fy + 39, 4)]:
        d.ellipse([tx2 - rr, ty2 - rr, tx2 + rr, ty2 + rr],
                  fill=(159, 224, 200, 225))
    hearts = [(cx - R * 0.52, cy + R * 0.40, 17, (247, 168, 184, 245)),
              (cx - R * 0.60, cy + R * 0.47, 12, (244, 205, 126, 238)),
              (cx - R * 0.66, cy + R * 0.52, 8, (159, 224, 200, 225))]
    for hx, hy, s, col in hearts:
        lobe = s * 0.62
        d.ellipse([hx - s * 0.92, hy - s * 0.55, hx - s * 0.92 + lobe * 2,
                   hy - s * 0.55 + lobe * 2], fill=col)
        d.ellipse([hx + s * 0.92 - lobe * 2, hy - s * 0.55, hx + s * 0.92,
                   hy - s * 0.55 + lobe * 2], fill=col)
        d.polygon([(hx - s * 0.95, hy - s * 0.02), (hx + s * 0.95, hy - s * 0.02),
                   (hx, hy + s * 0.85)], fill=col)
    for dx2, dy2 in ((0, 0), (18, 14), (34, 26)):
        d.ellipse([cx - R * 0.50 + dx2 - 5, cy - R * 0.58 + dy2 - 5,
                   cx - R * 0.50 + dx2 + 5, cy - R * 0.58 + dy2 + 5],
                  fill=(244, 205, 126, 215))

    # ---- L9 收口外环 + 整图裁回白胶边轮廓（外沿绝对干净）----
    d = ImageDraw.Draw(canvas)
    _rounded_poly(d, _hex_pts(cx, cy, R + 6), 24, outline=gold_lo + (255,))
    clean = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    clean.paste(canvas, (0, 0), outer_mask)
    return clean


# ----------------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------------

def generate(input_path, output_path, style="arknights", tone=None, text="蚀刻勋章",
             subtitle="", serial="", no_matting=False, line_strength=1.0,
             detail=1.0, matting_tol=26.0, number="", mode="auto",
             emblem_design=None, emblem_style="lineart",
             polarity="dark-on-light", carve="machine", endfield_family="story"):
    src = Image.open(input_path)
    src.load()
    check_input_pixels(src)
    if getattr(src, "is_animated", False):
        src.seek(0)

    # 色调归一（方舟: silver/gold/plated/stamp；终末地: ef_silver/ef_gold/ef_irid）
    # 表里必须登记 --list-types 公布的每个 ef_* id 自身：兜底是 ef_silver，漏登记会静默错档
    if tone is None:
        tone = "silver" if style == "arknights" else "ef_silver"
    if style == "endfield":
        tone = {"silver": "ef_silver", "industrial": "ef_silver", "ef_silver": "ef_silver",
                "plated": "ef_gold", "gold": "ef_gold_pure",
                "gold_plated": "ef_gold", "ef_gold": "ef_gold",
                "iridescent": "ef_pearl", "ef_irid": "ef_pearl",
                "dark": "ef_dark", "ef_dark": "ef_dark",
                "bronze": "ef_bronze", "ef_bronze": "ef_bronze", "copper": "ef_bronze",
                "pearl": "ef_pearl", "ef_pearl": "ef_pearl",
                "gold_pure": "ef_gold_pure", "ef_gold_pure": "ef_gold_pure",
                "pure": "ef_gold_pure"}.get(tone, "ef_silver")

    warn = ""
    compose_tone = None
    face = None
    dual_render = None   # 双色轮两趟闸门的第二趟闭包（只在武装时挂上，见下方注释）
    matting_backend = "n/a"
    if emblem_design:
        # ---- 主路径：AI 设计纹章（视觉模型产出的几何图元 JSON）----
        from emblem_render import render_emblem
        kind, has_alpha, eff_mode = "emblem", False, "emblem"
        if os.path.exists(str(emblem_design)):
            with open(emblem_design, encoding="utf-8-sig") as f:
                emblem_design = f.read().strip()
        # 社区主流：浅底深线 → 用浅银金属 steel 色板
        if style == "candy":
            # 糖果章在下方分支自行把设计稿渲染成 subject_c，无需预渲染 face
            face = None
        else:
            face_tone = tone
            if style == "arknights" and tone == "silver" and polarity == "dark-on-light":
                face_tone = "steel"
            face = render_emblem(emblem_design, tone=face_tone, style=emblem_style,
                                 polarity=polarity, carve=carve)
            compose_tone = face_tone if face_tone == "steel" else None
    else:
        # ---- 输入感知：类型 / 透明通道 ----
        has_alpha, kind = analyze_input(src)
        if has_alpha:
            kind = "graphic"   # 自带透明底的几乎都是设计资产：保持锐利、不压纹理

        subject = None
        matting_backend = "off"
        if has_alpha or no_matting:
            subject = src.convert("RGBA")
            matting_backend = "skipped"
        else:
            # 可选 AI 抠图后端（MEDAL_AI_MATTING=1 时启用）；失败回退经典算法
            ai, cov = (ai_matting(src), None) if ai_matting_enabled() else (None, None)
            if ai is not None:
                # 显著性模型对无人物/无物体的风景常整图无输出：覆盖度过低等于没抠到，
                # 必须退回经典链路（它自己会再退成整图入章），否则章面只剩一粒看不见的糊。
                cov = float(np.asarray(ai.getchannel("A")).mean() / 255.0)
                if cov < 0.04 or cov > 0.96:
                    ai = None
            if ai is not None:
                subject = ai
                matting_backend = "ai"
            else:
                subject, cov = extract_subject(src, tolerance=matting_tol)
                matting_backend = "classic"
            if cov is not None and (cov < 0.04 or cov > 0.96):
                if cov < 0:
                    warn = "[warn] 主体碎片化，已回退整图入章（圆角羽化融入）"
                else:
                    warn = f"[warn] matting confidence low ({cov:.0%}), fallback to full image"

        if style == "candy":
            # 糖果章只吃主体 RGBA，不走蚀刻管线
            eff_mode = "line"
        else:
            if kind == "photo" and not no_matting:
                subject = flatten_texture(subject, strength=detail)

            if style == "endfield" and mode == "auto":
                mode = "silhouette"   # 素材纹章为扁平实心形（DESIGN_SPEC v2 §7.3）
            eff_mode = "line" if mode in ("auto", "emblem") else mode
            if mode == "emblem":
                warn = (warn + "\n" if warn else "") + \
                    "[info] --mode emblem 未提供 --emblem-design，已回退 line 模式"
            face_tone = "silver" if tone == "stamp" else tone   # 印章仅纹章路径支持
            # 两趟闸门：武装（`MEDAL_DUALITY>0`）时**第一趟强制关支** —— 判病要拿默认臂的
            # 成图去量，健康格就此原样交付、一趟不多花；病格才用 `dual_render` 重跑第二趟。
            # `MEDAL_DUALITY_FORCE=1` = 不判病、格格开支（A/B 的对照臂，就是闸门前的老行为）。
            dual_on = (style == "endfield" and eff_mode == "silhouette"
                       and DUALITY_K > 0.0 and tone in DUALITY_GUARD)
            first_k = DUALITY_K if (dual_on and DUALITY_FORCE > 0.0) else 0.0
            face = etch_face(subject, tone=face_tone, line_strength=line_strength,
                             detail=detail, mode=eff_mode, face_px=FACE_PX, duality_k=first_k)
            if carve == "hand":
                from emblem_render import carve_texture
                face = carve_texture(face, "hand")
            if dual_on and DUALITY_FORCE <= 0.0:
                def dual_render(k):
                    """第二趟：复用同一张 `subject`（抠图不重跑），只换双色开关重走
                    `etch_face` → `compose_endfield` 同一条链，交回**整枚成图**给闸门量。"""
                    f = etch_face(subject, tone=face_tone, line_strength=line_strength,
                                  detail=detail, mode=eff_mode, face_px=FACE_PX, duality_k=k)
                    if carve == "hand":
                        from emblem_render import carve_texture
                        f = carve_texture(f, "hand")
                    return compose_endfield(f, text, subtitle, serial, tone, number,
                                            fam=endfield_family)

    if style == "endfield":
        out = compose_endfield(face, text, subtitle, serial, tone, number,
                               fam=endfield_family)
        if dual_render is not None:
            out, dual_msg = _dual_gate(out, dual_render, tone, DUALITY_K)
            if DUALITY_DBG > 0.0 or dual_msg.startswith("keep=dual"):
                print("[dualgate] tone=%s %s" % (tone, dual_msg), file=sys.stderr)
    elif style == "candy":
        # 糖果贴纸章：主体同样走抽象概括（AI 设计稿按糖果画风渲染）
        if emblem_design:
            from emblem_render import render_emblem
            subject_c = render_emblem(emblem_design, tone="candy", style="flat",
                                      polarity="none")
        else:
            subject_c = subject
        out = compose_candy(subject_c, text, subtitle, number)
    else:
        comp = ("gold" if tone == "gold" else
                ("stamp" if tone == "stamp" else
                 ("plated" if tone == "plated" else
                  (compose_tone if compose_tone else "silver"))))
        out = compose_arknights(face, text, subtitle, serial, comp, number)
        if tone == "plated":
            out = apply_ak_plating(out)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    out.save(output_path)
    info = f"[info] input={kind} alpha={has_alpha} mode={eff_mode} matting={matting_backend}"
    print(info, file=sys.stderr)
    return output_path, warn


def _session_dir(root, project):
    """迭代会话目录：<repo>/output/projects/<安全名>/。产物自动编号，支持"接着上次改一改"。"""
    import re as _re
    safe = _re.sub(r"[^\w\-]+", "_", project).strip("_") or "default"
    d = os.path.join(os.path.dirname(root), "output", "projects", safe)
    os.makedirs(d, exist_ok=True)
    return d


def _archive_round(proj_dir, n, style, tone, args, warn, design_path=None):
    """把本次参数/告警/设计稿归档进会话目录（n 由调用方在生成 PNG 前算好，保证一致）。"""
    import json as _json
    import time as _time
    from shutil import copyfile
    tag = f"round{n:02d}"
    meta = {"round": n, "time": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "style": style, "tone": tone, "text": args.text, "subtitle": args.subtitle,
            "serial": args.serial, "number": args.number, "mode": args.mode,
            "line_strength": args.line_strength, "detail": args.detail,
            "matting_tol": args.matting_tol, "polarity": args.polarity,
            "carve": args.carve, "input": args.input, "warn": warn}
    with open(os.path.join(proj_dir, f"{tag}.params.json"), "w", encoding="utf-8") as f:
        _json.dump(meta, f, ensure_ascii=False, indent=2)
    if design_path and os.path.isfile(design_path):
        copyfile(design_path, os.path.join(proj_dir, f"{tag}.design.json"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="照片 -> 明日方舟/终末地风格蚀刻章")
    ap.add_argument("input", nargs="?", default=None)
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--list-types", action="store_true",
                    help="列出全部章种（style × tone × 模式）后退出")
    ap.add_argument("--project", default=None,
                    help="迭代会话项目名：产物归档到 output/projects/<名>/ 自动编号，"
                         "便于追溯与二次修改（含每轮参数/告警/设计稿快照）")
    ap.add_argument("--style", choices=["arknights", "endfield", "candy"], default="arknights")
    ap.add_argument("--tone", default=None,
                    help="方舟: silver(普通)|plated(镀层)|gold(活动金章)；终末地: silver(银)|gold_pure/pure(纯金)|gold_plated(镀彩金; 别名gold实为纯金勿用)|dark(排名)|bronze(铜阶)|pearl(镀层)")
    ap.add_argument("--endfield-family", default="story", choices=["story", "combat", "industry"],
                    help="终末地形制家族：story 剧情/陈列金章 | combat 计数章 | industry 工业五金铭牌（工业/调度）")
    ap.add_argument("--text", default="蚀刻勋章")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--serial", default="")
    ap.add_argument("--no-matting", action="store_true")
    ap.add_argument("--line-strength", type=float, default=1.0)
    ap.add_argument("--detail", type=float, default=1.0)
    ap.add_argument("--matting-tol", type=float, default=26.0)
    ap.add_argument("--number", default="", help="大号数字层级，如 100（嵌入横幅字带）")
    ap.add_argument("--mode", default="auto",
                    choices=["auto", "line", "silhouette", "facet", "icon", "emblem"],
                    help="纹章化模式：line蚀刻线稿 | silhouette剪影 | facet分面 | icon图标化 | emblem=AI设计稿")
    ap.add_argument("--emblem-design", default=None,
                    help="AI 纹章设计稿 JSON 文件路径（配合 --mode emblem 使用）")
    ap.add_argument("--emblem-style", default="lineart", choices=["lineart", "flat"],
                    help="纹章渲染语言：lineart=社区细线+排线（默认）| flat=矢量填充")
    ap.add_argument("--polarity", default="dark-on-light",
                    choices=["dark-on-light", "light-on-dark"],
                    help="明暗极性：dark-on-light=浅底深线（社区主流）")
    ap.add_argument("--carve", default="machine", choices=["machine", "hand"],
                    help="刻痕质感：machine 机器刻 | hand 手工金石味")
    args = ap.parse_args(argv)

    if args.list_types:
        from medal_types import list_types
        print(list_types())
        return 0
    if not args.input:
        ap.error("缺少输入图片路径（或使用 --list-types 查看章种）")

    root = os.path.dirname(os.path.abspath(__file__))
    proj_dir = _session_dir(root, args.project) if args.project else None
    round_no = None
    out = args.output
    if out is None:
        if proj_dir:
            round_no = 1 + len([f for f in os.listdir(proj_dir)
                                if f.startswith("round") and f.endswith(".png")])
            out = os.path.join(proj_dir,
                               f"round{round_no:02d}_{args.style}_{args.tone or 'default'}.png")
        else:
            out = os.path.join(
                os.path.dirname(root), "output",
                os.path.splitext(os.path.basename(args.input))[0] + f"_{args.style}.png")
    path, warn = generate(args.input, out, args.style, args.tone, args.text,
                          args.subtitle, args.serial, args.no_matting,
                          args.line_strength, args.detail, args.matting_tol,
                          args.number, args.mode, args.emblem_design,
                          args.emblem_style, args.polarity, args.carve,
                          args.endfield_family)
    if proj_dir:
        if round_no is None:
            round_no = 1 + len([f for f in os.listdir(proj_dir)
                                if f.startswith("round") and f.endswith(".png")])
        _archive_round(proj_dir, round_no, args.style, args.tone, args, warn,
                       design_path=args.emblem_design)
    if warn:
        print(warn, file=sys.stderr)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
