---
name: arknights-medal-designer
description: 将用户上传的照片自动制作成《明日方舟》或《明日方舟：终末地》风格的蚀刻章图片。触发场景：用户提到「蚀刻章」「照片变蚀刻章」「明日方舟蚀刻章生成」「终末地蚀刻章制作」，或上传照片并希望转成游戏风格金属蚀刻章；也适用于用户只要蚀刻章生图提示词（nano banana/Gemini）或要求分析参考图风格。自动完成主体提取、XDoG 蚀刻风格化与章体合成，渲染全程本地处理。
---

# 方舟蚀刻章设计器 · Arknights Medal Designer（SKILL v2）

把**任意图片**（人像、武器/器物图标、风景照、几何徽标……）变成《明日方舟》官方风格蚀刻章或
《终末地》阳极氧化金属风蚀刻章 PNG。引擎具备输入感知与抽象化能力，不专精某一类题材。
设计语言参照 PRTS 公开官方素材归纳，固定/可变系统见 `references/style-system.md`。

## 模式路由（先选最小满足模式，意图模糊但要求"做一张"时走 Generate）

| 模式 | 触发 | 流程 |
|---|---|---|
| **Generate**（默认） | 照片/一句话 + "做一张/做成章" | 照片 → 设计稿 → 渲染 → 质检 → 交付图 |
| **Prompt-only** | 明确只要提示词；或当前环境无 Python 无法渲染 | 走 `NANO_PROMPTS.md` 产出面向 nano banana 的提示词，不渲染、不得暗示已出图 |
| **Reference Analysis** | 参考图/文件夹 + "分析/提炼风格" | 产出固定系统/可变系统/残留三类结论，不生成图（除非同时要求） |
| **Analyze + Generate** | "先分析参考再做一张" | 先 Reference Analysis，再以结论进 Generate |

## Photo Input（照片输入时先做，再选母题）

为每张照片判定角色：
- **Edit target（编辑目标）**："把这张照片做成章 / 保留这个人/宠物" → 照片主体必须出现在章上
- **Reference image（风格参考）**："参考这张图的风格/配色" → 只取视觉语法，不复刻主体
- **Supporting insert（素材插入）**："把照片里的这个物体放进去" → 取指定局部

无法从措辞判断且两种角色都合理时才提问；"做一张"+附照片 默认按 edit target（丢弃主体是
破坏性更大的解释）。

并记录一个**保留等级**（写进交付说明）：
- **High**：人/宠物/角色/作品默认档——保留可辨识特征（脸型发型、毛色分区、武器轮廓、
  标志配色），只做纹章化转译；除非用户明示允许再诠释
- **Medium**：保留主体与主要特征，允许裁切/缩放/色板/表面处理/周边构图变化
- **Low**：仅参考视觉语法，不保留主体身份与原构图

## 能力与流程（Generate 主链路）

1. **输入感知**：检测透明通道与内容类型；带 alpha 的设计资产直接使用并保持锐利，照片走
   抠图 + 纹理压平（中值滤波+细节回注）。可选 AI 抠图：`MEDAL_AI_MATTING=1` +
   `MEDAL_MATTING_MODEL=<u2net族.onnx>` 时引擎优先用本地 onnx 模型，失败自动回退经典算法。
2. **主体提取**：边界泛洪 + 背景主色屏障 + 多部件保留 + 孔洞填充；低置信自动回退整图并以
   圆角羽化融入章面（stderr 告警，必须转告用户）。
3. **蚀刻纹章化**四种模式：`line` 蚀刻线稿（默认）/ `silhouette` 剪影 / `facet` 分面 /
   `icon` 图标化兜底。
4. **章体合成**：
   - `arknights`：`silver` / `plated`（整面全息镀膜）/ `gold`（活动金章）/ `stamp`（朱砂印章）
   - `endfield`：`silver` → `gold` → `iridescent` 三阶进化；章面文字极简
   - `candy`：糖果贴纸章（白胶边/三色环/缝线/名字气泡）

## 如何调用

引擎脚本位于本 skill 目录下 `engine/badge_engine.py`，仅依赖 Python 3.10+ 与 numpy、Pillow
（可选：onnxruntime 用于 AI 抠图）。

