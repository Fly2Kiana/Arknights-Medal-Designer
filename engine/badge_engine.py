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
from ef_layer_geom import PLATE as EF_PLATE  # 装饰层落笔几何单一事实源（引擎与量测器共用同一张表）
from ef_layer_geom import corner_origins as _ef_corner_origins  # noqa: E402

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
    return os.environ.get("MEDAL_AI_MATTING", "").strip().lower() in ("1", "true", "on", "yes")


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


def _luma_span(img):
    """Rec.601 明度的极差（灰阶 0~255）：章面「自己有没有拉开」的量。"""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    luma = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    return float(luma.max() - luma.min())


# 回退支自动色阶的跨度门限（灰阶）。实测：平坦类夹具（纯色/雾天）章面跨度 3.9~8.0，
# 真实照片输入 36.2~107.5，官方章面跨度 p1 锚 162.2 —— 取平坦间隙几何平均并受 p1 封顶。
# 复现口径：对本包 samples/ 与 reference/ 逐输入量章面灰阶跨度即可复现，非手写常量
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
    "ef_gold_pure": ((196, 150, 70), (240, 228, 190), (252, 250, 240)),
    # 金色·加工：暖金铜面，深棕蚀刻线
    "ef_gold":    ((206, 158, 74), (240, 228, 190), (252, 250, 240)),
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


