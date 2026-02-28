# 火山引擎 integration overlay

入口：`deploy/kustomization/volcengine-integration`，引用 `deploy/service/seed-box/kustomize/overlays/integration`。

云特定 patch（CLB/存储等）可置于 `patches/` 并在根 kustomization 中引用 `deploy/cloud-providers/volcengine/seed-box/patches/...`。
