# 火山引擎 integration overlay

入口：`quwoquan_ops/environments/kustomization/volcengine-integration`，引用 `quwoquan_service/services/seed-box/deploy/kustomize/overlays/integration`。

云特定 patch（CLB/存储等）可置于 `patches/` 并在根 kustomization 中引用 `quwoquan_ops/environments/cloud-providers/volcengine/seed-box/patches/...`。
