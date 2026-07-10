# 华为云 integration overlay

入口：`quwoquan_ops/environments/kustomization/huaweicloud-integration`，引用 `quwoquan_service/services/seed-box/deploy/kustomize/overlays/integration`。

云特定 patch（ELB/EVS 等）可置于 `patches/` 并在根 kustomization 中引用 `quwoquan_ops/environments/cloud-providers/huaweicloud/seed-box/patches/...`。
