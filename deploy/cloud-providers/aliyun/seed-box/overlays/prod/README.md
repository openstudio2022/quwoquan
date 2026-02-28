# 阿里云 prod overlay

Kustomization 已移至仓库根：`kustomization.aliyun.prod.yaml`，使用根路径 `deploy/service/seed-box/kustomize/overlays/prod`。

云特定 patch（LB annotations 等）可置于 `patches/` 并在根 kustomization 中引用 `deploy/cloud-providers/aliyun/seed-box/patches/...`。
