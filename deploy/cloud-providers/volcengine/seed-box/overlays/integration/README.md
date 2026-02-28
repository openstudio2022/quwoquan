# 火山引擎 integration overlay

Kustomization 已移至仓库根：`kustomization.volcengine.integration.yaml`，使用根路径 `deploy/service/seed-box/kustomize/overlays/integration`。

云特定 patch（CLB/存储等）可置于 `patches/` 并在根 kustomization 中引用 `deploy/cloud-providers/volcengine/seed-box/patches/...`。
