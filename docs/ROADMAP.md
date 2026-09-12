# ROADMAP · 长期开发计划（2026-09-12 ZCode 交接轮制定；同日完整开发轮状态回写见文末）

> 最终目的（用户 2026-09-12 定义）：
> **① 全本地**：用本地模型 + skill 制作明日方舟 / 终末地**所有种类**蚀刻章，并按用户要求迭代修改；
> **② 任意 agent+skill**：不依赖本地模型，任何 agent（如 codex+skill）都能高规格交付蚀刻章
> （参照社区 minimal-zine-poster 类公开 skill 的执行逻辑）；
> **③ 一句话出提示词**：不依赖本地模型，任何 agent/网页 AI 按起手文档把用户一句话
> 转成面向 Google nano banana 的完整生图提示词（可附带参考图）。
> 三条线共享同一引擎与设计语言（PRTS 考据结论），各自独立可交付。

---

## 一、现状盘点（2026-09-12，含本轮修复后）

| 能力 | 现状 | 距离目标的差距 |
|---|---|---|
| 引擎（提取→蚀刻→合成） | ✅ 双游戏三风格（方舟 silver/plated/gold/stamp；终末地 ef_silver/ef_gold/ef_irid；糖果） | 方舟"种类章"（职业章等版式变体）、终末地更多章面版式未覆盖 |
| AI 纹章主路径 | ✅ 设计稿 JSON → 渲染，配视觉质检闭环 | 设计稿 schema 仅 10 种图元；缺"章种"维度的模板约束 |
| 视觉 API 适配（design_emblem.py） | ✅ OpenAI 兼容端点，环境变量配置，https 强制 | **已天然兼容本地视觉模型**（Ollama / llama.cpp server / vLLM / LM Studio 均提供 OpenAI 兼容接口）——只缺文档化"全本地"接线指引 |
| 离线兜底（line/silhouette/facet/icon） | ✅ 零网络零模型 | 抠图算法对复杂背景弱（有整图回退） |
| 本地抠图（网页端） | ✅ @imgly WASM，浏览器内推理 | CLI/引擎侧无本地 AI 抠图（可列可选增强） |
| Skill（SKILL.md） | ✅ DSH 形态，含质检闭环 | 未做模式路由与 references 拆分；未覆盖全部章种；输出契约未标准化 |
| nano banana 提示词 | ❌ 无 | 第 3 轮以 NANO_PROMPTS.md 起手文档形式交付 |
| 文档/法务 | ✅ 完整（含 2026-09-02 审核修复） | — |

## 二、产品线 ①：全本地（本地模型 + skill，全部章种 + 用户迭代）

**关键判断**：`design_emblem.py` 的 OpenAI 兼容设计已使"本地视觉模型"即插即用——用户在本地起
Ollama/LM Studio/vLLM 的视觉模型（如 qwen2.5-vl），设 `OPENAI_BASE_URL=http://127.0.0.1:PORT/v1`
即可全本地走主路径（回环 http 白名单已放行）。缺的是：接线文档、章种模板、迭代闭环。

### 里程碑 L1：全本地接线与章种盘点（小）
1. README/SKILL 增补「全本地模式」章节：本地 OpenAI 兼容端点接线步骤 + 推荐模型档位
   （视觉：qwen2.5-vl 7B/72B 档；抠图：@imgly 已本地；引擎本身零模型）。
2. 章种矩阵考据补全（依据 PROMPTS.md §三 与 reference/DESIGN_SPEC.md）：
   - 明日方舟：晋升章（银/镀层/金）、**种类章**（职业纹样版式，新增版式模板）、活动纪念章（金章已备）；
   - 终末地：银/金/炫彩之外，核对游戏内章面版式变体（挂扣/无挂扣、字面布局）；
   - 产出：`engine/templates/` 目录化（每章种一个 JSON 版式描述 → compose_* 参数化），
     避免继续堆叠 if/else。
3. 验收：全章种冒烟图 + PROMPTS §三 质检通过。

### 里程碑 L2：用户迭代闭环（中）
1. 「设计稿会话」：设计稿 JSON + 参数 + 用户修改意见 → 视觉模型/agent 增量修订 → 重渲染
   （skill 侧流程化：最多 N 轮，保留每轮产物）。
2. 参数记忆：`output/projects/<名字>/` 会话目录（design.json + manifest + 各轮 PNG），
   skill 约定读写，支持"上次那张，把剑换成杖"式修改。
3. 验收：同一会话内连续 3 轮修改，产物可追溯。

### 里程碑 L3：本地体验打磨（按需）
- CLI 本地 AI 抠图可选项（onnxruntime + 开源 matting 模型，需用户单独决策下载，≤ 数百 MB，
  严守 ≤1GiB 下载红线与 C 盘 >20GiB 铁律）；
- Web 工具与引擎模板对齐（新版模板移植完成后消除双实现漂移）。

## 三、产品线 ②：任意 agent+skill 高规格交付（参照 minimal zine poster 架构）

社区 minimal-zine-poster 类公开 skill 的可借鉴骨架：**模式路由（Generate / Prompt-only / Reference
Analysis / Photo Input + preservation 等级）→ references/ 分层加载 → prompt compiler →
quality gate → 变化纪律 → 标准输出契约**。

### 里程碑 A1：SKILL v2 重构（中）
1. `SKILL.md` 瘦身为路由层：四模式
   - **Generate（默认）**：照片/一句话 → 设计稿 → 渲染 → 质检 → 交付图；
   - **Prompt-only**：只要设计稿不渲染（对应"agent 无 Python 环境"场景）；
   - **Reference Analysis**：参考图/文件夹 → 归纳风格系统（固定/可变/残留三类结论）；
   - **Photo Input**：照片角色判定（edit target / reference / supporting insert）
     + 保留等级（high/medium/low）——zine poster 的 preservation 概念直接复用。
