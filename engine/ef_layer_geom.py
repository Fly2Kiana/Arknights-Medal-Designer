# -*- coding: utf-8 -*-
"""ef_layer_geom.py · 装饰四层的落笔几何：**单一事实源**

引擎按这张表画，量测按这张表算「存活率」，于是「画在哪」与「验在哪」不可能各说各话。

由来：
本地量测脚本的 check 档在渲染件上复用**素材侧**那套 bin（`plate` = v −0.70~-0.40、
`corner` = |u| 0.40~0.85 且 v −0.62~-0.22），而旧引擎把铭牌画在 v −0.877~-0.702、把四条角部
注记画在 |u|≈0.93（其中三条干脆落在章体外被 `keep_mask` 裁掉）⇒ 那两格量到的是**裸色场**，
「过」是必然的。几何进了这张表之后，bin 包不住笔画这件事会被存活率当场量出来，而不是靠人
翻代码比区间。

坐标口径：`compose_endfield` 的规范画布 `CW,CH = 1000,1240`、圆心 `(500,620)`、`R = 470`。
表里登记的是**相对圆心的像素偏移**（渲染侧只管加减），换算成章内归一 `u,v`（右 `u+`、下 `v+`，
单位 `R`）由 `uv_box()` 负责 —— 因为 `u = (x-cx)/R`，规范偏移除以规范 R 即得，与渲染件被
等比放大到多少无关（纪律 ⑦ 归一后 R=470，两者本就重合）。
"""

CX, CY, R_CANON = 500, 620, 470
CW_CANON, CH_CANON = 1000, 1240      # 规范画布尺寸（badge_engine.compose_endfield:1170）

# ---- 顶部铭牌（车牌式圆角框 + 四角铆钉 + 顶点空心三角）----
# 数值 = 建表前 `_ef_nameplate` 里的字面量，逐项对得上：板宽 168 → dx ±84；
# 板顶 cy-R+58 = cy-412；板高 82 → 板底 dy1 = -330；三角顶点 cy-R+4 = cy-466。
# `stroke`/`tri_width` = 2026-10-07 引擎轨补进来的两笔：原先是 `_ef_nameplate` 里的裸字面量
# （width=6 / width=4），掩膜要「只从表生成」就绕不过它们 ⇒ 进表，引擎改读表（等价搬迁的到位
# 判定 = 全矩阵渲染逐字节相同）。
PLATE = dict(dx0=-84, dy0=-412, dx1=84, dy1=-330, radius=14,
             rivet_inset=13, rivet_r=5, apex_dy=-466, tri_half_w=12, tri_h=34,
             stroke=6, tri_width=4)

# ---- 四条角部工程注记：(中心 u, 中心 v, 文案)，单位 = R，右 u+ / 下 v+ ----
# 落点来自素材实测（`corner` bin 内过 `T_STROKE` 绝对档的暗元像元分位，73 枚 / 10.0 万像元，
# p10~p90 = |u| 0.70~0.71 与 v −0.53~−0.27，**全在章面上半的左右两侧带**。
# 旧落点 `(-436,-410)/(340,-410)/(-436,+40)/(360,+40)` 四条一条不在这个带里，其中三条
# 干脆在章体外被裁掉（存活率 0.000）。中心口径由 `corner_origins()` 用真字体反解成锚点。
CORNER = [(-0.66, -0.50, "+001-E-1908"),
          (0.55, -0.50, "×‖×"),
          (-0.72, -0.35, "××+"),      # 外移：|u|=0.55 会压在 industry 左上圆盘表扣上（目检抓到）
          (0.66, -0.35, "+··+")]
CORNER_SIZE = 13

# 这一层的检测 bin 名（存活率按 bin 分组报）
INK_BINS = ("plate", "corner")

# ---- 注记「局部背景」环带的口径：取色圈 = 深度尺的读数圈 ----
# 引擎落笔前取的那圈背景（`badge_engine._ef_annot_bg`）和深度尺量的那圈背景
# （本地量测脚本的 RING_IN/RING_OUT，值原样搬来、一字未改）必须是同一个几何，
# 否则「按局部电平喂色」改完，量测的却是另一块地皮 ⇒ 改动与验收对不上号。
ANNOT_SKIP = 1            # 紧贴笔画的 1 px 不算背景（抗锯齿边属笔画，不属章面）
ANNOT_PAD = 9             # 环带外沿 = 掩膜向外长 9 px（环带厚度 8 px）


