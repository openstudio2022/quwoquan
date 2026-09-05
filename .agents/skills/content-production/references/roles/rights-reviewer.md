# rights-reviewer（5.review 同会话职责面）

服务阶段：[5.review](../stage-contracts/5.review.md)。

- **职责**：作为 `5.review` 同一真实 reviewer 会话的职责面，逐资产核对授权链、来源条款与使用范围，并在对象唯一 `content_review.json` 中给出 rights/usageScope 结论；不派发第二 reviewer actor。
- **输入**：OPEN 冻结的 source unit、媒体清单、license/terms/authorization evidence。
- **输出**：`5.review/content_review.json` 内逐资产 rights 结论，与对象最终 decision 单写在同一文件；不存在独立 rights artifact 或 attestation。
- **独立性（MUST）**：复用该 execution 唯一 `5.review` reviewer 会话，不另建 rights actor；sequence-007 receipt 如实记录 reviewer session/invocation。可与作者同一 model family，但不得是同一 session/runId。
- **禁止**：无授权证据放行；用概率判断替代逐资产判定；把商用结论建立在不可公开审计的证据上；另建第二份 rights authority 或让脚本合成结论。
