# Changelog

This file records user-visible changes to Arknights Medal Designer (方舟蚀刻章设计器). The project is distributed as source code; there is no npm publication.

## Unreleased (dev/zcode-dev-20260912 · 完整开发轮)

- **Fully-local pipeline verified end-to-end**: local Ollama (portable, `OLLAMA_MODELS`-driven) + `qwen2.5vl:7b` produces valid emblem-design JSON through the OpenAI-compatible loopback endpoint; `engine/badge_engine.py` renders it into a medal — zero cloud round-trip.
- **CLI optional AI matting** (`MEDAL_AI_MATTING=1`, model via `MEDAL_MATTING_MODEL`): onnxruntime + U²-Net-family model; falls back silently to classic matting. Rescues photos where classic matting fragments (verified on a cluttered-background photo). No hardcoded paths anywhere.
- **Web tool matting model fully vendored** (`web/vendor/`, ~193MB, every chunk SHA-256-verified against the upstream manifest): local copy first, pinned CDNs only as fallback — the CDN trust surface from the 2026-09-02 audit is eliminated.
- **SKILL v2**: SKILL.md becomes a mode router (Generate / Prompt-only / Reference Analysis / Photo Input with high-medium-low preservation levels); new `references/` set (style-system, prompt-compiler, quality-gate G1–G14, variation-engine) shared by any agent.
- **`--list-types`** medal-type catalogue (`engine/medal_types.py`) — the style × tone × mode registry used by docs and skills.
- **`--project` session directories**: `output/projects/<name>/roundNN…` auto-numbered rounds with per-round params/warnings/design-JSON snapshots for iterate-on-the-last-round workflows.
- `NANO_PROMPTS.md` gained a section on feeding prompts both ways between the no-engine path and the engine path.

## Unreleased (dev/zcode-handover-20260912)

- Security & robustness fixes from the 2026-09-02 audit (see `docs/AUDIT-FINDINGS.md`):
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
