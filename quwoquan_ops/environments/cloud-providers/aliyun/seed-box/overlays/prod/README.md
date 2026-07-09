# 阿里云 prod overlay

入口：`quwoquan_ops/environments/kustomization/aliyun-prod`，引用 `quwoquan_service/services/seed-box/deploy/kustomize/overlays/prod`。

云特定 patch（LB annotations 等）可置于 `patches/` 并在根 kustomization 中引用 `quwoquan_ops/environments/cloud-providers/aliyun/seed-box/patches/...`。
