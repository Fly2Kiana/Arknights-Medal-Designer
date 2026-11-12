# 用法与提示词指南 · Usage & Prompt Guide

本指南说明如何驱动方舟蚀刻章设计器，以及如何写一条好的纹章设计提示词。引擎接口与模型无关：一张照片 + 可选的设计稿 JSON → 一枚蚀刻章 PNG。

## 一、管线总览

```
输入照片
  ├─ 主路径：视觉模型设计纹章（JSON）→ 引擎渲染
  └─ 兜底：  引擎直接蚀刻主体（line / silhouette / facet / icon）
  → 蚀刻章 PNG
```

若当前模型自带视觉，可直接设计纹章并自检成品；否则把设计委派给任意可用视觉模型，或走离线兜底。引擎本身不依赖任何模型。

## 二、纹章设计原则

一条好的纹章提示词遵循几条原则：

- **转译不临摹**：提取主体一两个标志性特征，重构成纹章母题——交叉元素、环带包围、放射星芒、菱形/星形饰件、底部字带收口。
- **均衡构图**：主母题居中、饰件环绕，保持对称或 X 形中心对称。
- **有限明度**：用蚀刻暗线、中调与亮面，而非平滑渐变。
- **游戏关联母题**：游戏相关主体先识别角色/物件，取其标志符号（如兔耳 + 黑环、光环/羽翼、猫耳、菱形徽、源石结晶）作母题，而非泛化图形。

设计以一组几何图元（多边形、圆、线、弧、矩形、贝塞尔、星形、放射星芒、月桂、缎带）表达，存为 JSON 文件。装饰原语优先于纯矩形，让成品读起来是蚀刻纹章而非简笔画。引擎对常见格式差异做了归一化。

想要无需引擎、可直接投给生图模型的提示词，见 [NANO_PROMPTS.md](NANO_PROMPTS.md)。

## 三、成品自检

交付前确认成品到位：干净的尖角正六边形；风格识别特征齐备；纹章读起来是「设计过的」而非「处理过的照片」；铭文居中清晰；装饰在章内、无穿模；品阶正确。完整标准见 [references/quality-gate.md](references/quality-gate.md)。

## 四、参数速查

```
python engine/badge_engine.py <输入> -o <输出.png>
  --style arknights|endfield|candy        # 哑光金属 / 阳极氧化金属 / 糖果贴纸
  --tone  silver|plated|gold|stamp        # 方舟品阶（stamp=朱砂印）
          silver|gold_pure|gold_plated|dark|bronze|pearl   # 终末地品阶
  --endfield-family story|combat|industry # 终末地形制家族
  --mode emblem|line|icon|facet|silhouette # emblem=AI 设计稿主路径
  --emblem-design <设计稿.json>            # 配合 --mode emblem
  --emblem-style lineart|flat             # 蚀刻线稿 / 扁平填充
  --polarity dark-on-light|light-on-dark  # 浅底深线 / 深底白线
  --carve machine|hand                    # 机器刻 / 手工金石味
  --text / --subtitle / --serial / --number   # 铭文与数字层级
  --line-strength 0.4~1.8  --detail 0.5~2.0  --matting-tol 18~34
```

常用组合：
- 方舟金属风：`--style arknights --tone silver --mode emblem --emblem-style lineart --polarity light-on-dark`
- 社区浅银风：`--style arknights --tone silver --mode emblem --polarity dark-on-light`
- 糖果贴纸风：`--style candy --mode emblem`
- 目录级批量压测：`python engine/batch_test.py <目录> [--quick]`
- 无视觉环境的 API 适配：`python engine/design_emblem.py <照片> -o design.json [--render out.png --style ...]`
  （`OPENAI_API_KEY` 必填；`OPENAI_BASE_URL`/`OPENAI_MODEL` 可选；正式出图建议用指令跟随强的视觉模型）

## 五、已知边界

- 经典抠图对复杂背景照片会碎片化 → 自动整图回退并告警。高密度场景推荐 `facet`、网页端 AI 抠图，或可选的 CLI 本地 AI 抠图。
- 网页工具与引擎共用同一套模板与品阶。