2. 新增 `references/`（skill 目录内，随 skill 分发）：
   - `style-system.md`：设计语言系统化（自 DESIGN_SPEC.md 升华：几何、色板、明度三档、图元库）；
   - `prompt-compiler.md`：设计稿 JSON 编译规范（schema + few-shot + 反例）；
   - `quality-gate.md`：PROMPTS §三 清单升级为可判 PASS/FAIL 的门禁；
   - `variation-engine.md`：多候选纪律（布局族/母题/饰件系统的变化，不止换参数）。
3. 输出契约标准化（对齐 zine poster 格式）：生成图 + 最终提示词 + 模式/配方/保留说明。
4. PORTING.md 更新：Codex/Claude 投放路径（`~/.codex/skills/`、`~/.claude/skills/`）与
   双 shell 命令示例。

### 里程碑 A2：可交付规格（小）
- "高规格交付"定义固化为 checklist：质检门禁全过 + 会话产物齐备 + 告警（回退/降级）如实告知；
- batch_test 扩展为回归基准（对 samples 集的像素/指标基线）。

## 四、产品线 ③：一句话 → nano banana 提示词（本轮第 3 轮落地）

- 交付 `NANO_PROMPTS.md`（根目录，自包含起手文档）：任何 agent/网页 AI 读它即可把用户
  一句话转成 nano banana（Gemini 图像模型）可用的完整提示词；
- 编写方法论遵循《AI 提示词工程师规则 v2》（外部参考，不入库）：角色锚定、JSON/模块化结构、
  "如果识别到X就执行Y"条件句式、参数化 @param、防护性约束（preserve_*/additive_only）、
  迭代修正模块；
- 内容上融合本项目设计语言（PROMPTS.md 的三档明度/对称构图/图元词汇/章种要素），
  输出为英文描述性段落（nano banana 对自然语言段落响应最佳）+ 可选参数化模块 + 负向约束；
- 支持可选参考图：声明参考图用途（主体参考/风格参考）与保留等级（同产品线②的语义）。

## 五、协作与工程规范（zcode ↔ dsh 交接面）

1. **分支模型**：开发一律走 `dev/<who>-<date>` 短分支，验证后合回 master；
   公开仓库以内容快照方式同步（不共享提交历史），推送前必须通过 §四 审核清单。
2. **每轮流程**：状态评估（干净树/磁盘铁律）→ 计划文档 → 实现 → 验证
   （冒烟 + 像素回归）→ commit（中文 conventional，一笔一主题）→ CHANGELOG。
3. **回归红线**：模板/管线改动必须跑三风格冒烟 + 与基线像素比对（本轮建立的
   worktree + ImageChops 比对法，脚本化进 A2）。
4. **审计联动**：docs/AUDIT-FINDINGS.md 为安全基线；后续改动涉及
   网络面/输入解析时重新过一遍该清单。

## 六、里程碑顺序建议

```
第3轮(本轮)：NANO_PROMPTS.md          → 产品线③ MVP（零代码风险）
L1 全本地接线 + 章种盘点 → A1 SKILL v2 → L2 迭代闭环 → A2 交付规格 → L3 打磨
```
（②A1 与 ①L1 可并行；③ 在 A1 落地后可与 skill 路由层的 Prompt-only 模式合并成同一路由。）

## 七、风险与约束备忘

- 仓库体积：vendor @imgly 模型（数十 MB）需用户决策；大型本地模型**绝不入库**；
- 下载红线：任何模型/资产下载 ≤1GiB 且 C 盘剩余 >20GiB，缺一即停并报告；
- 法务：全部输出保持"玩家二创、勿商用"边界；官方素材仍只作研究参考不入库；
- 双实现漂移：web/index.html 与引擎的模板逻辑需在 L3 前保持人工同步，长期应单一化。

## 八、状态回写（2026-09-12 完整开发轮，分支 dev/zcode-dev-20260912）

| 里程碑 | 状态 | 落点 |
|---|---|---|
| L1 全本地接线 | ✅ 核心完成 | 本地视觉链路端到端验收通过（Ollama 便携 + qwen2.5vl:7b → design JSON → 出章）；README/SKILL「全本地模式」章节；章种注册表 `--list-types` |
| L1 章种版式 JSON 模板化 | ⏳ 未做 | 色彩/几何参数仍内嵌 compose_*；新增章种版式时再做 |
| A1 SKILL v2 | ✅ 完成 | 路由层 + references 四件套 |
| L2 迭代闭环 | ✅ MVP 完成 | `--project` 会话目录（roundNN + 参数/告警/设计稿快照）；skill 侧流程已写入 |
| ③ 一句话提示词 | ✅ MVP 完成 | NANO_PROMPTS.md（交接轮）+ 引擎双向联动说明（本轮） |
| M2 vendor | ✅ 完成 | web/vendor/ 193MB，SHA-256 逐块校验，CDN 降为回退 |
| CLI 本地 AI 抠图 | ✅ 完成 | onnxruntime + silueta（D:\medal_models，环境变量驱动） |
| 本地视觉模型 | ✅ 完成 | D:\ollama 便携 + OLLAMA_MODELS=D:\ollama_models（挪动=改环境变量） |

下一轮建议：L1 章种版式 JSON 模板化 → 新章种扩充（种类章/职业章）→ L2 会话目录接入
design_emblem 自动归档 → web 新版模板移植收尾。
