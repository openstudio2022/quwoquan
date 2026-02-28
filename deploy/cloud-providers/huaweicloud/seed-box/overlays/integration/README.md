# 华为云 integration overlay

入口：`deploy/kustomization/huaweicloud.integration.yaml`，引用 `deploy/service/seed-box/kustomize/overlays/integration`。

云特定 patch（ELB/EVS 等）可置于 `patches/` 并在根 kustomization 中引用 `deploy/cloud-providers/huaweicloud/seed-box/patches/...`。
