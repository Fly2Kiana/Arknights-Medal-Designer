# Contributing

Thanks for helping improve Arknights Medal Designer. This is a player-made tool for *Arknights* / *Arknights: Endfield* style medals; contributions must keep it a local, non-commercial, clearly-unaffiliated tool.

## Development setup

- Python 3.10+
- `pip install -r requirements.txt`

## Testing

```powershell
python engine/batch_test.py samples --quick
```

Visual QC follows the checklist in `PROMPTS.md` §三 (candy ≥ 0.85 / metal ≥ 0.85 / game-association ≥ 0.7).

## Conventions

- Keep public-facing docs bilingual: update [README.md](README.md) (English) and [README.zh-CN.md](README.zh-CN.md) (简体中文) together.
- Commit messages follow the repository style: `类型：中文摘要` (e.g. `修复：…`, `文档：…`, `功能：…`).
- Never commit: personal photos, downloaded reference material, credentials, or machine-specific paths. Regenerate the study corpus with the scripts under `reference/`.
- Player-made guardrails: do not add features that reproduce official assets verbatim, upload user photos, or imply official endorsement.
