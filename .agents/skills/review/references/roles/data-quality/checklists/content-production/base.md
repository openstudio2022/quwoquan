# data-quality · content-production

本 workflow 只有这一名 reviewer；权利判据并入此表，不再派发第二专审。

- [MUST] producer 准出只要求 acquire/author/review 三份 seal receipt 连续闭合、逐对象 publish、explicit cohort 与 immutable producer handoff，不以任何环境消费结果作为完成条件。
  check: 读取三份 create-once receipts、逐对象 publish proof、explicit cohort ref/digest 与 immutable handoff identity/digest；缺任一 producer 事实或绑定不一致时判失败。
- [MUST NOT] 把环境 import/activate/readback 作为 producer 阶段、准出条件或回授信号；这些事实由 downstream 独立验证，且不得写入或改写 producer execution、receipt、handoff 或 terminal。
  check: producer handoff 出现 consumer/environment fact，或 downstream 结果触发 producer 重开、覆盖、补写时判失败。
- [MUST] schema、manifest、asset、source 与发布账本语义一致且事实可回溯。
  evidence: data-static-contract
- [MUST] 每个 release 资产的权利六字段 `sourceUrl/license/termsUrl/authorizationProof/usageScope/rightsStatus` 按现有 schema 在场，与实际来源及权利记录一致；许可、授权未知或版权保留如实记录，不补造作者、许可或授权证明。
  evidence: content-publish-purity
- [MUST NOT] 把许可白名单、`restricted`、`unverified/unknown` 或未获授权本身作为 producer 准出硬门；权利状态、accessPolicy 与 authorizationRequired 只记录，公众可见性由下游运营策略决定，冻结的 research/usageScope wire 取值不更改。
  check: 仅因权利类别拒绝，或以缺失证据伪造 verified/授权记录时判失败；字段缺失、来源/字节绑定不一致仍按现有 schema 与完整性门处理。
- [MUST NOT] 以旧回执、模板拼装或拍脑袋补全冒充本次生产证据。
  check: 对照本次 seal receipt digest；回执过期或事实无 source 时判失败。
