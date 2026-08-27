# -*- coding: utf-8 -*-
"""
纹章渲染器 v2 · Emblem Renderer
================================
把视觉模型设计的几何图元 JSON 渲染成章面，支持社区美术语言：
- style='flat'   实心填充 + 粗描边（矢量风）
- style='lineart' 社区主流：细线描 + 排线/交叉线阴影（0.55 区单排线，0.22 区交叉排线）
- polarity='dark-on-light' 浅底深线（社区主流·银底暗线）
- polarity='light-on-dark' 深底浅线（官方高对比款）
- carve='machine'|'hand'  机器刻（锐利均匀）vs 手工刻（线宽抖动+边缘毛糙+金石味）
- tone='stamp' 朱砂印章色板
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import badge_engine as be

STAMP_PAL = ((118, 32, 18), (178, 62, 36), (226, 108, 72))   # 朱砂三档


def _lum_color(lum, pal, polarity):
    if polarity == "dark-on-light":
        lum = 1.0 - lum        # 翻转：低明度→亮墨
    dark, mid, bright = pal
    if lum <= 0.4:
        x = max(0.0, min(1.0, (lum - 0.22) / (0.55 - 0.22)))
        return tuple(int(dark[i] + (mid[i] - dark[i]) * x) for i in range(3))
    x = max(0.0, min(1.0, (lum - 0.55) / (0.88 - 0.55)))
    return tuple(int(mid[i] + (bright[i] - mid[i]) * x) for i in range(3))


def _hatch_mask(lum_map, ink, canvas_px, period=(16, 10)):
    """明度分区转纹理：0.55→定向排线，0.22→speckle 颗粒点（参考图的蚀刻颗粒）"""
    img = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p1, p2 = period
    w = max(2, int(canvas_px * 0.0028))
    th1 = math.radians(30)
    a = np.asarray(lum_map)
    single = (a >= 0.40) & (a < 0.80)
    both = (a > 0.15) & (a < 0.40)
    # 单排线层（0.55 区）
    layer1 = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld1 = ImageDraw.Draw(layer1)
    for y in range(0, canvas_px, p1):
        ld1.line([(0, y), (canvas_px, int(y + canvas_px * math.tan(th1)) % canvas_px)],
                 fill=ink + (255,), width=w)
    layer1.putalpha(Image.fromarray(np.where(single, 255, 0).astype(np.uint8), "L"))
    # speckle 颗粒层（0.22 暗区）
    rng = np.random.default_rng(42)
    dots = rng.random((canvas_px // 4, canvas_px // 4))
    ds = 4
    layer2 = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld2 = ImageDraw.Draw(layer2)
    rr = max(1, int(canvas_px * 0.0016))
    for gy in range(dots.shape[0]):
        for gx in range(dots.shape[1]):
            if dots[gy, gx] < 0.55:
                x, y = gx * ds, gy * ds
                ld2.ellipse([x - rr, y - rr, x + rr, y + rr], fill=ink + (220,))
    layer2.putalpha(Image.fromarray(np.where(both, 255, 0).astype(np.uint8), "L"))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(layer1)
    out.alpha_composite(layer2)
    return out


def carve_texture(face, kind="machine"):
    """刻痕质感：machine=保持锐利；hand=边缘毛糙+金石抖动"""
    if kind == "machine":
        return face
    a = np.asarray(face.getchannel("A"), dtype=np.float32)
    rng = np.random.default_rng(9)
    # 随机斑驳：少量边缘减损
    n = rng.random(a.shape)
    a2 = a.copy()
    edge = (a > 0) & (a < 255)
    a2[edge & (n < 0.05)] *= 0.45
    a2[edge & (n > 0.97)] = np.minimum(255, a2[edge & (n > 0.97)] * 1.15)
    face.putalpha(Image.fromarray(a2.astype(np.uint8), "L"))
    # 整体轻微钝化
    return face.filter(ImageFilter.GaussianBlur(0.5))


def _auto_materialize(shapes, canvas_px):
    """把纯描边设计稿铸成有体积的纹章明度图：
    闭合轮廓→灌中调；描边邻域→暗区；线密度高→暗。"""
    from collections import deque
    stroke_img = Image.new("L", (canvas_px, canvas_px), 0)
    sd = ImageDraw.Draw(stroke_img)
    for s in shapes:
        t = s.get("t")
        w = max(6, int((s.get("w") or 12) * canvas_px / 1000 * 0.6))
        if t == "poly" and s.get("pts"):
            pts = [tuple(p) for p in s["pts"]]
            if s.get("fill") is None and s.get("stroke") is not None:
                sd.polygon(pts, outline=255, width=w)
        elif t == "circle" and s.get("cx") is not None:
            cx, cy, r = s["cx"], s["cy"], s["r"]
            if s.get("fill") is None and s.get("stroke") is not None:
                sd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=255, width=w)
        elif t == "rect" and s.get("x0") is not None:
            if s.get("fill") is None and s.get("stroke") is not None:
                sd.rectangle([s["x0"], s["y0"], s["x1"], s["y1"]], outline=255, width=w)
        elif t == "line":
            sd.line([(s["x1"], s["y1"]), (s["x2"], s["y2"])], fill=255, width=w)
        elif t == "arc":
            cx, cy, r = s["cx"], s["cy"], s["r"]
            sd.arc([cx - r, cy - r, cx + r, cy + r],
                   start=float(s.get("a0", 0)), end=float(s.get("a1", 360)),
                   fill=255, width=w)

    m = np.asarray(stroke_img) > 0
    h, w = m.shape
    outside = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not m[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not m[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not m[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                q.append((ny, nx))
    interior = ~outside          # 闭合区域 + 描边本体
    # 线密度场：近描边/密集区 → 暗
    dens = np.asarray(stroke_img, np.float32) / 255.0
    dens_img = Image.fromarray((np.clip(dens, 0, 1) * 255).astype(np.uint8), "L")
    dens = np.asarray(dens_img.filter(ImageFilter.GaussianBlur(7)),
                      dtype=np.float32) / 255.0
    lum = np.where(interior,
                   np.where(m, 0.22, np.clip(0.58 - dens * 1.4, 0.22, 0.58)),
                   0.0).astype(np.float32)
    return lum


def _sample_bezier(p0, p1, p2, p3, n=48):
    pts = []
    for i in range(n + 1):
        t = i / n
        x = ((1 - t) ** 3) * p0[0] + 3 * ((1 - t) ** 2) * t * p1[0] \
            + 3 * (1 - t) * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = ((1 - t) ** 3) * p0[1] + 3 * ((1 - t) ** 2) * t * p1[1] \
            + 3 * (1 - t) * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        pts.append((x, y))
    return pts


def _draw_ornament(d, s, lum_color, canvas_px):
    """纹章装饰原语：bezier/star/sunburst/laurel/banner"""
    t = s.get("t")
    w = max(3, int((s.get("w") or 10) * canvas_px / 1000))
    sc = lum_color(float(s.get("stroke") or 0.22), s)
    if t == "bezier":
        pts = _sample_bezier(tuple(s["p0"]), tuple(s["p1"]), tuple(s["p2"]),
                             tuple(s["p3"]))
        if s.get("fill") is not None:
            d.polygon(pts + [pts[0]], fill=sc)
        else:
            d.line(pts, fill=sc, width=w, joint="curve")
    elif t == "star":
        cx, cy = s["cx"], s["cy"]
        r1, r2 = s.get("r1", s.get("r", 30)), s.get("r2", s.get("r1", 30) * 0.45)
        n = int(s.get("points", 5))
        rot = math.radians(float(s.get("rot", -90)))
        pts = []
        for i in range(n * 2):
            rr = r1 if i % 2 == 0 else r2
            ang = rot + math.pi * i / n
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        d.polygon(pts, fill=sc if s.get("fill") is not None else None,
                  outline=sc, width=w)
    elif t == "sunburst":
        cx, cy = s["cx"], s["cy"]
        r0, r1 = s.get("r0", 40), s.get("r1", 160)
        n = int(s.get("count", 16))
        for i in range(n):
            ang = math.radians(360.0 * i / n + float(s.get("rot", 0)))
            x0 = cx + r0 * math.cos(ang)
            y0 = cy + r0 * math.sin(ang)
            x1 = cx + (r1 if i % 2 == 0 else r1 * 0.72) * math.cos(ang)
            y1 = cy + (r1 if i % 2 == 0 else r1 * 0.72) * math.sin(ang)
            d.line([(x0, y0), (x1, y1)], fill=sc, width=w)
    elif t == "laurel":
        # 弧形月桂枝：茎 + 交替小叶
        cx, cy = s["cx"], s["cy"]
        length = s.get("length", 220)
        ang0 = math.radians(float(s.get("angle", 45)))
        n = int(s.get("branches", 8))
        stem = []
        for i in range(n + 1):
            t2 = i / n
            ang = ang0 + t2 * 1.9
            stem.append((cx + length * t2 * math.cos(ang),
                         cy + length * t2 * math.sin(ang)))
        d.line(stem, fill=sc, width=w, joint="curve")
        for i in range(1, n):
            bx, by = stem[i]
            t2 = i / n
            ang = ang0 + t2 * 1.9
            for side in (-1, 1):
                la = ang + side * math.pi / 2 + 0.35 * side
                lx = bx + 26 * math.cos(la)
                ly = by + 26 * math.sin(la)
                d.ellipse([lx - 12, ly - 6, lx + 12, ly + 6],
                          fill=sc if s.get("fill") is not None else None,
                          outline=sc, width=max(2, w - 2))
    elif t == "banner":
        x0, y0 = s["x0"], s["y0"]
        x1, y1 = s["x1"], s["y1"]
        if abs(y1 - y0) < 4:
            y1 = y0 + 96
        fold = s.get("fold", 26)
        # 主体 + 燕尾缺口
        pts = [(x0, y0), (x1, y0), (x1 - fold, (y0 + y1) / 2),
               (x1, y1), (x0, y1)]
        d.polygon(pts, fill=sc if s.get("fill") is not None else None,
                  outline=sc, width=w)
        d.line([(x0, (y0 + y1) / 2), (x1 - fold, (y0 + y1) / 2)],
               fill=sc, width=max(2, w - 2))


def _normalize_shapes(shapes):
    """兼容视觉模型可能产出的多种图元格式"""
    out = []
    for s in shapes:
        t = s.get("t")
        if not t:
            # 从字段推断类型
            if "pts" in s:
                t = "poly"
            elif "cx" in s and "r" in s:
                t = "arc" if "a0" in s or "a1" in s else "circle"
            elif "x1" in s:
                t = "line"
            elif "x" in s or "x0" in s:
                t = "rect"
            else:
                continue
        ns = dict(s)
        ns["t"] = t
        # pts 字符串 "x,y x,y ..." → [[x,y],...]
        if isinstance(ns.get("pts"), str):
            pts = []
            for tok in ns["pts"].split():
                try:
                    x, y = tok.split(",")
                    pts.append([float(x), float(y)])
                except ValueError:
                    pass
            ns["pts"] = pts
        # rect 用 x/y/w/h
        if t == "rect" and "x" in ns and "x0" not in ns:
            ns["x0"] = float(ns.pop("x"))
            ns["y0"] = float(ns.pop("y", ns["y0"] if "y0" in ns else 0))
            ns["x1"] = ns["x0"] + float(ns.pop("w", 0))
            ns["y1"] = ns["y0"] + float(ns.pop("h", 0))
        # arc 角度字段别名
        if "a0" not in ns and "a1" in ns and "a2" in ns:
            ns["a0"], ns["a1"] = float(ns["a1"]), float(ns["a2"])
        # line 用 stroke 表示线色
        if t == "line" and "lum" not in ns and ns.get("stroke") is not None:
            ns["lum"] = ns["stroke"]
        # 数值归一
        for k in ("fill", "stroke", "lum"):
            if k in ns:
                v = ns[k]
                if isinstance(v, str) or v is None:
                    ns[k] = None
                else:
                    ns[k] = float(v)
        out.append(ns)
    return out


def render_emblem(design_json, tone="silver", canvas_px=1000, style="lineart",
                  polarity="dark-on-light", carve="machine"):
    data = json.loads(design_json)
    shapes = _normalize_shapes(data.get("shapes", []))
    pal = STAMP_PAL if tone == "stamp" else be.PALETTES.get(tone, be.PALETTES["silver"])
    ink = _lum_color(0.22, pal, polarity)

    # 1) 明度分区图（只有 fill，无描边）
    lum_map = np.zeros((canvas_px, canvas_px), dtype=np.float32)
    for s in shapes:
        t = s.get("t")
        fill = s.get("fill")
        if fill is None:
            continue
        tmp = Image.new("L", (canvas_px, canvas_px), 0)
        d0 = ImageDraw.Draw(tmp)
        if t == "poly":
            d0.polygon([tuple(p) for p in s["pts"]], fill=255)
        elif t == "circle":
            cx, cy, r = s["cx"], s["cy"], s["r"]
            d0.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
        elif t == "rect":
            d0.rectangle([s["x0"], s["y0"], s["x1"], s["y1"]], fill=255)
        else:
            continue
        m = np.asarray(tmp) > 127
        lum_map[m] = float(fill)

    # 填充覆盖率过低（纯描边稿）→ 自动铸体
    fill_cov = float((lum_map > 0).mean())
    if style == "lineart" and fill_cov < 0.25:
        auto = _auto_materialize(shapes, canvas_px)
        lum_map = np.maximum(lum_map, auto)
        if float((auto > 0).mean()) < 0.05:
            m_stroke = auto == 0.22
            if m_stroke.any():
                thick = Image.fromarray((m_stroke * 255).astype(np.uint8), "L").filter(
                    ImageFilter.MaxFilter(7))
                lum_map = np.maximum(lum_map,
                                     np.where(np.asarray(thick) > 0, 0.30, 0.0)
                                     .astype(np.float32))

    # 金属体积：铸体内上亮下暗的明度渐变（上缘受光、下缘背光）
    yy = np.linspace(0.0, 1.0, canvas_px)[:, None].astype(np.float32)
    interior = lum_map > 0.10
    if interior.any():
        bevel = (0.5 - yy) * 0.18
        lum_map = np.clip(np.where(interior, lum_map + bevel, 0.0), 0.0, 0.95)

    # 2) 输出层
    out = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    if style == "lineart":
        # 0.88 亮区 = 蚀刻镂空（完全透明，让章底透出），只保留排线/颗粒暗区与描边
        out.alpha_composite(_hatch_mask(lum_map, ink, canvas_px))
    else:
        tmp = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
        dfl = ImageDraw.Draw(tmp)
        for s in shapes:
            t = s.get("t")
            fill = s.get("fill")
            if fill is None or t not in ("poly", "circle", "rect"):
                continue
            col = _lum_color(float(fill), pal, polarity) + (255,)
            if t == "poly":
                dfl.polygon([tuple(p) for p in s["pts"]], fill=col)
            elif t == "circle":
                cx, cy, r = s["cx"], s["cy"], s["r"]
                dfl.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
            elif t == "rect":
                dfl.rectangle([s["x0"], s["y0"], s["x1"], s["y1"]], fill=col)
        out.alpha_composite(tmp)

    # 3) 描边层（细线 + 蚀刻刻槽：light-on-dark 白线下衬暗槽，线如刻进金属）
    sd = ImageDraw.Draw(out)
    lam = lambda lum, _s=None: _lum_color(float(lum), pal, polarity)
    engrave = (polarity == "light-on-dark" and style == "lineart")
    shc = (18, 24, 32, 150)
    for s in shapes:
        t = s.get("t")
        if t in ("bezier", "star", "sunburst", "laurel", "banner"):
            _draw_ornament(sd, s, lam, canvas_px)
            continue
        w = max(3, int((s.get("w") or 12) * canvas_px / 1000 * (0.45 if style == "lineart" else 1.0)))
        stroke = s.get("stroke")
        sc = _lum_color(float(stroke), pal, polarity) + (255,) if stroke is not None else None
        if t == "poly" and s.get("pts"):
            pts = [tuple(p) for p in s["pts"]]
            if sc:
                if engrave:
                    sd.polygon([(x + 2, y + 2) for x, y in pts], outline=shc, width=w)
                sd.polygon(pts, outline=sc, width=w)
        elif t == "circle":
            cx, cy, r = s["cx"], s["cy"], s["r"]
            if sc:
                if engrave:
                    sd.ellipse([cx - r + 2, cy - r + 2, cx + r + 2, cy + r + 2],
                               outline=shc, width=w)
                sd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=sc, width=w)
        elif t == "rect":
            if sc:
                if engrave:
                    sd.rectangle([s["x0"] + 2, s["y0"] + 2, s["x1"] + 2, s["y1"] + 2],
                                 outline=shc, width=w)
                sd.rectangle([s["x0"], s["y0"], s["x1"], s["y1"]], outline=sc, width=w)
        elif t == "line":
            lum = s.get("lum", 0.22)
            c = _lum_color(float(lum), pal, polarity) + (255,)
            if engrave:
                sd.line([(s["x1"] + 2, s["y1"] + 2), (s["x2"] + 2, s["y2"] + 2)],
                        fill=shc, width=w)
            sd.line([(s["x1"], s["y1"]), (s["x2"], s["y2"])], fill=c, width=w)
        elif t == "arc":
            cx, cy, r = s["cx"], s["cy"], s["r"]
            a0, a1 = s.get("a0", 0), s.get("a1", 360)
            lum = s.get("lum", s.get("stroke", 0.88)) or 0.88
            c = _lum_color(float(lum), pal, polarity) + (255,)
            if engrave:
                sd.arc([cx - r + 2, cy - r + 2, cx + r + 2, cy + r + 2],
                       start=float(a0), end=float(a1), fill=shc, width=w)
            sd.arc([cx - r, cy - r, cx + r, cy + r], start=float(a0), end=float(a1),
                   fill=c, width=w)

    out = carve_texture(out, carve)

    # 糖果贴纸：白色贴纸描边 + 贴纸凸起（软投影+奶白高光）
    if tone == "candy":
        a = out.getchannel("A")
        big = a.filter(ImageFilter.MaxFilter(15))
        ring = ImageChops.subtract(big, a)
        white = Image.new("RGBA", out.size, (255, 253, 246, 255))
        white.putalpha(ring.filter(ImageFilter.GaussianBlur(1)))
        # 右下软投影（焦糖色）
        sh_a = ImageChops.subtract(ImageChops.offset(a, 10, 10), a)
        shadow = Image.new("RGBA", out.size, (160, 108, 84, 255))
        shadow.putalpha(sh_a.filter(ImageFilter.GaussianBlur(2.5)))
        # 左上奶白高光（贴纸厚度感）
        hl_a = ImageChops.subtract(ImageChops.offset(a, -8, -8), a)
        hl = Image.new("RGBA", out.size, (255, 255, 250, 255))
        hl.putalpha(hl_a.filter(ImageFilter.GaussianBlur(2)))
        base = Image.new("RGBA", out.size, (0, 0, 0, 0))
        base.alpha_composite(shadow)
        base.alpha_composite(white)
        base.alpha_composite(out)
        base.alpha_composite(hl)
        out = base

    # 裁到内容
    bbox = out.getchannel("A").getbbox()
    if bbox:
        l, t, r, b = bbox
        pad = max(20, int((r - l) * 0.05))
        l, t = max(0, l - pad), max(0, t - pad)
        r, b = min(canvas_px, r + pad), min(canvas_px, b + pad)
        out = out.crop((l, t, r, b))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("design_json")
    ap.add_argument("-o", "--output", default="emblem_out.png")
    ap.add_argument("--tone", default="silver")
    ap.add_argument("--style", default="lineart", choices=["lineart", "flat"])
    ap.add_argument("--polarity", default="dark-on-light",
                    choices=["dark-on-light", "light-on-dark"])
    ap.add_argument("--carve", default="machine", choices=["machine", "hand"])
    ap.add_argument("--badge", action="store_true")
    ap.add_argument("--style-game", default="arknights")
    ap.add_argument("--text", default="蚀刻勋章")
    ap.add_argument("--number", default="")
    args = ap.parse_args()

    with open(args.design_json, encoding="utf-8-sig") as f:
        design = f.read().strip()
    face = render_emblem(design, tone=args.tone, style=args.style,
                         polarity=args.polarity, carve=args.carve)
    if args.badge:
        if args.style_game == "endfield":
            out = be.compose_endfield(face, args.text, "", "", args.tone, args.number)
        else:
            out = be.compose_arknights(face, args.text, "", "",
                                       "gold" if args.tone == "gold" else
                                       ("stamp" if args.tone == "stamp" else "silver"),
                                       args.number)
        out.save(args.output)
    else:
        face.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
