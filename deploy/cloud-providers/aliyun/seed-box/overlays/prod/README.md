# 阿里云 prod overlay

入口：`deploy/kustomization/aliyun-prod`，引用 `deploy/service/seed-box/kustomize/overlays/prod`。

云特定 patch（LB annotations 等）可置于 `patches/` 并在根 kustomization 中引用 `deploy/cloud-providers/aliyun/seed-box/patches/...`。
