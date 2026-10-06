# -*- coding: utf-8 -*-
"""
实战压测工装 · Real Photo Batch Tester
对目录内每张真实照片执行风格×色调×模式矩阵，产出：
  output/real/<名字>_<style>_<tone>[_<mode>].png
  output/real/_manifest.json   （每张图的输入分析 + 生成参数 + 耗时）
用法:
  python batch_test.py <照片目录或单张路径>… [--out 目录] [--quick]
  可给多个目录/多张路径（夜跑 S2 起，护栏输入面 = `samples real_photos` = 16 张 = 335 格）；
  **行组合 `plan_matrix` 一个字没改**，只动输入面 ⇒ 原 83 张必须逐字节不变（判据 N-5）。
"""
import argparse
import json
import os
import sys
import time

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import badge_engine as be

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# 终末地支：6 品阶 × 3 家族 = 18 条（护栏定义变更，计划 §4.2）
EF_TONES = ["ef_silver", "ef_gold", "ef_gold_pure", "ef_dark", "ef_bronze", "ef_pearl"]
EF_FAMS = ["story", "combat", "industry"]


def plan_matrix(kind: str, has_alpha: bool):
    """按输入类型规划生成矩阵：(style, tone, mode, endfield_family) 列表

    终末地支上一版只有 `ef_silver`/`ef_gold` 两条 ⇒ 唯一动过像素的 `dark` 网格结构上
    抓不到（勘误轮登记的覆盖面洞）。现在 6 品阶 × 3 家族全跑，`mode` 一律钉在 `line`：
    `silhouette`/`facet` 会把照片内容画进章面，量测 bin 会被 subject 污染。
    方舟/糖果支一行不改（本轮不该动它们的像素）。
    """
    m = [("arknights", "silver", "line", None)]
    if kind == "photo":
        m += [("arknights", "gold", "facet", None)]
        if not has_alpha:
            m += [("endfield", "ef_gold", "silhouette", None)]
    elif kind == "graphic" and has_alpha:
        m += [("arknights", "plated", "line", None)]
    if kind in ("photo", "graphic"):
        m += [("endfield", t, "line", f) for f in EF_FAMS for t in EF_TONES]
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="+",
                    help="一个或多个照片目录/单张路径（夜跑 S2：输入面从 1 个目录扩到 2 个）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--quick", action="store_true", help="每张只跑第一个组合")
    ap.add_argument("--tol-sweep", action="store_true",
                    help="额外跑容差扫描(18/26/34)用于抠图对比")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.out or os.path.join(root, "output", "real")
    os.makedirs(out_dir, exist_ok=True)

    files = []
    for target in args.input:
        if os.path.isdir(target):
            files += [os.path.join(target, f) for f in sorted(os.listdir(target))
                      if os.path.splitext(f)[1].lower() in IMG_EXT]
        else:
            files.append(target)
    # 成品名只取输入的文件名主干 ⇒ 跨目录同名会互相覆盖（静默丢格）。
    # 输入面扩到两个目录后这是真风险，先撞名先停，不猜谁该赢。
    seen, dup = {}, []
    for fp in files:
        stem = os.path.splitext(os.path.basename(fp))[0]
        if stem in seen:
            dup.append("%s（%s 与 %s）" % (stem, seen[stem], fp))
        else:
            seen[stem] = fp
    if dup:
        print("[abort] 输入文件名跨目录撞名 ⇒ 成品会互相覆盖：" + "、".join(dup))
        return 2

    manifest = []
    for fp in files:
        name = os.path.splitext(os.path.basename(fp))[0]
        try:
            src = Image.open(fp)
            src.load()
        except Exception as e:
            print(f"[skip] {name}: {e}")
            continue
        has_alpha, kind = be.analyze_input(src)
        print(f"\n===== {name} | kind={kind} alpha={has_alpha} =====")
        entry = {"file": os.path.basename(fp), "kind": kind,
                 "has_alpha": has_alpha, "outputs": [], "warns": []}

        combos = plan_matrix(kind, has_alpha)
        if args.quick:
            combos = combos[:1]

        for style, tone, mode, fam in combos:
            t0 = time.time()
            outp = os.path.join(out_dir, f"{name}_{style}_{tone}"
                                + (f"_{mode}" if mode != "line" else "")
                                + (f"_{fam}" if fam else "") + ".png")
            try:
                kw = {} if fam is None else {"endfield_family": fam}
                path, warn = be.generate(fp, outp, style=style, tone=tone,
                                         text="蚀刻勋章", mode=mode, **kw)
                dt = time.time() - t0
                rel = os.path.relpath(path, root)
                entry["outputs"].append({"path": rel, "style": style, "tone": tone,
                                         "mode": mode, "family": fam, "sec": round(dt, 2)})
                print(f"  [{style}/{tone}/{mode}"
                      + (f"/{fam}" if fam else "") + f"] {dt:.1f}s -> {rel}")
                if warn:
                    entry["warns"].append(warn)
                    print(f"    {warn}")
            except Exception as e:
                print(f"  [{style}/{tone}/{mode}"
                      + (f"/{fam}" if fam else "") + f"] ERROR: {e}")
                entry["outputs"].append({"style": style, "tone": tone, "mode": mode,
                                         "family": fam, "error": str(e)})

        # 容差扫描（仅照片、非 alpha）
        if args.tol_sweep and kind == "photo" and not has_alpha:
            for tol in (18, 34):
                outp = os.path.join(out_dir, f"{name}_mattol{tol}.png")
                try:
                    be.generate(fp, outp, style="arknights", tone="silver",
                                matting_tol=float(tol), mode="line")
                    entry["outputs"].append({"path": os.path.relpath(outp, root),
                                             "matting_tol": tol})
                    print(f"  [tol={tol}] saved")
                except Exception as e:
                    print(f"  [tol={tol}] ERROR: {e}")

        manifest.append(entry)

    mf = os.path.join(out_dir, "_manifest.json")
    with open(mf, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\nmanifest -> {mf}")
    print(f"total images: {len(manifest)}")


if __name__ == "__main__":
    sys.exit(main() or 0)
