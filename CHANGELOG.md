# Changelog

This file records user-visible changes to Arknights Medal Designer (方舟蚀刻章设计器). The project is distributed as source code; there is no npm publication.

## Unreleased (dev/zcode-handover-20261024 · 终末地全档重做轮 R-8~R-25)

- **五档色场全部换血为官方章原色直采**：pure/gold_plated 走 hp 原色直采路径（跳过恒定色相投影，保留官方 hue 52°→28° 随亮度漂移与 val 233→71 大跨度）；silver/dark/pearl 网格重采并逐档定标（银 209、深灰场 RGB 79,79,81、珠光 sat 口径对齐）。
- **dark 档重构**：删除合成厚斜边亮环（"rim 140"系章顶金属搭扣混入 d 分箱的测量伪影）；场区去绿偏定标（中性蓝黑 79,79,81）；内场亮向按三枚官方章分象限实测翻转（亮向右下）；1px 细密拉丝 420 条。
- **gold_pure 过渡**：扫光按用户红线像素级定标（亮向 (0.52,-0.85) offset 0.417，线过章体相对 (0.501,0.394)），场层羽化 blur 32，暗格自适应偏置（B 通道对齐官方 0.44）。
- **镀彩金**：B 通道穿零修复（逐像素 boost 上限 cap，引擎+web 镜像）+ HSV 空间色相保持型强饱和 1.30（绿区 hue 85 不再塌到 65）+ 绿区保持统计（密度门槛 30% 防三角倒置）+ 绿子集取更绿半部。
- **珠光**：HSV 空间强饱和 1.45（色相保持的"猛"）+ 近灰像元掩码（白基底防花）。
- **合成亮环层删除**：dark 档"厚斜边亮环"系测量伪影（章顶搭扣混入），rim 幅度降至 0.15。
- **新尺子** `engine/measure_lighting.py`：章体自动检测→六边形交集→重模糊双尾修剪→2D 梯度拟合，可直接测渲染件；`MEDAL_STAGE_DUMP` 分级转储逐级审计管线。
- **新采样器**：`resample_pearl/plated/dark/goldpure.py` 四件套（各档独立定标链）。
- **稳定性**：分级转储钩子缩进 bug 修复（else 被绑走致五档走 ramp 兜底）；_hsv_sat_boost 尺度混用修复（近灰 0-255/增强 0-1 混尺致珠光黑块）；嵌入块双次补同步。
- **验证**：7 真实照片×5 档压力测试全通过；5 档×3 形制矩阵复核；护栏全绿；web 全镜像。

## Unreleased (dev/zcode-style-v2-20260912 · 风格 v2 轮)