def etch_face(rgba, tone="silver", line_strength=1.0, detail=1.0, face_px=520,
              mode="line"):
    """mode: line=蚀刻线稿 | silhouette=剪影纹章 | facet=分面平涂"""
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

    if mode == "silhouette":
        # 剪影纹章：整块实心（按色板极性取深或浅）+ 轮廓微变化
        solid = _gauss_arr(np.asarray(sub.getchannel("A"), dtype=np.float32) / 255.0, 2.0)
        t = np.where(solid > 0.45,
                     fill_t + (edges - 0.5) * 0.16 * ls,
                     max(0.10, fill_t - 0.42)).astype(np.float32)
        t = np.clip(t, 0.0, 1.0)
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
    tt = t[..., None]
    lo = dark + (mid - dark) * np.clip(tt * 2.0, 0, 1)
    hi = mid + (bright - mid) * np.clip(tt * 2.0 - 1.0, 0, 1)
    out_rgb = np.where(tt < 0.5, lo, hi)

    face = Image.fromarray(np.clip(out_rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    fa = sub.getchannel("A").filter(ImageFilter.GaussianBlur(0.5))
    # 整图入章（抠图回退）：大圆角 + 宽羽化 + 边缘压暗，画面融进章面金属底
    a_min, a_max = fa.getextrema()
    # 跨度门限只判 line 档。根本理由：A1 的病料是「引擎自己的排线」，而 `_hatch()` 只在
    # line 支被调用 ⇒ 其余档没有可被刻深的线；实测理由：门限一并管到别的档时，
    # 83 张全矩阵 A/B 出现一张真照片差分行（landscape/ef_gold/silhouette）—— silhouette
    # 的平涂是设计意图，不该被当成"输入没信息"而关掉抛光。E-④ 的间隙本来就只在 line 支
    # 量过（网页侧 shadow_face 逐行复刻的就是引擎这条回退支）。
    span_ok = mode != "line" or _luma_span(face) >= FALLBACK_POLISH_SPAN_MIN
    if a_min > 200 and span_ok:
        # 回退整图的对比度修复：自动色阶 + 对比增强（实战反馈：回退图普遍过淡发灰）
        # 跨度门限：章面本身没拉开时（纯色/雾天输入只剩引擎自己的排线，跨度 0.1~8 灰阶），
        # 自动色阶会把那 6 灰阶拉到 255 满量程 = 42 倍增益 ⇒ 排线被刻成满章深线。
        from PIL import ImageEnhance as _IE
        from PIL import ImageOps as _IO
        face = _IO.autocontrast(face.convert("RGB"), cutoff=1)
        face = _IE.Contrast(face).enhance(1.2).convert("RGBA")
        w2, h2 = sub.size
        rad = max(64, int(min(w2, h2) * 0.14))
        r_mask = Image.new("L", sub.size, 0)
        ImageDraw.Draw(r_mask).rounded_rectangle([0, 0, w2 - 1, h2 - 1],
                                                 radius=rad, fill=255)
        F = max(90, int(min(w2, h2) * 0.18))          # 宽羽化带
        xs_ = np.arange(w2, dtype=np.float32)
        ys_ = np.arange(h2, dtype=np.float32)
        dx_ = np.minimum(xs_, w2 - 1 - xs_)[None, :]
        dy_ = np.minimum(ys_, h2 - 1 - ys_)[:, None]
        dist = np.minimum(dx_, dy_)
        fade = np.clip(dist / F, 0, 1)
        fade = (fade ** 0.7) * 255                    # 前快后慢的自然过渡
        fa = ImageChops.multiply(ImageChops.multiply(fa, r_mask),
                                 Image.fromarray(fade.astype(np.uint8), "L"))
        fa = fa.filter(ImageFilter.GaussianBlur(2))
        # 边缘压暗（落刀阴影），进一步消除"贴片感"
        rgb_a = np.asarray(face.convert("RGB"), dtype=np.float32)
        shade = 0.72 + 0.28 * np.clip(dist / (F * 1.4), 0, 1)[..., None]
        rgb_shaded = np.clip(rgb_a * shade, 0, 255).astype(np.uint8)
        face = Image.fromarray(rgb_shaded, "RGB").convert("RGBA")
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
    ⇒「网点」变成「整片暗膜上留针孔」，见计划 §2.1-i。
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

    # ---- 底场：垂直轻微变浅的哑光单色 ----
    hex_mask = Image.new("L", (CW, CH), 0)
    ImageDraw.Draw(hex_mask).polygon(_hex_pts(cx, cy, R), fill=255)
    field = Image.new("RGB", (CW, CH))
    dfd = ImageDraw.Draw(field)
    for y in range(CH):
        t = max(0.0, min(1.0, (y - (cy - R)) / (2 * R)))
        c0, c1 = field_top, field_bot
        col = tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
        dfd.line([(0, y), (CW, y)], fill=col)
    canvas.paste(field, (0, 0), hex_mask)

    # ---- 多层同心细线套环（官方核心语言）----
    d = ImageDraw.Draw(canvas)
    rings = [(R - 4, 3, line_hi),          # 最外圈一条较细亮线
             (R - 26, 2, line_mid),
             (R - 44, 2, line_mid),
             (R - 60, 2, line_lo)]
    # 套环受光斜面：暗影偏移 + 主环 + 上左高光，金属冲压感
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
        ray_c = line_lo if tone != "gold" else (186, 146, 68)
        ray_alpha = 110 if tone != "gold" else 140
    for i in range(72):
        ang = math.radians(i * 5)
        r1 = apothem - 20 if i % 2 == 0 else apothem - 84
        x0, y0 = cx + 92 * math.cos(ang), cy - 10 + 92 * math.sin(ang)
        x1, y1 = cx + r1 * math.cos(ang), cy - 10 + r1 * math.sin(ang)
        d.line([(x0, y0), (x1, y1)], fill=ray_c + (ray_alpha,), width=4)

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
    bw = min(int(_hex_halfwidth(R, 292) * 2 * 0.92), 500)
    bh = 84
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
                   # 改读 ef_layer_measured.json 的实测色（判据 L-0 ④ 自证过）；
                   # 现在它们只驱动章面底色场与 `_metal_ramp` 兜底路径。
        "field": [(70, 74, 78), (94, 96, 97), (52, 58, 62)],
        "band": (190, 194, 198),
        "engrave": (238, 238, 236),
        "accent": (111, 184, 168),
    },
    "ef_gold_pure": {  # 纯金（剧情金章）：金体 + 右上→左下方向打光
        "field": [(170, 140, 60), (238, 230, 185), (164, 131, 50)],
        "band": (250, 245, 220),
        "engrave": (252, 250, 240),
        "accent": (200, 40, 50),
    },
    "ef_gold": {   # 实测 顶#DCD38E 侧#DC6107(亮橙) 底#98B020(黄绿)
        "field": [(220, 97, 7), (220, 211, 142), (152, 176, 32)],
        "band": (250, 245, 220),
        "engrave": (250, 247, 235),
        "accent": (200, 40, 50),
    },
    "ef_dark": {   # 实测 上#525457 侧#2B2E2C
        "field": [(43, 46, 44), (82, 84, 87), (30, 31, 32)],
        "band": (140, 143, 145),
        "engrave": (240, 240, 238),
        "accent": (200, 202, 204),
    },
    "ef_bronze": {  # 铜阶：与 dark 共场（面板计数 铜14=深灰观感），无 #N 角标；点缀取铜色
        "field": [(43, 46, 44), (82, 84, 87), (30, 31, 32)],
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


def _ef_field(tone, CW, CH):
    """网格 → 双三次插值的非对称色场（多方向渐变 1:1 复刻素材）"""
    key = tone[3:] if tone.startswith("ef_") else tone   # ef_gold -> gold
    key = {"bronze": "dark"}.get(key, key)               # 铜阶与排名章共用场网格
    g = _ef_grids().get(key)
    if not g:
        return None
    arr = np.asarray(g, dtype=np.uint8)
    # 去团斑：网格先高斯平滑（单元格中值受纹章遮挡扰动，平滑保留渐变趋势、消除色斑）
    m = max(arr.shape[0], arr.shape[1])
    # 平滑分档：粗网格重抹去团斑；超细网格在采样端已 σ2.2 格平滑，这里只轻抹去残噪
    sigma = 1.1 if m <= 16 else (0.7 if m <= 24 else (0.9 if m <= 48 else 0.55))
    smooth = Image.fromarray(arr, "RGB").filter(ImageFilter.GaussianBlur(sigma))
    arr = np.asarray(smooth)
    # 边缘保持：首末行列各复制一次，防止插值把素材的陡峭边缘色带稀释
    arr = np.concatenate([arr[:, :1], arr, arr[:, -1:]], axis=1)
    arr = np.concatenate([arr[:1], arr, arr[-1:]], axis=0)
    small = Image.fromarray(arr, "RGB")
    # 场级扩散模糊：素材的虹彩是"色块自然扩散+模糊过渡"，插值噪声则呈条状——
    # 上采样后做一次与色块尺度相当的低通，复刻素材的柔和扩散
    field = small.resize((CW, CH), Image.BICUBIC)
    blur_px = {"ef_pearl": 16}.get(tone, 20)
    return field.filter(ImageFilter.GaussianBlur(blur_px))


_EF_LAYERS = None


def _ef_layers():
    """装饰四层实测色（engine/ef_layer_measured.json，由 reference/ 素材程序化采样得到）

    缺品阶/缺组/缺层一律 raise：兜底默认值会把「漏登记」变成静默错档。
    """
    global _EF_LAYERS
    if _EF_LAYERS is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ef_layer_measured.json")
        with open(p, encoding="utf-8") as f:
            _EF_LAYERS = json.load(f)
    return _EF_LAYERS


def _ef_group(tone):
    """该品阶借用的素材组（`meta.render_tone`，与量测器 `--check` 同一张表）"""
    L = _ef_layers()
    key = tone[3:] if tone.startswith("ef_") else tone
    grp = L["meta"]["render_tone"].get(key)
    if grp is None or grp not in L["groups"]:
        raise KeyError(f"ef_layer_measured: 品阶 {tone} 的素材组 {grp!r} 未登记")
    return L["groups"][grp]


_EF_FEED_LAYERS = ("plate", "corner", "lowdot")   # 这三层按判据 L-4′ 的判定决定喂不喂


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
    """一层实测色的绝对 RGB；`_ef_fed` 为 None 时返回 fallback（计划 §3.3）"""
    return _ef_fed(tone, layer) or fallback


def _ef_plate_lift(tone):
    """铭牌面板**这块区域**的去梯度电平（plate − 同高两侧金属）。

    素材 6 组里 5 组判 `flat`（|d_ref| 落进尺子的空读数 +0.016 内，计划 §6.1）⇒ 返回
    None = 面板与周围金属齐平，不许提亮；只有 `lift` 才返回偏移量。
    """
    p = _ef_group(tone)["plate"]
    return p["d_ref"] if p.get("d_ref_verdict") == "lift" else None


def _ef_corner_annotation(d, x, y, text, color, size=13):
    """角部工程注记：如 +001-E-1908 / ×××/＋｜ 式散布符号"""
    f = load_font(FONT_MONO or FONT_EN_BLACK or FONT_CN, size or 14)
    d.text((x, y), text, font=f, fill=color + (235,))


def _ef_ports(d, cx, bottom_y, color):
    """底部接口触点：两颗螺丝孔 + 一条触点条"""
    for dx in (-52, 52):
        d.ellipse([cx + dx - 7, bottom_y - 7, cx + dx + 7, bottom_y + 7],
                  outline=color + (200,), width=3)
    d.rounded_rectangle([cx - 26, bottom_y + 12, cx + 26, bottom_y + 24], radius=6,
                        fill=color + (90,))


def _ef_industry_hardware(d, cx, cy, R, outline, engrave, tp):
    """industry 家族五金件（素材 153730 复核修正：章体为正六边形，无切角无挂耳）：
    左上圆盘表扣 + 贴边侧接口 + 角区内六角螺丝 + 底部双箭 + L 形角码"""
    f_dark = tp["field"][0]
    # ---- 左上圆盘表扣：外环 + 内盘波形刻线 + 顶部双刻度 ----
    px, py = cx - int(R * 0.42), cy - int(R * 0.26)
    pr = int(R * 0.16)
    d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=f_dark + (80,),
              outline=outline, width=7)
    ir = int(pr * 0.72)
    d.ellipse([px - ir, py - ir, px + ir, py + ir], outline=engrave + (200,), width=3)
    for k in (-1, 0, 1):     # 盘内波形斜线（蚀刻排线语言）
        d.line([(px - ir + 8, py + k * 12 + 14), (px + ir - 8, py + k * 12 - 14)],
               fill=engrave + (190,), width=4)
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
    **落笔坐标取自 `engine/ef_layer_geom.py` 的 `PLATE`（单一事实源）**：
    量测器要按同一张表算「笔画有没有活进验收 bin」，写死在这里就会两边各说各话。"""
    p = EF_PLATE
    x0, y0, x1, y1 = cx + p["dx0"], cy + p["dy0"], cx + p["dx1"], cy + p["dy1"]
    # 面板**这块区域**的电平走实测 `d_ref`（plate − 同高两侧金属，去打光梯度）：素材 6 组
    # 里 5 组判 `flat` ⇒ 只画框和铆钉、不填色（旧值 `field_mid+(60,)` 与奶油色 (244,236,200)
    # 都是手设提亮，无素材依据）。面板里的刻字另走 L-4′，六组全是不可单常数化 ⇒ 保持现值。
    lift = _ef_plate_lift(tone)
    d.rounded_rectangle([x0, y0, x1, y1], radius=p["radius"],
                        fill=None if lift is None
                        else tuple(int(round(c * (1.0 + lift))) for c in field_mid) + (60,),
                        outline=outline, width=6)
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
    d.polygon(tri, outline=outline, width=4)


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
    corner_c = _ef_measured(tone, "corner", fallback=engrave_c)
    accent = tp["accent"]

    # ---- 场：素材采样网格的多方向非对称渐变（珠光走 v12 基准参数）----
    axis = 55 if fam == "story" else 35
    field = _ef_field(tone, CW, CH)
    if field is not None:
        from PIL import ImageEnhance
        soft = tone == "ef_gold_pure"
        if tone == "ef_pearl":
            field = ImageEnhance.Color(field).enhance(1.08)      # 珠光柔和（v12 基准）
        else:
            field = ImageEnhance.Color(field).enhance(1.05 if soft else 1.25)
        fa = np.asarray(field.convert("RGB"), dtype=np.float32)
        yy2, xx2 = np.mgrid[0:CH, 0:CW].astype(np.float32)
        edge_f = np.clip(np.sqrt(((xx2 - cx) / (R * 0.98)) ** 2 +
                                 ((yy2 - cy) / (R * 1.08)) ** 2), 0, 1.15) ** 1.6
        if tone == "ef_pearl":
            boost = 1 + 0.50 * edge_f                            # 珠光：轻补偿（v12 基准）
        elif soft:
            boost = 1 + 0.30 * edge_f                            # 纯金：哑光
        else:
            boost = 1 + 1.15 * edge_f                            # 金属：浓烈边缘
        mean3 = fa.mean(2, keepdims=True)
        fa = np.clip(mean3 + (fa - mean3) * boost[..., None], 0, 255)
        field = Image.fromarray(fa.astype(np.uint8), "RGB")
        field = ImageEnhance.Contrast(field).enhance(1.05)
        field = field.convert("RGBA")
        field.alpha_composite(_brushed_streaks((CW, CH), axis, 230, 13))
        canvas.paste(field, (0, 0), hex_mask)
    else:
        ramp = _metal_ramp((CW, CH), axis, f_dark, f_mid, tp["band"],
                           band_pos=0.40, band_w=0.16).convert("RGBA")
        ramp.alpha_composite(_brushed_streaks((CW, CH), axis, 240, 15))
        canvas.paste(ramp, (0, 0), hex_mask)

    # ---- 底部网点渐隐（章面下缘特征）----
    # 实测的 `feed_rgb` 就是素材网点**笔画像元**自己的电平（判据 L-4′ 极性判定后的暗/亮
    # 元中位色），所以照实喂时必须满不透明；旧常数 alpha=90 会把笔画朝底色场稀释掉
    # ~2/3，量测器在 lowdot bin 里连样本都取不到（§2.1-i）。未照实喂的组保持 90。
    # `ss=8` 是同一个坑的另一半：不超采样时画出来的不是 32% 网点而是 84% 暗膜。
    dot_measured = _ef_fed(tone, "lowdot")
    dot = _halftone_tile(period=5, dot=1.6, ss=8,
                         color=dot_measured or tuple(int(c * 0.5) for c in f_mid),
                         alpha=255 if dot_measured else 90, offset=False)
    fade = Image.new("L", (CW, CH), 0)
    fd = ImageDraw.Draw(fade)
    # 190 仍是**未实测**常数，但 V-④ 量过它值不值得抬：可算的子带里「要压到素材那个压暗比
    # 所需的不透明度」全部 ≥1.0（对渲染件逐格量「刻得出所需不透明度」的占比）
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

    # ---- 方向性打光：右上高光 → 左下渐暗（游戏内实拍规律）----
    yy3, xx3 = np.mgrid[0:CH, 0:CW].astype(np.float32)
    t_dir = np.clip(((xx3 - cx) / (CW * 0.62) - (yy3 - cy) / (CH * 0.62)) / 2 + 0.5, 0, 1)
    light = 0.92 + 0.15 * (t_dir ** 1.2)          # 0.92(左下) → 1.07(右上)；网格场已含主打光
    arr = np.asarray(canvas.convert("RGB"), dtype=np.float32) * light[..., None]
    canvas = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    canvas.putalpha(Image.new("L", (CW, CH), 255))

    # ---- 镀层珠光：低饱和虹彩偏移（白底珠光，非全息光谱）----



    # ---- 中央纹章 ----
    f = face.copy()
    fr = min((650 if (tone == "ef_gold" and fam == "story") else 580) / max(f.size), 1.0)
    f = f.resize((max(1, int(f.width * fr)), max(1, int(f.height * fr))), Image.LANCZOS)
    canvas.alpha_composite(f, (cx - f.width // 2, cy - f.height // 2 - 10))

    # ---- 描边：贴着章体边缘向内的**实心带**，不是居中在边界上的细线 ----
    # 旧写法 `polygon(_hex_pts(R), width=5)` 的线宽是**居中**在路径上的（跨 R±2.5），
    # 而末尾 keep_mask 按 R-3 裁 ⇒ 垂直于边只剩 2.7px；量测器的 `edge` bin 却是
    # 「边缘向内 3+R//120 = 6px」，于是 6px 里 3.3px 仍是色场，判据 L-1 读不回实测电平
    # （5 组里 4 组 |Δ| 0.102~0.255，见计划 §2.1-h）。带子按同一个 6px 口径画，多 1px
    # 余量给章体边界的抗锯齿。
    band_w = 3 + R // 120 + 1
    edge_band = Image.new("L", (CW, CH), 0)
    eb = ImageDraw.Draw(edge_band)
    eb.polygon(_hex_pts(cx, cy, R - 3), fill=255)
    eb.polygon(_hex_pts(cx, cy, R - 3 - band_w), fill=0)
    canvas.paste(Image.new("RGBA", (CW, CH), outline_c), (0, 0), edge_band)

    d = ImageDraw.Draw(canvas)
    d.polygon(_hex_pts(cx, cy, R - 16), outline=outline_c[:3] + (110,), width=2)

    # ---- 条纹簇装饰（右上/左下斜线排组，对照素材角部密排线）----
    if fam == "story":
        def stripes(px, py, n, ln, gap, col, wid=2):
            for i in range(n):
                d.line([(px + i * gap, py), (px + i * gap + ln, py + ln)],
                       fill=col, width=wid)
        stripes(cx + 120, cy - R + 60, 7, 46, 9, engrave_c + (60,))
        stripes(cx - R + 60, cy + 110, 6, 40, 9, engrave_c + (55,))
        stripes(cx + apothem - 120, cy + 60, 5, 34, 8, engrave_c + (50,))

    # ---- 剧情章装饰：斜插销钉 + 左侧点阵（对照 核心降落）----
    if fam == "story" and tone == "ef_gold_pure":
        pin = (92, 74, 34, 255)
        for (px, py, ang) in ((cx - R + 70, cy - R + 130, 32), (cx + R - 170, cy + 130, 32)):
            L = 96
            dxp, dyp = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            d.line([(px - dxp * L / 2, py - dyp * L / 2), (px + dxp * L / 2, py + dyp * L / 2)],
                   fill=pin, width=10)
            d.ellipse([px - dxp * L / 2 - 5, py - dyp * L / 2 - 5,
                       px - dxp * L / 2 + 5, py - dyp * L / 2 + 5], fill=pin)
        for r_ in range(4):
            for c_ in range(3):
                d.ellipse([cx - R + 52 + c_ * 16, cy - 20 + r_ * 16,
                           cx - R + 60 + c_ * 16, cy - 12 + r_ * 16],
                          fill=(250, 247, 235, 200))

    # ---- 两侧装饰轨：螺丝 + 字符列 / 点阵栅格（对照截图左右缘）----
    if fam == "story":
        lx, rx = cx - apothem + 16, cx + apothem - 16
        rail = engrave_c + (120,)
        d.line([(lx, cy - R + 90), (lx, cy + R - 110)], fill=rail, width=1)
        d.line([(rx, cy - R + 90), (rx, cy + R - 110)], fill=rail, width=1)
        for sy in (cy - 150, cy, cy + 150):
            for sx in (lx, rx):
                d.ellipse([sx - 5, sy - 5, sx + 5, sy + 5], outline=rail, width=2)
        f_g = load_font(FONT_MONO or FONT_CN, 13)
        for i, gy in enumerate(range(cy - 110, cy + 120, 42)):
            d.text((lx - 6, gy), ("+" if i % 2 == 0 else "×"), font=f_g, fill=rail)
            d.text((rx - 4, gy), ("·" if i % 2 == 0 else "+"), font=f_g, fill=rail)
        for gy in range(cy - 130, cy + 130, 18):
            d.ellipse([rx + 4, gy, rx + 7, gy + 3], fill=rail)
        # 红色点缀线（穿过纹章中心，对照 top0 的红色标记线）
        if tone == "ef_gold":
            ry_ = cy - 6
            d.line([(cx - 64, ry_), (cx + 64, ry_)], fill=accent + (210,), width=4)
            for dxx in (-48, -16, 16, 48):
                d.ellipse([cx + dxx - 4, ry_ - 4, cx + dxx + 4, ry_ + 4], fill=accent + (230,))

    # ---- 顶部铭牌框（story/combat：车牌式 + 四角铆钉 + 空心三角）/ industry：五金件 ----
    if fam == "industry":
        _ef_industry_hardware(d, cx, cy, R, outline_c, engrave_c, tp)
    else:
        _ef_nameplate(d, cx, cy, R, outline_c, f_mid, tone)
    # 四条注记的落点取自实测带（`ef_layer_geom.CORNER`，素材角部注记暗元 u/v 分位）：
    # 旧坐标有 3 条画在章体外被裁掉、第 4 条在章内但在验收 bin 外（存活率全 0.000）。
    for x, y, s in _ef_corner_origins(cx, cy, R):
        _ef_corner_annotation(d, x, y, s, corner_c, EF_CORNER_SIZE)

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

    # ---- 裁回章体 + 细颗粒 ----
    keep_mask = Image.new("L", (CW, CH), 0)
    kd = ImageDraw.Draw(keep_mask)
    kd.polygon(_hex_pts(cx, cy, R - 3), fill=255)   # 三家族轮廓统一正六边形，无外凸件
    clean = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    clean.paste(canvas, (0, 0), keep_mask)
    canvas = clean
    rng = np.random.default_rng(7)
    n = rng.integers(-4, 5, (CH, CW, 1), dtype=np.int16)
    arr = np.asarray(canvas.convert("RGB"), dtype=np.int16) + n
    noisy = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    # 章体剪影一律硬边正六边形。不能用 `canvas.getchannel("A")`：ImageDraw 画半透明笔画时
    # 是把 fill 的 alpha **写进** alpha 通道（不是叠加），内发丝线 (…,110) 因此在 R-16 处
    # 留下一条 <127 的「假透明缝」⇒ alpha 被切成外环 + 本体两块，量测器 `alpha>127` 口径下
    # 的 `edge` bin 从 6px 变成 14px（逐次腐蚀前 6 圈各吃掉 7~9k 像元，本体周边只有 2.9k），
    # 于是描边电平永远读不回来（计划 §2.1-h）。
    noisy.putalpha(keep_mask)
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


def _brushed_streaks(size, theta_deg, count=240, alpha=16):
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
        shade = 255 if rng.random() < 0.55 else 0
        a = int(alpha * rng.uniform(0.5, 1.0))
        d.line([(sx + px * off, sy + py * off),
                (sx + dx * ln + px * off, sy + dyv * ln + py * off)],
               fill=(shade, shade, shade, a), width=1)
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
            ai = ai_matting(src) if ai_matting_enabled() else None
            if ai is not None:
                subject = ai
                cov = None
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
            face = etch_face(subject, tone=face_tone, line_strength=line_strength,
                             detail=detail, mode=eff_mode)
            if carve == "hand":
                from emblem_render import carve_texture
                face = carve_texture(face, "hand")

    if style == "endfield":
        out = compose_endfield(face, text, subtitle, serial, tone, number,
                               fam=endfield_family)
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
    """迭代会话目录：<repo>/output/projects/<安全名>/。产物自动编号，支持"上一轮改一改"。"""
    import re as _re
    safe = _re.sub(r"[^\w\-]+", "_", project).strip("_") or "default"
    d = os.path.join(os.path.dirname(root), "output", "projects", safe)
    os.makedirs(d, exist_ok=True)
    return d


def _archive_round(proj_dir, n, style, tone, args, warn, design_path=None):
    """把本轮参数/告警/设计稿归档进会话目录（n 由调用方在生成 PNG 前算好，保证一致）。"""
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
                    help="方舟: silver(普通)|plated(镀层)|gold(活动金章)；终末地: silver(银)|gold_pure/pure(纯金)|gold(镀彩金)|dark(排名)|bronze(铜阶)|pearl(镀层)")
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
