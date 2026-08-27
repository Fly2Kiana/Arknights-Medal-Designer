# -*- coding: utf-8 -*-
"""Generate three heraldic sword-emblem designs + render QC previews."""
import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emblem_render import render_emblem

CX = 500.0  # canvas center x
CYTOP = 500.0

def rot(pts, cx, cy, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    out = []
    for (x, y) in pts:
        dx, dy = x - cx, y - cy
        out.append([cx + dx * c - dy * s, cy + dx * s + dy * c])
    return out

def mirror(pts):
    return [[1000.0 - x, y] for (x, y) in pts]

def poly(pts, fill, stroke=None, w=16):
    d = {"t": "poly", "pts": [[round(x, 1), round(y, 1)] for (x, y) in pts],
         "fill": fill}
    if stroke is not None:
        d["stroke"] = stroke
        d["w"] = w
    return d

def circle(cx, cy, r, fill, stroke=None, w=14):
    d = {"t": "circle", "cx": round(cx, 1), "cy": round(cy, 1), "r": round(r, 1),
         "fill": fill}
    if stroke is not None:
        d["stroke"] = stroke
        d["w"] = w
    return d

def rect(x0, y0, x1, y1, fill, stroke=None, w=14):
    d = {"t": "rect", "x0": round(x0, 1), "y0": round(y0, 1),
         "x1": round(x1, 1), "y1": round(y1, 1), "fill": fill}
    if stroke is not None:
        d["stroke"] = stroke
        d["w"] = w
    return d

def line(x1, y1, x2, y2, lum, w=7):
    return {"t": "line", "x1": round(x1, 1), "y1": round(y1, 1),
            "x2": round(x2, 1), "y2": round(y2, 1), "lum": lum, "w": w}

def arc(cx, cy, r, a0, a1, lum, w=7):
    return {"t": "arc", "cx": round(cx, 1), "cy": round(cy, 1), "r": round(r, 1),
            "a0": a0, "a1": a1, "lum": lum, "w": w}


def sword_vertical():
    """Central vertical sword (tip up) as list of shapes."""
    S = []
    # blade (tapered, symmetric about x=500)
    S.append(poly([[500, 130], [536, 265], [548, 612], [452, 612], [464, 265]],
                  fill=0.88, stroke=0.22, w=18))
    # central ridge line
    S.append(line(500, 190, 500, 600, 0.55, 7))
    # diamond inlay (dark accent)
    S.append(poly([[500, 320], [546, 396], [500, 472], [454, 396]], fill=0.22, stroke=0.55, w=8))
    # crossguard (horizontal bar)
    S.append(poly([[352, 622], [648, 622], [648, 676], [352, 676]],
                  fill=0.55, stroke=0.22, w=18))
    S.append(line(352, 649, 648, 649, 0.22, 7))
    # handle
    S.append(poly([[470, 676], [530, 676], [530, 846], [470, 846]],
                  fill=0.55, stroke=0.22, w=14))
    # round pommel
    S.append(circle(500, 898, 52, fill=0.88, stroke=0.22, w=16))
    S.append(circle(500, 898, 30, fill=0.22))
    return S


# ---------------------------------------------------------------------------
# CONCEPT A : sword + crossed double wings + starburst
# ---------------------------------------------------------------------------
def wing_left():
    """Left wing made of curved feather bands, sweeps up-left from the guard."""
    W = []
    base = [446, 620]
    # feather quills fanning up-left
    tips = [(150, 240), (215, 165), (300, 130)]
    halves = [46, 42, 38]
    for (tx, ty), h in zip(tips, halves):
        dx, dy = tx - base[0], ty - base[1]
        L = math.hypot(dx, dy)
        ux, uy = dx / L, dy / L
        px, py = -uy, ux
        p = [base,
             [base[0] + px * h, base[1] + py * h],
             [tx, ty],
             [base[0] - px * h, base[1] - py * h]]
        W.append(poly(p, fill=0.55, stroke=0.22, w=14))
        W.append(line(base[0], base[1], tx, ty, 0.22, 6))
    return W


def wings_plus():
    """Left wing + its mirror, as one flat list of shapes."""
    W = wing_left()
    for p in list(W):
        if p["t"] == "poly":
            W.append(poly(mirror(p["pts"]), p["fill"], p.get("stroke"),
                          p.get("w", 14)))
        elif p["t"] == "line":
            m = mirror([(p["x1"], p["y1"]), (p["x2"], p["y2"])])
            W.append(line(m[0][0], m[0][1], m[1][0], m[1][1], p["lum"], p["w"]))
    return W


def concept_a():
    S = []
    # symmetric starburst rays radiating in an outer ring (avoid wing zone)
    for i in range(12):
        a = 360.0 / 12 * i
        x1 = CX + 430 * math.cos(math.radians(a))
        y1 = CYTOP + 430 * math.sin(math.radians(a))
        x2 = CX + 500 * math.cos(math.radians(a))
        y2 = CYTOP + 500 * math.sin(math.radians(a))
        S.append(line(x1, y1, x2, y2, 0.22, 6))
    # crossed double wings
    S += wings_plus()
    # sword on top
    S += sword_vertical()
    return S


# ---------------------------------------------------------------------------
# CONCEPT B : sword standing inside a ring band + wheat ear ornaments
# ---------------------------------------------------------------------------
def wheat(side):  # side=+1 right, -1 left
    """A wheat ear: filled tapered stalk band hugging an arc + overlapping grains."""
    G = []
    root = [500 + side * 268, 812]
    top = [500 + side * 22, 320]
    P = [root,
         [500 + side * 250, 720],
         [500 + side * 205, 610],
         [500 + side * 150, 500],
         [500 + side * 92, 405],
         top]
    # filled tapered stem band (crescent ribbon)
    def offset(p, h):
        i = P.index(p)
        nx = P[i - 1] if i > 0 else p
        fx = P[i + 1] if i < len(P) - 1 else p
        tx, ty = fx[0] - nx[0], fx[1] - nx[1]
        tl = math.hypot(tx, ty) or 1.0
        px, py = -ty / tl, tx / tl
        return [p[0] + px * h, p[1] + py * h]
    left = [offset(p, -walk(p, P)) for p in P]
    right = [offset(p, walk(p, P)) for p in P]
    band = [[round(x, 1), round(y, 1)] for x, y in (left + right[::-1])]
    G.append(try_poly(band, 0.55, 0.22, 9))
    # overlapping grain leaves along the outer half, merging into the head
    for i in range(1, len(P) - 1):
        x, y = P[i]
        o = offset(P[i], walk(P[i], P))
        ox, oy = x + (o[0] - x) * 1.15, y + (o[1] - y) * 1.15
        G.append(try_poly([[x, y + 30], [ox + side * 30, y - 4], [x, y - 34], [ox - side * 30, y - 4]],
                          0.55, 0.22, 9))
    # dominant dark tip grain
    tx, ty = top
    G.append(try_poly([[tx, ty + 38], [tx + side * 24, ty - 6], [tx, ty - 50], [tx - side * 24, ty - 6]],
                      0.22, 0.88, 11))
    G.append(line(tx + side * 6, ty + 18, tx, ty - 30, 0.88, 6))
    return G


def walk(p, P):
    """Half-width of stalk at point p, tapering from root to tip."""
    i = P.index(p)
    frac = i / (len(P) - 1)
    return 34 * (1 - frac) + 12 * frac


def try_poly(pts, fill, stroke=None, w=9):
    try:
        return poly(pts, fill, stroke, w)
    except Exception:
        return {"t": "line", "x1": pts[0][0], "y1": pts[0][1],
                "x2": pts[-1][0], "y2": pts[-1][1], "lum": fill, "w": w}


def concept_b():
    S = []
    # concentric ring bands (annulus) via two filled circles
    S.append(circle(500, 500, 384, fill=0.55, stroke=0.22, w=20))
    S.append(circle(500, 500, 318, fill=0.88, stroke=0.22, w=8))
    # fine engraving ring between
    S.append(circle(500, 500, 351, fill=None, stroke=0.22, w=6))
    # wheat ornaments inside, both sides
    S += wheat(+1)
    S += wheat(-1)
    # sword standing center
    S += sword_vertical()
    return S


# ---------------------------------------------------------------------------
# CONCEPT C : two swords crossed in an X + diamond emblem core
# ---------------------------------------------------------------------------
def sword_rot(deg):
    S = sword_vertical()
    out = []
    for s in S:
        t = s["t"]
        if t == "poly":
            out.append(poly(rot(s["pts"], 500, 520, deg), s["fill"], s["stroke"], s.get("w", 16)))
        elif t == "circle":
            p = rot([[s["cx"], s["cy"]]], 500, 520, deg)[0]
            out.append(circle(p[0], p[1], s["r"], s["fill"], s.get("stroke"), s.get("w", 14)))
        elif t == "line":
            a = rot([(s["x1"], s["y1"]), (s["x2"], s["y2"])], 500, 520, deg)
            out.append(line(a[0][0], a[0][1], a[1][0], a[1][1], s["lum"], s["w"]))
    return out


def concept_c():
    S = []
    # radiating rays behind
    for i in range(12):
        a = 360.0 / 12 * i
        x1 = CX + 300 * math.cos(math.radians(a))
        y1 = CYTOP + 300 * math.sin(math.radians(a))
        x2 = CX + 360 * math.cos(math.radians(a))
        y2 = CYTOP + 360 * math.sin(math.radians(a))
        S.append(line(x1, y1, x2, y2, 0.22, 6))
    # two crossed swords (X)
    S += sword_rot(40)
    S += sword_rot(-40)
    # diamond emblem core at center
    S.append(poly([[500, 150], [720, 520], [500, 890], [280, 520]], fill=0.22, stroke=0.88, w=20))
    S.append(poly([[500, 320], [600, 520], [500, 720], [400, 520]], fill=0.88, stroke=0.22, w=8))
    S.append(circle(500, 520, 90, fill=0.55, stroke=0.22, w=10))
    S.append(poly([[500, 470], [540, 520], [500, 570], [460, 520]], fill=0.22))
    return S


if __name__ == "__main__":
    builds = {"A": concept_a, "B": concept_b, "C": concept_c}
    for name, fn in builds.items():
        shapes = fn()
        design = {"shapes": shapes}
        j = json.dumps(design, ensure_ascii=False, separators=(",", ":"))
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               f"design_{name}.json"), "w", encoding="utf-8") as f:
            f.write(j)
        print(name, "shapes:", len(shapes))
        face = render_emblem(j, tone="silver", style="lineart",
                             polarity="dark-on-light", carve="machine")
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "output", f"design_{name}.png")
        face.save(out)
        print("   ->", out)
