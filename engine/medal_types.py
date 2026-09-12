# -*- coding: utf-8 -*-
"""章种注册表 · Medal Types Registry
================================
全部 style×tone 章种的机读清单：
- CLI `--list-types` 列出（供 agent/用户选择章种）；
- skill 与文档引用同一份事实源，避免文档与实现漂移。

新增章种：在此登记（视觉参数的 JSON 模板化见 docs/ROADMAP.md L1 后续项）。
视觉考据依据 reference/DESIGN_SPEC.md。
"""

MEDAL_TYPES = [
    # ===== 明日方舟 =====
    {"id": "arknights/silver", "game": "明日方舟", "style": "arknights", "tone": "silver",
     "name": "晋升蚀刻章（标准）",
     "elements": "哑光灰蓝底 + 半调网点 + 四层同心套环 + 放射密纹 + 嵌入式横幅字带；无挂扣、无高光带"},
    {"id": "arknights/plated", "game": "明日方舟", "style": "arknights", "tone": "plated",
     "name": "镀层蚀刻章（全息）",
     "elements": "银章骨骼不变，整面全息虹彩镀膜（随形附着于轮廓缘+环带），整体提亮柔化"},
    {"id": "arknights/gold", "game": "明日方舟", "style": "arknights", "tone": "gold",
     "name": "活动金章",
     "elements": "乳白珐琅底 + 深铜金线 + 内缘五角星星环；无全息光谱（与终末地金阶区分）"},
    {"id": "arknights/stamp", "game": "明日方舟", "style": "arknights", "tone": "stamp",
     "name": "朱砂印章",
     "elements": "纸面底 + 朱红线描 + 放射纹收弱；仅纹章路径支持（--mode emblem）"},
    # ===== 终末地 =====
    {"id": "endfield/ef_silver", "game": "终末地", "style": "endfield", "tone": "silver",
     "name": "蚀刻章·银色（初期）",
     "elements": "缎面银白阳极氧化 + 镜面高光带 + 顺向拉丝 + 顶部挂扣 + 单细深描边 + 角部数字 label"},
    {"id": "endfield/ef_gold", "game": "终末地", "style": "endfield", "tone": "gold",
     "name": "蚀刻章·金色（加工）",
     "elements": "暖金铜面替换银灰（骨骼不变），深棕蚀刻线，局部青绿虹移色块"},
    {"id": "endfield/ef_irid", "game": "终末地", "style": "endfield", "tone": "iridescent",
     "name": "蚀刻章·特殊镀层（炫彩）",
     "elements": "金色骨骼 + 整面全息光谱（橙→黄绿→青绿→蓝紫→粉）两道交叉 + 白色纹章"},
    # ===== 糖果贴纸 =====
    {"id": "candy/sticker", "game": "玩家二创", "style": "candy", "tone": "",
     "name": "糖果贴纸章",
     "elements": "die-cut 白胶边 + 粉彩底场（径向/波点）+ 奶油/金/暗红三色环 + 连续缝线 + 圆角名字气泡"},
]


def find(style: str, tone: str):
    for t in MEDAL_TYPES:
        if t["style"] == style and (not t["tone"] or t["tone"] == tone):
            return t
    return None


def list_types() -> str:
    lines = ["可用章种（--style × --tone）：", ""]
    for t in MEDAL_TYPES:
        lines.append(f"  {t['id']:<22} {t['name']}")
        lines.append(f"    {'':22} {t['elements']}")
    lines.append("")
    lines.append("纹章化模式（--mode）：emblem=AI设计稿主路径 | line 蚀刻线稿 | "
                 "silhouette 剪影 | facet 分面 | icon 图标化兜底")
    return "\n".join(lines)


if __name__ == "__main__":
    print(list_types())
