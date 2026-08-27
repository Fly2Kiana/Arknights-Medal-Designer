# -*- coding: utf-8 -*-
"""
实战压测工装 · Real Photo Batch Tester
对目录内每张真实照片执行风格×色调×模式矩阵，产出：
  output/real/<名字>_<style>_<tone>[_<mode>].png
  output/real/_manifest.json   （每张图的输入分析 + 生成参数 + 耗时）
用法:
  python batch_test.py <照片目录或单张路径> [--out 目录] [--quick]
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


def plan_matrix(kind: str, has_alpha: bool):
    """按输入类型规划生成矩阵：(style, tone, mode) 列表"""
    m = [("arknights", "silver", "line")]
    if kind == "photo":
        m += [("endfield", "ef_silver", "line"),
              ("arknights", "gold", "facet")]
        if not has_alpha:
            m += [("endfield", "ef_gold", "silhouette")]
    elif kind == "graphic":
        m += [("endfield", "ef_gold", "line")]
        if has_alpha:
            m.append(("arknights", "plated", "line"))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=None)
    ap.add_argument("--quick", action="store_true", help="每张只跑第一个组合")
    ap.add_argument("--tol-sweep", action="store_true",
                    help="额外跑容差扫描(18/26/34)用于抠图对比")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.out or os.path.join(root, "output", "real")
    os.makedirs(out_dir, exist_ok=True)

    target = args.input
    if os.path.isdir(target):
        files = [os.path.join(target, f) for f in sorted(os.listdir(target))
                 if os.path.splitext(f)[1].lower() in IMG_EXT]
    else:
        files = [target]

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

        for style, tone, mode in combos:
            t0 = time.time()
            outp = os.path.join(out_dir, f"{name}_{style}_{tone}"
                                + (f"_{mode}" if mode != "line" else "") + ".png")
            try:
                path, warn = be.generate(fp, outp, style=style, tone=tone,
                                         text="蚀刻勋章", mode=mode)
                dt = time.time() - t0
                rel = os.path.relpath(path, root)
                entry["outputs"].append({"path": rel, "style": style,
                                         "tone": tone, "mode": mode, "sec": round(dt, 2)})
                print(f"  [{style}/{tone}/{mode}] {dt:.1f}s -> {rel}")
                if warn:
                    entry["warns"].append(warn)
                    print(f"    {warn}")
            except Exception as e:
                print(f"  [{style}/{tone}/{mode}] ERROR: {e}")
                entry["outputs"].append({"style": style, "tone": tone,
                                         "mode": mode, "error": str(e)})

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
    main()
