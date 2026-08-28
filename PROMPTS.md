# 方舟蚀刻章设计器 — 自包含操作手册（PROMPTS.md）

> 本文件让**任何模型**（无论是否自带视觉）都能独立执行完整生产闭环：
> 看图 → 设计纹章 → 引擎渲染 → 视觉质检 → 交付。
> 引擎接口是模型无关的：`照片路径 + 设计稿 JSON → PNG`。

---

## 一、管线总览

```
输入照片
   │
   ├─[主路径] 视觉模型读图 → 输出几何图元设计稿 JSON（模板见§二）
   │               │
   │               ▼
   │          python engine/badge_engine.py <照片> --mode emblem
   │                --emblem-design <design.json> [风格参数见§四]
   │               │
   ├─[兜底路径] --mode line|icon|facet|silhouette（离线，无需设计稿）
   │
   ▼
   视觉质检（清单见§三，未过项回改设计稿/参数重跑）
   ▼
   交付
```

**视觉能力自适应**：若当前模型自带图像识别 → 直接 `read_image` 看图与质检；
否则 → 委派任意可用视觉子模型执行 §二/§三 的读图任务。引擎本身不依赖任何模型。

---

## 二、纹章设计提示词模板（把照片抽象成蚀刻章纹章）

### 设计原则（写给设计模型）
1. 这是「转译」不是「临摹」：提取主体 1~2 个标志性特征作母题，与纹章元素组合
   （交叉元素、环带包围、放射星芒、菱形/星形饰件、底部字带收口）
2. 对称（或 X 形中心对称）构图，主母题占中央约 55~65%，饰件环绕
3. 三档硬明度 0.22 / 0.55 / 0.88；粗轮廓（宽 14~22）配细内部线（宽 6~10）
4. 若照片与游戏相关（如明日方舟角色），先做**游戏关联分析**：
   识别角色/物件 → 提取其标志性符号（兔耳+黑环=阿米娅、光环/羽翼、猫耳、罗德岛菱形徽、源石结晶等）
   → 以这些符号为母题，不得输出与游戏无关的泛化图形

### 图元格式（坐标 0..1000，每设计 18~40 个图元，一行严格 JSON）
```json
{"shapes":[
  {"t":"poly","pts":[[x,y],...],"fill":0.55,"stroke":0.22,"w":10},
  {"t":"circle","cx":x,"cy":y,"r":r,"fill":0.88,"stroke":0.22,"w":8},
  {"t":"line","x1":0,"y1":0,"x2":0,"y2":0,"lum":0.22,"w":8},
  {"t":"arc","cx":0,"cy":0,"r":0,"a0":0,"a1":360,"lum":0.88,"w":6},
  {"t":"rect","x0":0,"y0":0,"x1":0,"y1":0,"fill":0.55,"stroke":0.22,"w":10},
  {"t":"bezier","p0":[x,y],"p1":[x,y],"p2":[x,y],"p3":[x,y],"stroke":0.22,"w":9},
  {"t":"star","cx":0,"cy":0,"r1":20,"points":5,"rot":-90,"fill":0.88,"stroke":0.22,"w":3},
  {"t":"sunburst","cx":0,"cy":0,"r0":40,"r1":200,"count":16,"stroke":0.55,"w":6},
  {"t":"laurel","cx":0,"cy":0,"length":240,"angle":30,"branches":9,"stroke":0.22,"w":8},
  {"t":"banner","x0":0,"y0":0,"x1":0,"y1":0,"fold":26,"fill":0.55,"stroke":0.22,"w":10}
]}
```
- 装饰原语优先（bezier/laurel/sunburst/star/banner），避免“画图板简笔画感”
- 渲染器已做格式归一化：`pts` 可为 "x,y x,y" 字符串；`fill:"none"`/`stroke:"none"` 视为空；
  `rect` 可用 x/y/w/h；`arc` 可用 a1/a2；`line` 可用 stroke 表示线色——但仍建议按标准格式输出

### 多候选策略（质量不稳定时）
同输入出 3 个互不相同的概念设计稿 → 视觉评审排序 → 选优者渲染；
不过线（§三）则按评审意见修订重跑，最多 2 轮。

---

## 三、视觉质检清单（逐项验收，发现问题回改重跑）

