# 设计稿编译器 · Prompt Compiler（references/prompt-compiler.md）

> 把"主体 + 风格系统"编译成引擎可渲染的设计稿 JSON。schema 的完整图元语法、
> few-shot 示例与多候选流程见 `PROMPTS.md` §二；本文件定义编译纪律与反例。

## 一、编译输入

1. 主体描述（用户一句话 / 照片观察结论——经 Photo Input 模式处理后）
2. 风格决策：游戏（arknights/endfield/candy）× 品阶 × 极性（light-on-dark / dark-on-light）
3. 保留等级（见 SKILL.md Photo Input 节）：high 保留的特征必须进母题

## 二、编译硬规则

1. 坐标系 0..1000，原点左上；整体构图先草拟再填充图元
2. 每设计 18–40 个图元（弱模型可降到 12–20），装饰原语优先（bezier/laurel/sunburst/star/banner），
   避免"画图板简笔画感"
3. 明度只用三档：fill/stroke/lum ∈ {0.22, 0.55, 0.88}；描边宽：粗轮廓 14–22、内部细线 6–10
4. 对称构图：左右镜像的图元必须成对出现（可用引擎 gen_designs.py 的 mirror/rot 思路）
5. 输出一行严格 JSON：`{"shapes":[...]}`，禁止 markdown 围栏、注释、省略号、截断
6. 游戏相关输入必须先做游戏关联分析（PROMPTS.md §二规则 4），母题来自角色标志符号

## 三、反例（质检时直接打回）

- 用 20 档灰度画"渐变"→ 破坏三档硬明度（style-system 固定系统）
- 母题是"照片里的人物姿势照搬"→ 违反转译原则
- 图元 <12 且全是矩形 → 简笔画感，退回加装饰原语
- pts 用字符串但混入 "x" "y" 残缺 token（渲染器会静默跳过残缺点，构图残缺）
- 终末地章面画横幅字带 / 方舟章画挂扣 → 游戏识别特征张冠李戴（style-system 一、固定系统）

## 四、渲染与自检回路

```powershell
python engine/badge_engine.py <照片> --mode emblem --emblem-design design.json \
    --style <style> --tone <tone> --text <铭文>
```
出图后立即走 quality-gate（references/quality-gate.md）；不过线 → 按 gate 指出的条目
改设计稿（改图元，不换构图骨架）重跑，最多 2 轮。
