# -*- coding: utf-8 -*-
"""ef_layer_geom.py · 装饰四层的落笔几何：**单一事实源**

引擎按这张表画，复测按这张表算「存活率」，于是「画在哪」与「验在哪」不可能各说各话。

由来：
复测在渲染件上复用**素材侧**那套分带（`plate` = v −0.70~-0.40、
`corner` = |u| 0.40~0.85 且 v −0.62~-0.22），而旧引擎把铭牌画在 v −0.877~-0.702、把四条角部
注记画在 |u|≈0.93（其中三条干脆落在章体外被 `keep_mask` 裁掉）⇒ 那两格量到的是**裸色场**，
「过」是必然的。几何进了这张表之后，bin 包不住笔画这件事会被存活率当场量出来，而不是靠人
翻代码比区间。

坐标口径：`compose_endfield` 的规范画布 `CW,CH = 1000,1240`、圆心 `(500,620)`、`R = 470`。
表里登记的是**相对圆心的像素偏移**（渲染侧只管加减），换算成章内归一 `u,v`（右 `u+`、下 `v+`，
单位 `R`）由 `uv_box()` 负责 —— 因为 `u = (x-cx)/R`，规范偏移除以规范 R 即得，与渲染件被
等比放大到多少无关（按素材 R 中位归一到 R=470，两者本就重合）。
"""

CX, CY, R_CANON = 500, 620, 470

# ---- 顶部铭牌（车牌式圆角框 + 四角铆钉 + 顶点空心三角）----
# 数值 = 建表前 `_ef_nameplate` 里的字面量，逐项对得上：板宽 168 → dx ±84；
# 板顶 cy-R+58 = cy-412；板高 82 → 板底 dy1 = -330；三角顶点 cy-R+4 = cy-466。
PLATE = dict(dx0=-84, dy0=-412, dx1=84, dy1=-330, radius=14,
             rivet_inset=13, rivet_r=5, apex_dy=-466, tri_half_w=12, tri_h=34)

# ---- 四条角部工程注记：(中心 u, 中心 v, 文案)，单位 = R，右 u+ / 下 v+ ----
# 落点来自素材实测（`corner` bin 内过 `T_STROKE` 绝对档的暗元像元分位，73 枚 / 10.0 万像元，
# 素材实测的分位）：p10~p90 = |u| 0.70~0.71 与 v −0.53~−0.27，**全在章面上半的左右两侧带**。
# 旧落点 `(-436,-410)/(340,-410)/(-436,+40)/(360,+40)` 四条一条不在这个带里，其中三条
# 干脆在章体外被裁掉（存活率 0.000）。中心口径由 `corner_origins()` 用真字体反解成锚点。
CORNER = [(-0.66, -0.50, "+001-E-1908"),
          (0.55, -0.50, "×‖×"),
          (-0.72, -0.35, "××+"),      # 外移：|u|=0.55 会压在 industry 左上圆盘表扣上（目检抓到）
          (0.66, -0.35, "+··+")]
CORNER_SIZE = 13

# 这一层的复测分带名（存活率按分带分组报）
INK_BINS = ("plate", "corner")


def plate_boxes():
    """铭牌层的落笔包围盒（规范画布像素）→ [(x0, y0, x1, y1), ...]

    只取外框 + 铆钉 + 三角三块；框内的刻字属 `plate` 的另一半（判「不可单常数化」），
    该半区不喂色，故不计入存活率。
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


def corner_origins(cx=CX, cy=CY, R=R_CANON):
    """四条注记的**绘制锚点**（左基线）→ [(x, y, 文案), ...]

    表里给的是「注记块的中心该落在哪」，而 `d.text()` 吃的是左基线锚点 ⇒ 用真字体包围盒
    把中心反解成锚点。字号不随 R 缩放（引擎一直按 13px 画），只平移。
    """
    f = _corner_font()
    out = []
    for uc, vc, s in CORNER:
        b = f.getbbox(s)                        # 相对 (0,0) 按默认锚点绘制时的包围盒
        cx_px = cx + uc * R - (b[0] + b[2]) / 2.0
        cy_px = cy + vc * R - (b[1] + b[3]) / 2.0
        out.append((cx_px, cy_px, s))
    return out


def corner_boxes():
    """四条注记的文字包围盒（规范画布像素）"""
    f = _corner_font()
    out = []
    for cx_px, cy_px, s in corner_origins():
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
