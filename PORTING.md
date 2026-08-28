# 移植计划 · PORTING.md（技术方向规划）

> 目标：将本方舟蚀刻章设计器移植到其他 agent 环境（Codex / Claude Code / 通用 CLI agent）。
> 状态：**技术方向规划，实施时间未定**（文档/许可/双语文案已随仓库发布）。
> 原则：引擎接口模型无关（照片+设计稿JSON→PNG），移植工作集中在"环境引导 + AI设计路径适配 + 字体兜底"三块。

---

## 一、现状盘点

| 组件 | 现状 | 移植性 |
|---|---|---|
| 引擎 badge_engine.py / emblem_render.py | 纯 Python（numpy/Pillow），相对路径，字体目录已含 mac/Linux 回退 | 基本可移植 |
| CLI 接口（照片+JSON→PNG） | 模型无关 | ✅ |
| 离线兜底（line/icon/facet/silhouette） | 零外部依赖 | ✅ 任何环境可跑 |
| SKILL.md | YAML frontmatter 与 Claude/Codex Skills 格式同构 | 可近乎直投 |
| PROMPTS.md / 质检清单 | 纯文本指令 | ✅ |
| AI 纹章主路径（设计+质检） | 依赖 agent 环境特有视觉机制 | ⚠️ 需适配 |
| 命令示例 | PowerShell 语法（$env:PYTHONIOENCODING） | ⚠️ 需补 bash 版 |
| 字体 | 主用 Windows 字体（msyh/幼圆/Bahnschrift） | ⚠️ mac/Linux 需补候选 |

## 二、待产出的移植物料（4 项）

1. **Skill 格式适配**
   - 投放位置：Codex → `~/.codex/skills/arknights-medal-designer/`（或项目 `.codex/skills/`）；
     Claude → `~/.claude/skills/`；通用 → 项目根 `AGENTS.md` 引用本目录
   - SKILL.md 去除环境专属措辞（如指向特定工作目录的表述）

2. **运行时引导**
   - `requirements.txt`（numpy、pillow）✅ 已落地（2026-08-27）
   - 命令示例改 shell 无关：`PYTHONIOENCODING=utf-8 python3 engine/badge_engine.py ...`（PowerShell/bash 双栏）⏳ 待补

3. **AI 设计路径 API 适配器（关键项）**
   - 做法 A（零新依赖）：目标 agent 自带视觉 → 按 PROMPTS.md 模板自行读图出设计稿 ✅ 可用
   - 做法 B：`design_emblem.py` ✅ 已落地（2026-08-27）——调用任意 OpenAI 兼容视觉 API
     （base_url/model/key 走环境变量）读图产出设计稿 JSON，可 `--render` 直接出图
   - 推荐 A+B 并存

4. **字体跨平台兜底**
   - ✅ 已落地（2026-08-27）：候选已补入引擎（mac `PingFang`/`Hiragino Sans GB`/`Hiragino Maru Gothic`；Linux `NotoSansCJK`/`WenQuanYi`/`DejaVu`），待 mac/Linux 实机验证
   - 遗留：英文圆体在 Linux 的等价物仍可补充

## 三、目标环境前置条件（写入 PORTING 检查清单）

1. Python 3.10+；`pip install -r requirements.txt`（numpy、pillow，requirements.txt 已随仓库提供）
2. 文件读写 + shell 执行权限（Codex/Claude 默认具备）
3. 网络：离线兜底不需要；做法 B 需可达的视觉 API（或 agent 自带视觉）
4. 冒烟测试：`python engine/badge_engine.py samples/sword_icon.png -o output/smoke.png --style arknights`，
   按 `PROMPTS.md` §三 质检清单人工核对；`output/` 为运行时生成目录，参考图不入库

## 四、执行顺序

1. 双 shell 命令示例 + SKILL.md 措辞清理
2. 字体跨平台兜底 ✅ 已落地（2026-08-27，待 mac/Linux 实机验证）
3. design_emblem.py ✅ 已落地（2026-08-27）
4. PORTING 检查清单定稿 + 冒烟测试
5. git 提交

## 五、结论备忘

- 离线兜底路径：今天即可直投（仅需 numpy/Pillow）
- 主路径：目标 agent 有视觉 → 零改动；无视觉 → 补 API 适配脚本
- 其余为文档/字体/命令示例层面小修，预计 4~5 个文件新增与改动
