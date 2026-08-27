# Arknights Medal Designer · 方舟蚀刻章设计器

[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/) [![CI](https://github.com/Fly2Kiana/Arknights-Medal-Designer/actions/workflows/ci.yml/badge.svg)](https://github.com/Fly2Kiana/Arknights-Medal-Designer/actions/workflows/ci.yml) [![Player-made](https://img.shields.io/badge/Player--made-only-orange?style=flat-square)](#project-boundary)

**English** | [简体中文](README.zh-CN.md)

Turn any photo into a stylized *Arknights* / *Arknights: Endfield* medal (蚀刻章) PNG. Two game styles, multi-tier finishes, an AI emblem-design pipeline as the main path, and a classic offline fallback. All processing stays on your machine.

> Player-made notice: Arknights and Arknights: Endfield are trademarks of Hypergryph (鹰角网络). This is an independent player-made tool, not affiliated with or endorsed by Hypergryph. Generated images are stylistic re-creations for personal entertainment only and must not be used commercially.

## Project boundary

- Not an official asset exporter: the engine reimagines your input as a stylized medal; it does not reproduce official art verbatim.
- Fully local: photos are processed on your machine. The web tool loads an in-browser AI matting model (`@imgly/background-removal`) and falls back to the built-in algorithm; nothing is uploaded.
- Player-made only: outputs are derivative stylistic works. Do not use them commercially or to claim official association.

## Project components

| Path | Role |
|---|---|
| `SKILL.md` | Agent skill definition (chat-in, medal-out workflow) |
| `engine/badge_engine.py` | Core engine: subject extraction → XDoG etching → medal composition (numpy + Pillow) |
| `engine/emblem_render.py` | Renders the AI-designed geometric emblem JSON onto the medal face |
| `engine/batch_test.py` / `engine/gen_designs.py` | Real-photo stress-test rig / procedural emblem-design generator |
| `web/index.html` | Single-file web tool (drag, tune, download) — an early template build; the newer templates (Endfield rework + candy) are being ported |
| `PROMPTS.md` | Self-contained operator manual: design prompt template, QC checklist, parameter reference |
| `PORTING.md` | Porting plan to other agent environments (technical direction plan; schedule not yet set) |
| `reference/` | Research fetch scripts (regenerate the downloaded study material) and `DESIGN_SPEC.md` (design research notes) |
| `samples/` | Test inputs |
| `output/` | Runtime output directory (gitignored; generated locally) |

## Styles and tiers

| Style | Tiers | Main pipeline | Status |
|---|---|---|---|
| Arknights (matte metal) | `silver` / `plated` / `gold` (+ `stamp`) | AI emblem design → render; offline fallback `line`/`silhouette`/`facet`/`icon` | ✅ Implemented |
| Endfield (anodized metal) | `silver` / `gold` / `iridescent` | same as the Arknights row | ✅ Implemented |
| Candy sticker | — | same as the Arknights row | ✅ Implemented |
| Web tool newer-template port (Endfield rework + candy) | — | — | ⏳ Planned |

Only rows marked **Implemented** ship in the current tree. Planned entries are directions, not release commitments.

## Installation

Prepare the environment first: you need **Python 3.10+** with `pip`, and a supported consumer — a DSH agent session (for the skill), any browser (for the web tool), or a terminal (for the CLI). numpy and Pillow are the only runtime dependencies; no GPU is required.

### Install with your AI agent

Send the following repository URL and prompt to your coding agent:

```text
Install Arknights Medal Designer from https://github.com/Fly2Kiana/Arknights-Medal-Designer.
Check Python 3.10+ and pip first. Clone it into a location I approve, run
pip install -r requirements.txt, then run the smoke test:
python engine/badge_engine.py samples/sword_icon.png -o output/smoke.png --style arknights
and confirm the pointy-top hexagon, the concentric rings, and the text band look right per the
PROMPTS.md §三 checklist. Do not run the fetch scripts under reference/ (research-only, they
download third-party material). Do not start the web server for me. Tell me when it is
installed and tested.
```

### Manual installation

1. Check the environment.

   ```powershell
   python --version
   pip --version
   ```

   Python 3.10+ is required. Windows needs no extra font setup (the engine uses the Windows system fonts); mac/Linux fallback candidates are already listed in the engine and will be extended along the roadmap.

2. Get the code and install the only two dependencies (numpy, Pillow; about 50 MB, no GPU).

   ```powershell
   git clone https://github.com/Fly2Kiana/Arknights-Medal-Designer.git
   cd Arknights-Medal-Designer
   pip install -r requirements.txt
   ```

3. Run the smoke test and check the output yourself.

   ```powershell
   $env:PYTHONIOENCODING='utf-8'
   python engine/badge_engine.py samples/sword_icon.png -o output/smoke.png --style arknights
   ```

   The generated `output/smoke.png` should show a pointy-top hexagon with multi-layer concentric rings, a halftone matte field, an etched sword emblem, and a centered text band. Compare against the checklist in `PROMPTS.md` §三 (candy ≥ 0.85 / metal ≥ 0.85 / game-association ≥ 0.7). `output/` is a local runtime directory; the repository does not ship generated images.

4. Use it through one of the three entry points.

   **As a DSH agent skill** (chat-in, medal-out):

   ```powershell
   Copy-Item -Recurse this-folder "$env:USERPROFILE\.agents\skills\arknights-medal-designer"
   ```

   Start a new agent session afterwards, say「帮我做一张蚀刻章」("make me an etching medal") and upload a photo. The skill drives the AI emblem-design main path (visual model designs the emblem JSON → local render) with the classic offline fallback, and self-checks the result before delivering.

   **Web tool** (visual tuning):

   ```powershell
   python -m http.server 43985 --bind 127.0.0.1 --directory web
   # open http://127.0.0.1:43985/
   ```

   Drag in a photo → pick template/tone/inscription → tune line strength and detail → generate → download PNG. On first use the page loads an in-browser AI matting model (`@imgly/background-removal`, tens of MB, needs network once); if it fails, the built-in classic algorithm takes over automatically. Photos never leave the browser.

   **CLI** (scriptable batches):

   ```powershell
   $env:PYTHONIOENCODING='utf-8'
   python engine/badge_engine.py photo.jpg -o out/my_badge.png --style arknights `
       --text "阿米娅" --subtitle "ROSMONTIS" --serial "NO.001"
   python engine/badge_engine.py photo.jpg --style endfield --text "终末地" --line-strength 1.2
   # AI emblem main path:
   python engine/badge_engine.py photo.jpg --mode emblem --emblem-design design.json --style arknights --tone silver
   # Real-photo stress test over a directory:
   python engine/batch_test.py samples --quick
   ```

   `--style` selects the medal template (`arknights` matte metal / `endfield` anodized metal / `candy` sticker), `--tone` the finish tier. `--mode emblem` (with `--emblem-design`) selects the AI design main path; otherwise the engine uses the classic offline pipelines (`line`/`silhouette`/`facet`/`icon`). Output goes to `-o`; without it, to the local `output/` directory. Set `PYTHONIOENCODING` on Windows so Chinese inscriptions render correctly.

5. Update or uninstall.

   ```powershell
   # Update a git clone:
   git pull
   pip install -r requirements.txt     # re-run when requirements change
   # Update an installed skill (re-copy the runtime subset):
   Copy-Item -Recurse -Force `
     <repo>\SKILL.md, <repo>\PROMPTS.md, <repo>\engine, <repo>\web `
     "$env:USERPROFILE\.agents\skills\arknights-medal-designer"
   # Uninstall the skill:
   Remove-Item -Recurse -Force "$env:USERPROFILE\.agents\skills\arknights-medal-designer"
   ```

   The fetch scripts under `reference/` are research-only; they download third-party study material and are not needed to use the tool. Never commit or distribute other people's photos processed with it.

## Parameters

| Parameter | Range | Note |
|---|---|---|
| `--style` | arknights / endfield / candy | medal template |
| `--tone` | Arknights: silver/plated/gold/stamp; Endfield: silver/gold/iridescent | finish tier |
| `--text` | ≤8 chars recommended | main inscription |
| `--subtitle` | optional | top label |
| `--serial` | optional | serial annotation |
| `--number` | optional | tier number (e.g. 100) |
| `--mode` | emblem / line / silhouette / facet / icon | emblem = AI design JSON (main path) |
| `--emblem-design` | design.json path | required with `--mode emblem` |
| `--line-strength` | 0.4–1.8 | etching line strength |
| `--detail` | 0.5–2.0 | hatch/detail density |
| `--matting-tol` | 18–34 | matting tolerance; lower for cluttered backgrounds |

## Quality bar

Visual acceptance (per `PROMPTS.md` §三): candy ≥ 0.85 / metal ≥ 0.85 / game-association ≥ 0.7.

## Known boundaries

- Classic matting works best with a clear subject over a simple background; on low confidence the engine falls back to the full image with a rounded fade-in and warns.
- The web tool is still an early template build; the newer templates (Endfield rework + candy) are not ported yet.
- Fonts: Windows system fonts are primary; mac/Linux fallbacks are planned (see `PORTING.md`).

## Roadmap

Planned directions, not release commitments:

1. Web tool newer-template port (Endfield rework + candy).
2. `design_emblem.py` — OpenAI-compatible vision API adapter for agent environments without built-in vision.
3. Cross-platform font fallbacks (mac/Linux).

## More documentation

- [PROMPTS.md](PROMPTS.md) — operator manual and QC checklist
- [SKILL.md](SKILL.md) — agent skill definition
- [PORTING.md](PORTING.md) — porting plan
- [reference/DESIGN_SPEC.md](reference/DESIGN_SPEC.md) — design research notes
- [CHANGELOG.md](CHANGELOG.md) · [SECURITY.md](SECURITY.md) · [SUPPORT.md](SUPPORT.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [NOTICE](NOTICE)

## License

[MIT](LICENSE). Arknights and related names remain the property of their respective owners; see the player-made notice above.
