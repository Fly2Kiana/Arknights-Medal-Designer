# 审核发现清单（2026-09-02 只读审核，修复依据）

> 审核对象：本地快照 + GitHub 公开仓库（当时 HEAD `e3110b31`）。
> 结论：无高危漏洞、无凭据泄漏、无恶意代码；本地快照与仓库 master 内容一致（仅换行符差异）。
> 本清单是 2026-09-12 修复轮（见 CHANGELOG Unreleased 节）的依据。
> **状态（2026-09-12 更新）**：M1/M2 文档化 ✅；L1 ✅；L2 ✅；L3 ✅；L4 ✅；L5 ✅；
> L6 双渲染/渐变热点 ✅（classicCut 微优化未做，量级可接受）；CI SHA 固化 ✅；
> v1.1 未随 HEAD 发版 → 移交 ROADMAP/推送清单；@imgly vendor → 移交 ROADMAP 待用户决策。

## 中

- **M1 隐私声明与 design_emblem.py 行为矛盾**：README（双语）"nothing is uploaded"、
  SECURITY.md "does not transmit user photos" 为全称否定，但 `engine/design_emblem.py`
  会把照片 base64 上传到 `OPENAI_BASE_URL` 视觉 API（文档化功能，SKILL.md 有如实说明）。
- **M2 网页端运行时从公共 CDN 加载代码**：web/index.html 动态 import
  `@imgly/background-removal@1.5.5`（esm.sh/jsdelivr/unpkg，版本已锁定，失败降级内置算法；
  照片不离开浏览器），但 CDN 投毒可致任意 JS 执行；模型资产另由该库自有 CDN 拉取。

## 低

- **L1** design_emblem.py 不强制 HTTPS：`http://` base URL 会明文发送 Bearer 密钥与照片。
- **L2** 第三方响应/设计稿解析防御不足：`call_vision` 的 `resp["choices"][0]...` 链式取值；
  `render_emblem` 顶层非 dict 会 AttributeError；laurel `branches:0` 除零；
  图元缺字段（banner/bezier）KeyError。
- **L3** 图像解压炸弹防护仅依赖 Pillow 默认值；web `toCanvas` 无降采样上限，超大图可致内存耗尽。
- **L4** web `setStatus` 用 innerHTML（当前无用户可控 HTML，不可利用，属习惯风险）。
- **L5** web `URL.createObjectURL` 从不 revoke（小内存泄漏）。
- **L6** 性能：candy+emblem 双重渲染设计稿；compose_arknights/compose_candy 逐像素 Python
  渐变（~115 万次/帧）；web classicCut 每像素分配数组。

## 信息级（部分本轮处理）

- CI actions 按标签引用（@v4/@v5）而非 SHA 固定；权限已是 contents: read（良好）。
- 标签 v1.1 停在 `ae76bbd`，HEAD（网页 v16 移植）未打标签/未发版。
- 无遥测、无硬编码凭据；reference/*.cjs 为研究脚本且输出 gitignored。
- 法务链路（MIT + NOTICE + 商标/二创声明）完整。

## 通过项（无需处理）

注入面（json.loads，无 eval/exec/pickle/subprocess）、凭据（无硬编码，密钥走环境变量 + ASCII
预校验）、外联清单、抠图回退与告警设计、固定种子可复现输出、CI 全绿矩阵。