```powershell
$env:PYTHONIOENCODING='utf-8'
python "<skill目录>/engine/badge_engine.py" "<输入照片路径>" -o "<输出.png>" --style arknights --text "名字" --subtitle "副标" --serial "编号"
```

参数说明：
- `--style`：`arknights`（默认）| `endfield` | `candy`
- `--tone`：方舟 `silver|plated|gold|stamp`；终末地 `silver|gold|iridescent`
- `--text`：主铭文（建议 ≤8 字）；`--subtitle`：顶部标签；`--serial`：编号；`--number`：数字层级
- `--line-strength`：0.4~1.8；`--detail`：0.5~2.0；`--matting-tol`：18~34（默认 26）
- `--no-matting`：跳过抠图整图入章
- `--mode`：`emblem`（AI 设计稿主路径，需 --emblem-design）| `line` | `icon` | `silhouette` | `facet`
- `--emblem-design`：AI 纹章设计稿 JSON 文件路径；`--emblem-style`：`lineart|flat`；
  `--polarity`：`dark-on-light|light-on-dark`；`--carve`：`machine|hand`

输出固定写进 `-o` 指定路径；不指定时写入项目 `output/` 目录。命令 stdout 打印最终文件路径，
stderr 可能出现告警（低置信回退/碎片化），**必须主动告知用户**。

## AI 设计纹章工作流（主路径，必读）

1. **看输入图并设计纹章**（视觉能力自适应：自带图像识别直接 read_image；否则委派任意可用
   视觉子模型；无任何视觉时可用 `engine/design_emblem.py` 走 OpenAI 兼容视觉 API——
   `OPENAI_API_KEY` 必填，`OPENAI_BASE_URL`/`OPENAI_MODEL` 可选，**该路径会把照片上传到所配
   端点，是全程本地的唯一例外**；配本地 Ollama/兼容端点即可全本地，见 README「全本地模式」）：
   - **先读本目录 `references/prompt-compiler.md`（编译纪律）与 `references/style-system.md`
     （固定/可变系统）**；完整设计提示词模板与图元规范见 `PROMPTS.md` §二
   - 核心规则：转译不临摹、三档硬明度 0.22/0.55/0.88、游戏输入必须做游戏关联分析
2. 设计稿存为临时 JSON 文件，调用引擎：
   `python engine/badge_engine.py <原图> --mode emblem --emblem-design <json路径> --style arknights --tone silver --text ...`
3. 出图后按 `references/quality-gate.md` 门禁逐项自检（G1–G14），不过线回改设计稿或参数重跑
   （最多 2 轮，2 轮规则见 gate），再按交付契约输出。
4. 多候选/批量任务遵循 `references/variation-engine.md`（相邻输出至少两个变化维度）。

无视觉能力且无可用子模型时降级：`--mode icon`（强分面+形态学清洗，图案感弱于主路径）。

## 迭代修改（用户要求改图时）

- 小改（文字/色调/品阶）：直接改参数重跑，最快
- 改构图/母题：改设计稿 JSON 对应图元后重跑（改图元不换骨架）；保留等级继续生效
- 会话产物管理：设计稿与各轮 PNG 存 `output/projects/<项目名>/`，便于追溯与二次修改

## 质检要求（必须）

出图后**不要直接交付**：按 `references/quality-gate.md` 的 G1–G14 门禁逐项自检；
发现问题按轮迭代后再交付。验收基准：糖果 ≥0.85 / 金属 ≥0.85 / 游戏关联 ≥0.7。

## 配套网页工具

同一算法的纯前端版「方舟蚀刻章设计器」位于本目录 `web/index.html`，支持拖拽上传、实时调参、
本地 vendor 的 AI 抠图模型（失败自动降级 CDN / 内置算法）。启动方式：

```powershell
python -m http.server 43985 --bind 127.0.0.1 --directory "<skill目录>/web"
```

访问 http://127.0.0.1:43985/ 。适合让用户自己精调参数；agent 侧批量出图走 CLI。

## 边界与限制

- 经典抠图对「主体清晰 + 背景较简洁」的照片效果最好；复杂背景请优先开 AI 抠图（CLI）或用
  网页工具（浏览器端模型），或勾选跳过抠图。
- 生成的图为二创风格演绎，仅供个人娱乐，勿用于商业用途。
