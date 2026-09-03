# 载体契约：video

四载体共用十阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写
video 作品的差异判据。产物清单真相源是
`quwoquan_data/scripts/core/stage_artifact_contract.py`，此处不复制。

## 对象根与坐标

- 对象根：`posts/video/<angle>/<title>/<seq>/`，坐标由 `0.plan/target_set.json`
  冻结（同 article）。

## 各阶段差异

- `1.download`：与 image 同走 media source admission exact pair 冻结
  workUnit（L2 `design.md#dec-022`）；取得模块必须从已取得视频机械提取一帧 PNG poster，
  视频与 poster 写入同一 create-once CAS receipt。receipt 必须分别冻结两者的 ref、
  SHA-256、bytes、MIME；poster 明确声明为同 licensed video 的派生帧，并逐字段继承
  sourceUrl/license/termsUrl/authorizationProof/rightsStatus/rightsIssues。原子物化必须把
  两个对象都链接到 source unit `assets/` 并登记 `assets/index.json`。
- `3.compose`：证据包含视频源引用与叙事/剪辑意图；`4.draft` 必须由 AI 写 `video_script`。
- `4.draft`：物化前置判据含成片时长下限——sourced clip 短于 policy 下限时
  该对象 typed discard（`DATA.MEDIA.PUBLISHABLE_SHORTFALL`），不拖垮批次。
- `5.review`：`mediaRefReview.rightsReviews[]` 必须按 source-unit assetRef 分别覆盖
  视频和 poster；只有视频行、用视频结论隐含覆盖 poster，或任一 rights 字段与
  acquisition receipt 漂移都必须 fail closed。
- `publish`：物化需冻结 poster 身份（canonical video poster identity），且该身份
  必须回指已独立 rights-review 的 source poster CAS；
  跨 canonical 的视频内容与 poster 复用由事务核心拒绝。

## 状态

receipt 协议下 video lane 尚未走通首个对象；M100 里程碑计数为 10
（`GWT-004`），验收锚点绑定 `multi-carrier-release/spec.md` 的 `GWT-001`，
实现缺口按该 spec 的 OPEN 项跟踪。
