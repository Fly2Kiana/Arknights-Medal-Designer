# 移植到其他环境 · Porting

方舟蚀刻章设计器从设计上就能在原环境之外运行。引擎接口与模型无关——一张照片 + 可选的设计稿 JSON → 一枚蚀刻章 PNG——所以移植工作主要集中在环境引导、AI 设计路径与字体三块。

## 容易移植的部分

- **引擎与命令行**：纯 Python（numpy + Pillow），相对路径，无需 GPU。离线兜底（`line` / `silhouette` / `facet` / `icon`）在任何环境都能跑，无需网络或模型。
- **Skill 格式**：`SKILL.md` 采用与常见 agent skill 格式同构的 YAML frontmatter，可近乎直投到其他 agent 环境。
- **设计适配器**：`engine/design_emblem.py` 调用任意 OpenAI 兼容视觉 API（端点、模型、密钥走环境变量），让无内置视觉的环境也能走 AI 纹章设计主路径。

## 需要留意的部分

- **命令示例**：README 用 PowerShell；bash 等价写法很直接（`PYTHONIOENCODING=utf-8 python3 engine/badge_engine.py ...`）。
- **字体**：以 Windows 系统字体为主；macOS 与 Linux 的候选字体已列在引擎中，将在这些平台上实机验证。
- **AI 设计路径**：自带视觉机制的环境可直接设计纹章；其余用上面的适配器。

## 前置条件

1. Python 3.10+，`pip install -r requirements.txt`。
2. 文件读写与 shell 执行权限。
3. 仅在使用远程视觉 API 时需要网络；离线兜底不需要。
4. 冒烟测试：`python engine/badge_engine.py samples/sword_icon.png -o output/smoke.png --style arknights`，再对照 [PROMPTS.md](PROMPTS.md) 核对成品。

这是技术方向，非发布承诺。另见 [docs/ROADMAP.md](docs/ROADMAP.md)。