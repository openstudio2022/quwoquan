# data-quality · content-production

- [MUST] 产物已从受控输入走到 immutable release、导入与可读回执，不停在离线文件。
  check: 读取 execution/release/import/readback 身份；缺任一阶段或身份不同时判失败。
- [MUST] schema、manifest、asset、source 与发布账本语义一致且事实可回溯。
  evidence: data-static-contract
- [MUST NOT] 以旧回执、模板拼装或拍脑袋补全冒充本次生产证据。
  check: 对照本次 attempt/source digest；回执过期或事实无 source 时判失败。
