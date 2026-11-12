---
name: arknights-medal-designer
description: 将用户上传的照片自动制作成《明日方舟》或《明日方舟：终末地》风格的蚀刻章图片。触发场景：用户提到「蚀刻章」「照片变蚀刻章」「明日方舟蚀刻章生成」「终末地蚀刻章制作」，或上传照片并希望转成游戏风格金属蚀刻章；也适用于用户只要蚀刻章生图提示词（nano banana/Gemini）或要求分析参考图风格。自动完成主体提取、XDoG 蚀刻风格化与章体合成，渲染全程本地处理。
---

# 方舟蚀刻章设计器 · Arknights Medal Designer

把任意图片（人像、武器/器物图标、风景照、几何徽标……）变成《明日方舟》哑光金属风或《终末地》阳极氧化金属风的蚀刻章 PNG。引擎具备输入感知与抽象化能力，不专精某一类题材。设计语言见 `references/style-system.md` 与 `reference/DESIGN_SPEC.md`。

## 模式

| 模式 | 适用 | 产出 |
|---|---|---|
| **Generate**（默认） | 照片/一句话 +「做一张」 | 照片 → 纹章设计 → 渲染 → 自检 → 交付 PNG |
| **Prompt-only** | 只要提示词，或当前环境无法渲染 | 按 `NANO_PROMPTS.md` 产出生图提示词，不出图、不暗示已出图 |
| **Reference Analysis** | 参考图/文件夹 +「分析/提炼风格」 | 风格归纳，不生成图（除非同时要求） |
| **Analyze + Generate** | 「先分析参考再做一张」 | 先归纳风格，再据此生成 |

意图模糊但要求「做一张」时走 Generate。

## 照片输入

为每张照片判定用途：
- **编辑目标**：「把这张照片做成章 / 保留这个人或宠物」→ 主体必须出现在章上。
- **风格参考**：「参考这张图的风格/配色」→ 只取视觉语法，不复刻主体。
- **素材插入**：「把照片里的这个物体放进去」→ 取指定局部。

并记录一个**保留等级**（写进交付说明）：high 保留可辨识特征（脸型发型、毛色分区、武器轮廓、标志配色），只做纹章化转译；medium 保留主体与主要特征，允许裁切/缩放/调色/构图变化；low 仅参考视觉语法，不保留主体身份与原构图。

措辞不明且两种角色都合理时才提问；「做一张」+附照片默认按编辑目标处理。

## 能力与流程

1. **输入感知**：带透明通道的设计资产直接使用并保持锐利；照片走抠图 + 纹理压平。可选本地 AI 抠图（`MEDAL_AI_MATTING=1` + `MEDAL_MATTING_MODEL=<u2net族.onnx>`），失败自动回退经典算法。
2. **主体提取**：边界泛洪 + 背景主色屏障 + 多部件保留 + 孔洞填充；低置信自动整图回退并圆角羽化融入章面（stderr 告警须转告用户）。
3. **蚀刻纹章化**：`line` 线稿（默认）/ `silhouette` 剪影 / `facet` 分面 / `icon` 图标化兜底。
4. **章体合成**：
   - `arknights`：`silver` / `plated`（整面虹彩镀膜）/ `gold`（活动金章）/ `stamp`（朱砂印）
   - `endfield`：`silver` / `gold_pure` / `gold_plated` / `dark` / `bronze` / `pearl`；形制家族 `--endfield-family story|combat|industry`；章面文字极简
   - `candy`：糖果贴纸章（白胶边/三色环/缝线/名字气泡）

## 调用

引擎位于本 skill 目录下 `engine/badge_engine.py`，仅依赖 Python 3.10+ 与 numpy、Pillow（可选 onnxruntime 用于 AI 抠图）。

```powershell
$env:PYTHONIOENCODING='utf-8'
python "<skill目录>/engine/badge_engine.py" "<输入照片>" -o "<输出.png>" --style arknights --text "名字" --subtitle "副标" --serial "编号"
```

参数：
- `--style`：`arknights`（默认）| `endfield` | `candy`
- `--tone`：方舟 `silver|plated|gold|stamp`；终末地 `silver|gold_pure|gold_plated|dark|bronze|pearl`
- `--text` 主铭文（建议 ≤8 字）；`--subtitle` 顶部标签；`--serial` 编号；`--number` 数字层级
- `--line-strength` 0.4~1.8；`--detail` 0.5~2.0；`--matting-tol` 18~34；`--no-matting` 跳过抠图整图入章
- `--mode`：`emblem`（AI 设计稿主路径，需 `--emblem-design`）| `line` | `icon` | `silhouette` | `facet`
- `--emblem-design` 设计稿 JSON；`--emblem-style` `lineart|flat`；`--polarity` `dark-on-light|light-on-dark`；`--carve` `machine|hand`

输出写进 `-o`（不指定则写项目 `output/`）。stdout 打印最终路径，stderr 的告警（低置信回退/碎片化）须主动告知用户。

## AI 纹章设计（主路径）

1. **看输入图并设计纹章**：自带视觉直接读图；否则委派任意可用视觉子模型；无视觉时可用 `engine/design_emblem.py` 走 OpenAI 兼容视觉 API（`OPENAI_API_KEY` 必填，`OPENAI_BASE_URL`/`OPENAI_MODEL` 可选）。**该路径会把照片上传到所配端点，是全程本地的唯一例外**；配本地兼容端点即可全本地，见 README「全本地模式」。设计原则见 `references/prompt-compiler.md` 与 `PROMPTS.md`。
2. 设计稿存为 JSON，调用引擎 `--mode emblem --emblem-design <json路径>`。
3. 出图后按 `references/quality-gate.md` 自检，发现问题回改设计稿或参数重跑，再交付。
4. 多候选/批量任务见 `references/variation-engine.md`。

无视觉且无可用子模型时降级 `--mode icon`（图案感弱于主路径）。

## 迭代修改

- 小改（文字/色调/品阶）：改参数重跑，最快。
- 改构图/母题：改设计稿 JSON 对应图元后重跑（改图元不换骨架），保留等级继续生效。
- 会话产物：设计稿与各轮 PNG 存 `output/projects/<项目名>/`，便于追溯与二次修改。

## 配套网页工具

同一算法的纯前端版位于 `web/index.html`，支持拖拽上传、实时调参、本地 vendor 的 AI 抠图模型（失败自动降级 CDN / 内置算法）。启动：

```powershell
python -m http.server 43985 --bind 127.0.0.1 --directory "<skill目录>/web"
```

访问 http://127.0.0.1:43985/ 。适合用户自己精调参数；批量出图走 CLI。

## 边界与限制

- 经典抠图对「主体清晰 + 背景较简洁」的照片效果最好；复杂背景优先开 AI 抠图（CLI）或用网页工具（浏览器端模型），或跳过抠图。
- 生成的图为二创风格演绎，仅供个人娱乐，勿用于商业用途。