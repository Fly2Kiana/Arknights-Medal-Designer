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
     "name": "镀层蚀刻章（色相偏移）",
     "elements": "同骨骼整体色相偏移（成对素材实测：铜青→粉青）+ 提亮 + 轻珠光干涉"},
    {"id": "arknights/gold", "game": "明日方舟", "style": "arknights", "tone": "gold",
     "name": "活动金章",
     "elements": "乳白珐琅底 + 深铜金线 + 内缘五角星星环；无全息光谱（与终末地金阶区分）"},
    {"id": "arknights/stamp", "game": "明日方舟", "style": "arknights", "tone": "stamp",
     "name": "朱砂印章",
     "elements": "纸面底 + 朱红线描 + 放射纹收弱；仅纹章路径支持（--mode emblem）"},
    # ===== 终末地（v3：品阶五档 × 形制家族 story/combat/industry；色场数据驱动）=====
    {"id": "endfield/ef_silver", "game": "终末地", "style": "endfield", "tone": "silver",
     "name": "蚀刻章·银色（基础阶）",
     "elements": "浅银白金属（实测章面中位亮度 0.68≈175/255；旧文案「深冷灰 lum≈80」是深灰档，挂错在这里）+ 浅银蚀刻 + 右上→左下方向打光；story=章内铭牌框/角部注记，combat=章内名牌框+TIMES 计数，industry=胶囊条+圆盘表盘+双三角（三家族轮廓统一尖角正六边形，无切角无外凸件）"},
    {"id": "endfield/ef_gold_pure", "game": "终末地", "style": "endfield", "tone": "gold_pure",
     "name": "蚀刻章·纯金（收藏页金阶）",
     "elements": "哑光琥珀金（网格采样自收藏页卡片 collection/gold，实测中位 0.67）+ 右上高光→左下渐暗 + 米白蚀刻 + 斜插销钉/点阵装饰（对照 核心降落 等）"},
    {"id": "endfield/ef_gold", "game": "终末地", "style": "endfield", "tone": "gold_plated",
     "name": "蚀刻章·镀彩金（陈列大图金阶）",
     "elements": "亮橙侧缘 + 金黄顶 + 黄绿底的多方向渐变 + 红色点缀线 + 米白蚀刻（网格采样自陈列大图 showcase/gold，实测中位 0.82，比收藏页金阶亮一档）"},
    {"id": "endfield/ef_dark", "game": "终末地", "style": "endfield", "tone": "dark",
     "name": "蚀刻章·深灰（排名章）",
     "elements": "碳灰场（网格与实测 collection/dark 同源，中位 0.32≈82/255；旧网格 0.24 偏黑一档已修）+ 白蚀刻 + #N 排名角标（对照 锚定武陵/武陵工业先驱 系列）"},
    {"id": "endfield/ef_bronze", "game": "终末地", "style": "endfield", "tone": "bronze",
     "name": "蚀刻章·铜色（深灰派生档）",
     "elements": "派生档：与深灰共用色场网格，官方无独立铜色品阶；story/combat 与深灰逐字节相同，仅 industry 家族有铜色点缀（面板计数 86=铜14+银33+金39，铜只是计数档不是色档）；无 #N 角标"},
    {"id": "endfield/ef_pearl", "game": "终末地", "style": "endfield", "tone": "pearl",
     "name": "蚀刻章·镀层（虹彩珠光）",
     "elements": "白底柔和彩虹流（青→紫→粉）+ 深灰蚀刻；同一章的强化态渲染"},
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