def dilate_px(mask, px):
    """bool 掩膜向外长 `px` 像素（形态学膨胀 = MaxFilter 直径 2px+1）"""
    import numpy as np
    from PIL import Image, ImageFilter
    im = Image.fromarray(np.asarray(mask).astype(np.uint8) * 255)
    return np.asarray(im.filter(ImageFilter.MaxFilter(2 * int(px) + 1))) > 127


def annot_ring(mask, skip=ANNOT_SKIP, pad=ANNOT_PAD):
    """注记的背景环带 = 掩膜外 `pad` 圈剔掉贴笔的 `skip` 圈

    `skip`/`pad` 只给深度尺的扰动档（留白平移）传替身值用；常驻调用一律用本表两个常数。
    """
    return dilate_px(mask, pad) & ~dilate_px(mask, skip)


def plate_boxes():
    """铭牌层的落笔包围盒（规范画布像素）→ [(x0, y0, x1, y1), ...]

    只取外框 + 铆钉 + 三角三块；框内的刻字属 `plate` 的另一半（判「不可单常数化」），
    默认不喂色，故不计入存活率。
    """
    p = PLATE
    out = [(CX + p["dx0"], CY + p["dy0"], CX + p["dx1"], CY + p["dy1"])]
    half_w, half_h = (p["dx1"] - p["dx0"]) / 2.0, (p["dy1"] - p["dy0"]) / 2.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            rx = CX + sx * (half_w - p["rivet_inset"])
            ry = CY + p["dy0"] + half_h + sy * (half_h - p["rivet_inset"])
            r = p["rivet_r"]
            out.append((rx - r, ry - r, rx + r, ry + r))
    aw = p["tri_half_w"]
    out.append((CX - aw, CY + p["apex_dy"], CX + aw, CY + p["apex_dy"] + p["tri_h"]))
    return out


def _corner_font():
    """注记用的真字体（与 `_ef_corner_annotation` 同一支、同一字号）——
    宽度必须现量，写死就会漂：换文案/换字号时表还指着旧宽度，存活率跟着说谎。"""
    from badge_engine import load_font, FONT_MONO, FONT_EN_BLACK, FONT_CN
    return load_font(FONT_MONO or FONT_EN_BLACK or FONT_CN, CORNER_SIZE or 14)


def corner_origins(cx=CX, cy=CY, R=R_CANON, corner=None):
    """四条注记的**绘制锚点**（左基线）→ [(x, y, 文案), ...]

    表里给的是「注记块的中心该落在哪」，而 `d.text()` 吃的是左基线锚点 ⇒ 用真字体包围盒
    把中心反解成锚点。字号不随 R 缩放（引擎一直按 13px 画），只平移。
    `corner` 只给扰动档（M-2d）用：传入替身表 ⇒ 不许用来喂常驻值。
    """
    f = _corner_font()
    out = []
    for uc, vc, s in (CORNER if corner is None else corner):
        b = f.getbbox(s)                        # 相对 (0,0) 按默认锚点绘制时的包围盒
        cx_px = cx + uc * R - (b[0] + b[2]) / 2.0
        cy_px = cy + vc * R - (b[1] + b[3]) / 2.0
        out.append((cx_px, cy_px, s))
    return out


def corner_boxes(corner=None):
    """四条注记的文字包围盒（规范画布像素）"""
    f = _corner_font()
    out = []
    for cx_px, cy_px, s in corner_origins(corner=corner):
        b = f.getbbox(s)
        out.append((cx_px + b[0], cy_px + b[1], cx_px + b[2], cy_px + b[3]))
    return out


def uv_box(x0, y0, x1, y1):
    """规范画布像素 → 章内归一 (u0, v0, u1, v1)：右 u+、下 v+，单位 R"""
    return ((x0 - CX) / R_CANON, (y0 - CY) / R_CANON,
            (x1 - CX) / R_CANON, (y1 - CY) / R_CANON)


def ink_uv(layer):
    """某一层的全部落笔区域（uv 口径）→ [(u0,v0,u1,v1), ...]"""
    boxes = plate_boxes() if layer == "plate" else corner_boxes()
    return [uv_box(*b) for b in boxes]


