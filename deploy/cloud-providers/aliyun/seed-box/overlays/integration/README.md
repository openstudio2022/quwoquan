# 阿里云 integration overlay

入口：`deploy/kustomization/aliyun-integration`，引用 `deploy/service/seed-box/kustomize/overlays/integration`。

云特定 patch（LB annotations 等）可置于 `patches/` 并在根 kustomization 中引用 `deploy/cloud-providers/aliyun/seed-box/patches/...`。
