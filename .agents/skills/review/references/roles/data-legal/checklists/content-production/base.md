# data-legal · content-production

- [MUST] 素材来源、授权、肖像与可商用性均可追溯。
  check: 抽样 release ledger；任一素材缺来源或对应授权记录时判失败。
- [MUST] blocked 来源、平台水印和长句复现已被判否。
  evidence: content-publish-purity
- [MUST] 权利存疑素材从本次 release 排除，不以风险备注放行。
  check: 对照风险清单与 manifest；存疑素材仍在发布闭包时判失败。