- **Pure-gold tier** (`--tone gold_pure`/`pure`): matte amber field with authentic top-right → bottom-left directional lighting, cream engraving, diagonal pin rods and dot-grid decorations (sampled from the 15-medal collection sheet). Default `--tone gold` now maps to pure gold; the rich multicolor display look stays as `gold_plated`.
- **Silver tier corrected by sampling**: in-game battle-silver medals are actually cool dark-gray (lum≈80, sat≈13) with light engraving — field grid and etch palette re-sampled accordingly (the old pale satin belonged to the industry family only).
- **Directional lighting replaces the white mirror band** on all Endfield tiers (top-right ×1.22 → bottom-left ×0.84), removing the wash that hurt overall readability.
- Dark-rank field re-sampled with tier-classified filtering (6 medals).
- **Top nameplate rebuilt from zoomed reference measurement** (license-plate style): rounded rect ≈0.20×medal width, thin outline, four small filled corner rivets, hollow triangle pointer at the apex — same plate for story/combat families (the old external strap was a misread); HUD note moved below the plate.
- Field blob patches smooth out "团斑" artifacts (grid-level σ2.2 smoothing + adaptive render blur).
- **Web tool synced to engine v2**: five Endfield tiers + story/combat shape family in the UI; the sampled color-field grids and pearl blobs are embedded from `engine/ef_field_grids.json` via `engine/sync_web_fields.py` (single source of truth); license-plate nameplate, directional lighting, bottom ports, side rails, pins/dot-grid and stripe clusters all ported; Arknights plating recalibrated to the hue-shift model. Verified end-to-end in a real browser (vendored matting model, zero console errors).
- Docs synced: SKILL/PROMPTS/NANO_PROMPTS tier naming (silver/gold_pure/gold_plated/dark/pearl).
- **Tier taxonomy confirmed from the collection panel** (86 = 14 bronze + 33 silver + 39 gold): the silver tier is the LIGHT satin medal — its field grid re-sampled accordingly (synthesized from sampled points #D6D9DC→#9EA4AA, edge #767B80, top-right lift), clearly distinct from the charcoal bronze/rank tier.
- Pure-gold field upgraded to a 14×12 fine grid (15 medals; directional shading baked in, multiply layer softened to ×0.92–1.07) for smoother highlight transitions.
- Pearl (silver-plated) grid rebuilt from the large "生存专家" plated medal plus two more sources — much richer iridescent flow.

- **Endfield template v11 rebuilt from 2026-09 in-game screenshots**: four clearly distinct tiers — silver (satin), gold (gold→warm-green gradient field with cream engraving, warm-orange edge glow), dark rank medal (charcoal + white engraving + `#N` rank mark), pearl plating (white pearlescent + subtle rainbow shift + dark engraving, replacing the old full-spectrum holographic look).
- **Shape families**: `--endfield-family story|combat` — story display medal (top nameplate, corner engineering annotations, bottom connector ports, halftone fade) vs combat counter medal (top strap outside the hexagon + "N TIMES" engraved counter).
- **Arknights plating recalibrated from paired samples**: plating is now a whole-medal hue shift (+150°, adjustable) with brightness lift and a light pearl film — same skeleton, shifted palette (matches the paired normal/plated corpus), replacing the old full-spectrum overlay.
- New `--tone dark|pearl` for Endfield; `--list-types` registry updated; full iteration QC log in `docs/zcode/style-v2-qc-log.md`.
- **Pearl field upgraded to an 86×74 ultra-fine sampled grid** (medal re-localized, black collage emblem/edges/accents excluded, per-cell median + neighborhood fill + grid-level σ2.2 smoothing): banding eliminated, premium multi-color patchwork with smooth transitions (field blur reduced to 16px to keep the patch character).
- **Data-driven asymmetric color fields**: per-tier 8×9 color grids sampled from in-game screenshots (emblem/accent pixels excluded, median per cell) are rendered via bicubic interpolation with edge-hold — multi-directional gradients, transitions, saturation and richness now come straight from the reference material instead of hand-tuned stops. Per-tier saturation strategy (vivid metal edges vs soft pearl flow).
- **Color/pattern 1:1 replication pass**: field palettes replaced with values sampled programmatically from in-game screenshots (gold #DCD38E→#98B020 with #DC6107 orange sides; charcoal #525457/#2B2E2C; pearl #BBC2B1/#CDC2BC; silver #D0D3D6/#767B80), plus side-rail ornaments (screws/glyph columns/dot grids), red accent line, diagonal stripe clusters, and flat cream silhouette emblems at 65% face share (Endfield defaults to `silhouette` etching).

## Unreleased (dev/zcode-dev-20260912 · 完整开发轮)

- **Fully-local pipeline verified end-to-end**: local Ollama (portable, `OLLAMA_MODELS`-driven) + `qwen2.5vl:7b` produces valid emblem-design JSON through the OpenAI-compatible loopback endpoint; `engine/badge_engine.py` renders it into a medal — zero cloud round-trip.
- **CLI optional AI matting** (`MEDAL_AI_MATTING=1`, model via `MEDAL_MATTING_MODEL`): onnxruntime + U²-Net-family model; falls back silently to classic matting. Rescues photos where classic matting fragments (verified on a cluttered-background photo). No hardcoded paths anywhere.
- **Web tool matting model fully vendored** (`web/vendor/`, ~193MB, every chunk SHA-256-verified against the upstream manifest): local copy first, pinned CDNs only as fallback — the CDN trust surface from the 2026-09-02 audit is eliminated.
- **SKILL v2**: SKILL.md becomes a mode router (Generate / Prompt-only / Reference Analysis / Photo Input with high-medium-low preservation levels); new `references/` set (style-system, prompt-compiler, quality-gate G1–G14, variation-engine) shared by any agent.
- **`--list-types`** medal-type catalogue (`engine/medal_types.py`) — the style × tone × mode registry used by docs and skills.
- **`--project` session directories**: `output/projects/<name>/roundNN…` auto-numbered rounds with per-round params/warnings/design-JSON snapshots for iterate-on-the-last-round workflows.
- `NANO_PROMPTS.md` gained a section on feeding prompts both ways between the no-engine path and the engine path.

## Unreleased (dev/zcode-handover-20260912)

- Security & robustness fixes from the 2026-09-02 audit (see `docs/zcode/2026-09-02-audit-findings.md`):
  - `design_emblem.py`: reject plaintext `http://` endpoints except loopback (API key/photo travel in the clear); defensive parsing of provider responses; 80 MP input guard.
  - `emblem_render.py`: design-JSON validation (top-level type, `shapes` list, non-object entries); per-shape error isolation with stderr warnings; zero-branch laurel / zero-point star / missing banner & bezier fields no longer crash.
  - `badge_engine.py`: explicit 80 MP decompression-bomb guard; `--mode emblem` without a design file now explains the fallback on stderr; candy style no longer runs the emblem/etch pipeline twice (same output, ~2× faster for that path); medal face fields drawn row-wise instead of per-pixel.
  - Web tool: status messages no longer use `innerHTML`; input canvases downscale to 4096 px max; object URLs are revoked after use.
  - CI: actions pinned by commit SHA (checkout v4.2.2, setup-python v5.6.0).
- Docs: privacy statements (README ×2, SECURITY, SKILL) now name the two network-touching exceptions (web-tool CDN fetches; `design_emblem.py` photo upload) instead of an absolute "nothing is uploaded" claim.

## v1 — 2026-08-27

- Established the public project identity: **Arknights Medal Designer** (`arknights-medal-designer`), with a bilingual README pair (English + 简体中文).
- Restructured documentation: CHANGELOG, SECURITY, SUPPORT, CONTRIBUTING, and `requirements.txt` for reproducible installs.
- Expanded the installation guide: environment checks, an AI-agent install prompt, numbered manual steps with a smoke test, per-entrypoint usage, and update/uninstall commands.
- Hardened the research fetch scripts: relative paths instead of machine-specific absolute paths; expanded `.gitignore` for credentials/system files; added the MIT `LICENSE`.
- Recorded the earlier development history: dual-style medal engine (Arknights + Endfield), AI emblem-design pipeline with visual QC, real-photo batch test rig, and the self-contained `PROMPTS.md` operator manual.
- By design, local test outputs, downloaded study assets, and debug crops stay out of the repository; `output/` and the `reference/` download corpus regenerate locally.
- Added GitHub issue/PR templates, a Python CI workflow (Ubuntu/Windows × Python 3.10/3.12 smoke tests), and NOTICE (research-source attribution).
- Added `engine/design_emblem.py` — an OpenAI-compatible vision API adapter (env-configured) that produces design JSON for agent environments without built-in vision, with optional `--render` output.
- design_emblem.py fixes from live provider testing: pre-flight ASCII validation for `OPENAI_API_KEY`, and a configurable `--max-tokens` (default 1024, GLM-4V-Flash-compatible; raise it for providers with larger limits).
- design_emblem.py field notes from live testing (Zhipu GLM-4V-Flash / GLM-4V-Plus): free/low-cost tiers output few shapes and tend to copy the few-shot example — use them for connectivity self-checks; pick instruction-following-strong vision models (Qwen2.5-VL-72B / GPT-4o / Gemini Pro) for production designs.