**A. 章体结构**
- [ ] 六边形为正六边形（宽高比 0.866，偏差 ≤1%），无压缩拉伸
- [ ] 顶点完全合拢：miter 尖角、无空隙、无凸起
- [ ] 糖果风：三色环（奶油/金/暗红）分层清晰完整、缝线在白胶边内且全周连续
- [ ] 金属风：多层套环 + 网点 + 暗角 + 刻槽，纹章镂空处透出章底纹理（无垫板割裂）

**B. 主体纹章**
- [ ] 读起来是“设计过的纹章”，不是“处理过的照片”
- [ ] 有游戏关联元素（若输入与游戏相关）
- [ ] 主母题占 55~65%，无孤立/空洞

**C. 文字**
- [ ] 精确居中（中心轴偏差 ≤1px）、无错位、无溢出气泡/字带
- [ ] 金属风：缎带式字带（端部收角+双细线+菱形分隔），Bahnschrift/雅黑粗体
- [ ] 糖果风：幼圆/Arial Rounded 圆体 + 字距跟踪，气泡完全落在内环之内

**D. 图层与冲突**
- [ ] 名字气泡/字带不与边框环、装饰、主体重叠（穿模=硬错误）
- [ ] 装饰全部在章内，无出界残留
- [ ] 外沿裁切干净，无杂散像素

**E. 质感**
- [ ] 糖果风：贴纸凸起（白描边+软投影+高光）、die-cut 内阴影、纸质纹理
- [ ] 金属风：网点铺满、哑光颗粒、极轻冷蓝偏光

**验收基准（视觉评审 0~1）**：糖果 ≥0.85 / 金属 ≥0.85 / 游戏关联 ≥0.7 可交付。

---

## 四、引擎参数速查

```
python engine/badge_engine.py <输入> -o <输出.png>
  --style arknights|endfield|candy      # 官方金属 / 终末地 / 糖果贴纸
  --tone silver|plated|gold|stamp       # 方舟品阶（stamp=朱砂印章）
        silver|gold|iridescent          # 终末地品阶（银/金/炫彩）
  --mode emblem|line|icon|facet|silhouette   # emblem=AI设计稿主路径
  --emblem-design <设计稿.json>          # 配合 --mode emblem
  --emblem-style lineart|flat           # 蚀刻线稿 / 扁平填充
  --polarity dark-on-light|light-on-dark  # 浅底深线(社区主流) / 深底白线(官方)
  --carve machine|hand                  # 机器刻 / 手工金石味
  --text / --subtitle / --serial / --number   # 铭文与数字层级
  --line-strength 0.4~1.8  --detail 0.5~2.0  --matting-tol 18~34
```

组合速记：
- 官方金属风：`--style arknights --tone silver --mode emblem --emblem-style lineart --polarity light-on-dark`
- 社区浅银风：`--style arknights --tone silver --mode emblem --polarity dark-on-light`
- 糖果贴纸风：`--style candy --mode emblem`（默认 lineart→flat 由 tone=candy 自动处理）
- 批量压测：`python engine/batch_test.py <目录> [--quick] [--tol-sweep]`
- 无视觉环境 API 适配：`python engine/design_emblem.py <照片> -o design.json [--render out.png --style ...]`
  （环境变量 `OPENAI_API_KEY` 必填；`OPENAI_BASE_URL`/`OPENAI_MODEL` 可选）
  （GLM 类端点注意：默认 `--max-tokens 1024`；其它端点可用 `--max-tokens` 调大）

---

## 五、实现要点备忘

1. 金属风镀层后处理保存透明通道（alpha 随输出保留）
2. 设计纹章路径不铺设场色底板（仅整图回退时铺设）
3. `--polarity` 与底色极性需匹配（金属风建议 light-on-dark）
4. 六边形几何：宽=√3·R、高=2R；糖果风使用固定几何参数
5. 缝线图层绘制顺序：场底与环之后，内缩 R+24 避开顶点衬垫
6. 主体与气泡防穿模：气泡宽度按所在高度六边形内宽动态封顶

---

## 六、已知边界

- 经典抠图对复杂背景照片会碎片化→自动整图回退（警告提示）
- 高密度场景（集市/建筑群）经典路径偏弱，推荐 facet 或网页端 AI 抠图
- 网页工具（web/index.html）为早期模板版本，新版模板尚未移植
