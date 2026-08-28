# Changelog

This file records user-visible changes to Arknights Medal Designer (方舟蚀刻章设计器). The project is distributed as source code; there is no npm publication.

## v1 — 2026-08-27

- Established the public project identity: **Arknights Medal Designer** (`arknights-medal-designer`), with a bilingual README pair (English + 简体中文).
- Restructured documentation: CHANGELOG, SECURITY, SUPPORT, CONTRIBUTING, and `requirements.txt` for reproducible installs.
- Expanded the installation guide: environment checks, an AI-agent install prompt, numbered manual steps with a smoke test, per-entrypoint usage, and update/uninstall commands.
- Hardened the research fetch scripts: relative paths instead of machine-specific absolute paths; expanded `.gitignore` for credentials/system files; added the MIT `LICENSE`.
- Recorded the earlier development history: dual-style medal engine (Arknights + Endfield), AI emblem-design pipeline with visual QC, real-photo batch test rig, and the self-contained `PROMPTS.md` operator manual.
- By design, local test outputs, downloaded study assets, and debug crops stay out of the repository; `output/` and the `reference/` download corpus regenerate locally.
- Added GitHub issue/PR templates, a Python CI workflow (Ubuntu/Windows × Python 3.10/3.12 smoke tests), and NOTICE (research-source attribution).
- Added `engine/design_emblem.py` — an OpenAI-compatible vision API adapter (env-configured) that produces design JSON for agent environments without built-in vision, with optional `--render` output.