# ============================================================ 应然落笔掩膜（引擎轨 2026-10-07）
# 一句话口径：**这一层"该落的像元"是哪些** —— 只按本表的参数在空白画布上描一遍。
# 它存在的唯一理由：差分落笔的本地量测脚本（A 档）原先拿「落笔包围盒整框面积」
# 当分母，量到的是"这一笔占框多大"（美术口径），于是 `plate` 的结构上限只有 ≈0.28，
# 绝对线 ≥0.50 永远打不到 —— 纪律 ⑳ 点名的就是这件事。
#
# **为什么不许调 `badge_engine._ef_nameplate` 来生成掩膜**：压层档就是把那个函数换成 no-op，
# 拿引擎自己的输出当真值 ⇒ 「正常 vs 压本层」的墨迹必然落在掩膜里，读数退化成定理（纪律 ⑲）。
# 所以下面这套绘制调用是**故意写的第二套实现**：与引擎共读同一张表，但不共读代码。
# 残留盲区：`stroke`/`tri_width` 进了表之后，"引擎描边比表细/粗"掩膜检不出
# （两侧同时变）⇒ 等价性由 M-1b 的全矩阵逐字节承担，过画由墨迹外溢率承担。


def _draw_plate_mask(d, p, cx=CX, cy=CY):
    """铭牌该落的像元：圆角框环带 + 四枚实心铆钉 + 顶点三角环带（数值全取自 `PLATE`）"""
    x0, y0, x1, y1 = cx + p["dx0"], cy + p["dy0"], cx + p["dx1"], cy + p["dy1"]
    d.rounded_rectangle([x0, y0, x1, y1], radius=p["radius"], outline=255, width=p["stroke"])
    half_w, half_h = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    ins, rr = p["rivet_inset"], p["rivet_r"]
    for sx in (-1, 1):
        for sy in (-1, 1):
            rx = cx + sx * (half_w - ins)
            ry = y0 + half_h + sy * (half_h - ins)
            d.ellipse([rx - rr, ry - rr, rx + rr, ry + rr], fill=255)
    aw = p["tri_half_w"]
    apex = cy + p["apex_dy"]
    d.polygon([(cx, apex), (cx - aw, apex + p["tri_h"]), (cx + aw, apex + p["tri_h"])],
              outline=255, width=p["tri_width"])


def should_mask_canvas(layer, plate=None, corner=None, size=None):
    """某一层在**规范画布**上的应然落笔掩膜 → (H, W) 的 bool 数组

    `plate`/`corner` 只给扰动档（M-2d）传替身表用；常驻调用一律用本表。
    `lowdot` 没有掩膜：网点周期与占空比无实测数 ⇒ 直接抛错，不许拿框面积冒充分母（计划 M-4）。
    """
    import numpy as np
    from PIL import Image, ImageDraw
    if layer not in INK_BINS:
        raise ValueError("只有 %s 两层建得起应然掩膜（lowdot 的周期/占空未实测 ⇒ 判「不可验」）"
                         % "/".join(INK_BINS))
    w, h = size or (CW_CANON, CH_CANON)
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    if layer == "plate":
        _draw_plate_mask(d, PLATE if plate is None else plate)
    else:
        f = _corner_font()
        for x, y, s in corner_origins(corner=corner):
            d.text((x, y), s, font=f, fill=255)
    return np.asarray(im) > 127


def mask_selftest():
    """掩膜非空、且**严格小于**落笔框并集（否则换分母 = 没换）"""
    import numpy as np
    print("=== M-1a 应然掩膜自测（规范画布 %d×%d）：非空 + 严格小于落笔框并集 ==="
          % (CW_CANON, CH_CANON))
    rc = 0
    for layer in INK_BINS:
        m = should_mask_canvas(layer)
        boxes = plate_boxes() if layer == "plate" else corner_boxes()
        bm = np.zeros(m.shape, bool)
        for x0, y0, x1, y1 in boxes:
            bm[max(0, int(round(y0))):int(round(y1)) + 1,
               max(0, int(round(x0))):int(round(x1)) + 1] = True
        n_m, n_b = int(m.sum()), int(bm.sum())
        out = int((m & ~bm).sum())
        ok = 0 < n_m < n_b
        rc = rc or (0 if ok else 1)
        print("  %-7s 掩膜 %6d px  框并集 %6d px  掩膜/框 %.3f  框外像元 %5d（%.4f）⇒ %s"
              % (layer, n_m, n_b, n_m / float(n_b), out, out / float(max(n_m, 1)),
                 "过" if ok else "不过"))
    print("  ⇒ M-1a 判语：%s（比值就是「换分母换掉了多少」，越小说明原分母虚得越多）"
          % ("过" if rc == 0 else "不过"))
    return rc


if __name__ == "__main__":
    import sys
    if "--maskselftest" in sys.argv[1:]:
        sys.exit(mask_selftest())
    print("给 --maskselftest（见文件头）")
    sys.exit(2)
