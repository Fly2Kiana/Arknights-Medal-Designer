# 方舟蚀刻章设计器 · Arknights Medal Designer

[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/) [![CI](https://github.com/Fly2Kiana/Arknights-Medal-Designer/actions/workflows/ci.yml/badge.svg)](https://github.com/Fly2Kiana/Arknights-Medal-Designer/actions/workflows/ci.yml) [![玩家二创](https://img.shields.io/badge/玩家二创-only-orange?style=flat-square)](#项目边界)

[English](README.md) | **简体中文**

把任意照片自动做成《明日方舟》/《明日方舟：终末地》风格蚀刻章（Medal）PNG：双游风格、多品阶模板，AI 纹章设计为主路径、经典算法离线兜底，全程本地处理。

> 二创声明：Arknights 为鹰角网络（Hypergryph）商标；本项目为玩家二创工具，与官方无关，仅供个人娱乐，请勿用于商业用途。

## 项目边界

- 不是官方素材导出器：引擎把输入「转译」为风格化纹章，不逐字临摹官方美术资源。
- 全程本地：照片在本机处理；网页工具仅在浏览器内加载 AI 抠图模型（`@imgly/background-removal`），失败自动降级内置算法，照片不上传。
- 仅限二创：输出为风格演绎，请勿商用或暗示官方背书。

## 项目组成

| 路径 | 职责 |
|---|---|
| `SKILL.md` | Agent skill 定义（对话内直接出图） |
| `engine/badge_engine.py` | 核心引擎：主体提取 → XDoG 蚀刻 → 章体合成（numpy + Pillow） |
| `engine/emblem_render.py` | 把 AI 设计的几何图元 JSON 渲染上章面 |
| `engine/design_emblem.py` | OpenAI 兼容视觉 API 适配器：照片 → 设计稿 JSON（给无视觉能力的 agent 环境） |
| `engine/batch_test.py` / `engine/gen_designs.py` | 真实照片压测工装 / 程序化纹章设计稿生成器 |
| `web/index.html` | 单文件网页工具（拖拽/调参/下载）——当前为早期模板版本，新版模板（终末地重做 + 糖果风）移植中 |
| `PROMPTS.md` | 自包含操作手册：设计提示词模板、质检清单、参数速查 |
| `PORTING.md` | 移植计划（技术方向规划，实施时间未定） |
| `reference/` | 考据抓取脚本（可再生成研究素材）+ `DESIGN_SPEC.md`（考据结论） |
| `samples/` | 测试素材 |
| `output/` | 运行时输出目录（gitignore，本地生成） |

## 风格与品阶

| 风格 | 品阶 | 主管线 | 状态 |
|---|---|---|---|
| 方舟（哑光金属） | `silver` / `plated` / `gold`（另有 `stamp`） | AI 纹章设计 → 渲染；离线兜底 `line`/`silhouette`/`facet`/`icon` | ✅ 已实现 |
| 终末地（阳极氧化金属） | `silver` / `gold` / `iridescent` | 同上 | ✅ 已实现 |
| 糖果贴纸 | — | 同上 | ✅ 已实现 |
| 网页工具新版模板移植（终末地重做 + 糖果风） | — | — | ⏳ 计划中 |

仅标注 **已实现** 的行为当前树中可用；计划项是方向，不是发布承诺。

## 安装

先备好环境：**Python 3.10+**（含 pip），以及任一使用入口——DSH agent 会话（skill 用法）、任意浏览器（网页工具）或终端（CLI）。运行期仅依赖 numpy + Pillow，无需 GPU。

### 交给 AI agent 安装

把下面的仓库地址与提示词发给你的编码 agent：

```text
从 https://github.com/Fly2Kiana/Arknights-Medal-Designer 安装 Arknights Medal Designer。
先检查 Python 3.10+ 与 pip。克隆到我同意的位置，运行 pip install -r requirements.txt，
然后跑冒烟测试：
python engine/badge_engine.py samples/sword_icon.png -o output/smoke.png --style arknights
并按 PROMPTS.md §三 质检清单核对尖角六边形、同心套环与字带是否正常。
不要运行 reference/ 下的抓取脚本（仅研究用，会下载第三方素材）。不要替我启动网页服务器。
装好并测试通过后告诉我。
```

### 手动安装

1. 检查环境。

   ```powershell
   python --version
   pip --version
   ```

   需要 Python 3.10+。Windows 无需额外字体配置（引擎使用系统自带字体）；mac/Linux 候选字体已列在引擎中，后续按 Roadmap 扩充。

2. 获取代码并安装仅有的两个依赖（numpy、Pillow，约 50MB，无 GPU）。

   ```powershell
   git clone https://github.com/Fly2Kiana/Arknights-Medal-Designer.git
   cd Arknights-Medal-Designer
   pip install -r requirements.txt
   ```

3. 跑冒烟测试并亲自核对成品。

   ```powershell
   $env:PYTHONIOENCODING='utf-8'
   python engine/badge_engine.py samples/sword_icon.png -o output/smoke.png --style arknights
   ```

   生成的 `output/smoke.png` 应呈现：尖角正六边形 + 多层同心细线套环 + 哑光网点底 + 蚀刻剑纹章 + 居中横幅字带；对照 `PROMPTS.md` §三 清单逐项核对（糖果 ≥0.85 / 金属 ≥0.85 / 游戏关联 ≥0.7）。`output/` 是本地运行时目录，仓库不附带生成图。

4. 三选一使用。

   **DSH agent skill（对话内直接出图）**：

   ```powershell
   Copy-Item -Recurse this-folder "$env:USERPROFILE\.agents\skills\arknights-medal-designer"
   ```

   装完新开一个会话，说「帮我做一张蚀刻章」并上传照片。skill 会走 AI 纹章设计主路径（视觉模型出设计稿 JSON → 本地渲染），经典算法离线兜底，交付前按清单自检。

   **网页工具（可视化精调）**：

   ```powershell
   python -m http.server 43985 --bind 127.0.0.1 --directory web
   # 打开 http://127.0.0.1:43985/
   ```

   拖入照片 → 选模板/色调/铭文 → 调线稿强度与细节密度 → 生成 → 下载 PNG。首次使用会在浏览器内加载 AI 抠图模型（`@imgly/background-removal`，约几十 MB，仅首次需网络）；加载失败自动降级内置经典算法。照片全程不出浏览器。

   **CLI（批量脚本化）**：

   ```powershell
   $env:PYTHONIOENCODING='utf-8'
   python engine/badge_engine.py photo.jpg -o out/my_badge.png --style arknights `
       --text "阿米娅" --subtitle "ROSMONTIS" --serial "NO.001"
   python engine/badge_engine.py photo.jpg --style endfield --text "终末地" --line-strength 1.2
   # AI 纹章主路径：
   python engine/badge_engine.py photo.jpg --mode emblem --emblem-design design.json --style arknights --tone silver
   # 目录级真实照片压测：
   python engine/batch_test.py samples --quick
   ```

   `--style` 选章体模板（`arknights` 哑光金属 / `endfield` 阳极氧化金属 / `candy` 贴纸），`--tone` 选品阶，`--mode emblem` 走 AI 设计主路径；不带 `--emblem-design` 时自动回退经典离线管线（`line`/`silhouette`/`facet`/`icon`）。输出写到 `-o`；不指定则写入本地 `output/`。Windows 上请设置 `PYTHONIOENCODING` 以正确渲染中文铭文。

5. 更新与卸载。

   ```powershell
   # 更新 git 克隆：
   git pull
   pip install -r requirements.txt     # requirements 变化时重跑
   # 更新已安装的 skill（重拷运行时子集）：
   Copy-Item -Recurse -Force `
     <repo>\SKILL.md, <repo>\PROMPTS.md, <repo>\engine, <repo>\web `
     "$env:USERPROFILE\.agents\skills\arknights-medal-designer"
   # 卸载 skill：
   Remove-Item -Recurse -Force "$env:USERPROFILE\.agents\skills\arknights-medal-designer"
   ```

   `reference/` 下的抓取脚本仅供研究，会下载第三方考据素材，日常使用不需要它们。切勿提交或传播经它处理的他人照片。

## 参数速查

| 参数 | 范围 | 说明 |
|---|---|---|
| `--style` | arknights / endfield / candy | 章体模板 |
| `--tone` | 方舟 silver/plated/gold/stamp；终末地 silver/gold/iridescent | 品阶 |
| `--text` | ≤8 字为宜 | 主铭文 |
| `--subtitle` | 可选 | 顶部标签 |
| `--serial` | 可选 | 编号注释 |
| `--number` | 可选 | 数字层级（如 100） |
| `--mode` | emblem / line / silhouette / facet / icon | emblem=AI 设计稿主路径 |
| `--emblem-design` | design.json 路径 | 配合 `--mode emblem` |
| `--line-strength` | 0.4–1.8 | 线稿强度 |
| `--detail` | 0.5–2.0 | 细节/排线密度 |
| `--matting-tol` | 18–34 | 抠图容差，背景杂乱调低 |

## 质量基线

视觉验收（`PROMPTS.md` §三）：糖果 ≥0.85 / 金属 ≥0.85 / 游戏关联 ≥0.7。

## 已知边界

- 经典抠图对「主体清晰 + 背景简洁」效果最好；低置信自动整图回退（圆角羽化）并提示。
- 网页工具仍是早期模板版本；新版模板（终末地重做 + 糖果风）尚未移植。
- 字体以 Windows 系统字体为主，mac/Linux 回退计划中（见 `PORTING.md`）。

## Roadmap

计划方向，非发布承诺：

1. 网页工具新版模板移植（终末地重做 + 糖果风）。
2. 字体跨平台兜底（mac/Linux）。

## 更多文档

- [PROMPTS.md](PROMPTS.md) —— 操作手册与质检清单
- [SKILL.md](SKILL.md) —— skill 定义
- [PORTING.md](PORTING.md) —— 移植计划
- [reference/DESIGN_SPEC.md](reference/DESIGN_SPEC.md) —— 考据结论
- [CHANGELOG.md](CHANGELOG.md) · [SECURITY.md](SECURITY.md) · [SUPPORT.md](SUPPORT.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [NOTICE](NOTICE)

## License

[MIT](LICENSE)。Arknights 等名称归各自权利人所有，详见文首二创声明。
