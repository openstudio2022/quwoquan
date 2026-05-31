# recommendation-platform（推荐 / ML 平台）

L1 非功能能力域：推荐与机器学习平台。下辖训练（rec-model-training）与推理（rec-model-service）两类工程，与 `runtime` 下的 Go 推荐引擎通过 HTTP 协作。

- 能力定位、子节点与约束：见 [spec.md](spec.md)。
- 工程资产映射（app / metadata / service / deploy / test）：见 [`specs/l1_index.yaml`](../../l1_index.yaml) `domain_services[key=recommendation-platform]`。

> 本目录为 L1 领域服务节点；具体能力按 L3 story 在子目录下以 `spec.md + acceptance.yaml` 落地，不在本层维护跨 story 设计决策。
