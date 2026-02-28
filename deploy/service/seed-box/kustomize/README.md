# seed-box Kustomize

## 目标

以 all-in-one（Go）+ recommendation（Python Sidecar）为默认发布形态，
并通过同一套 overlays 统一环境参数。

## 目录

- `base/`：跨环境稳定模板（Deployment、Service、HPA、PDB）
- `overlays/dev`：开发态参数
- `overlays/integration`：集成态参数
- `overlays/prod`：生产态参数

## 参数化键

overlays 通过 `configMapGenerator + replacements` 注入：

- `APP_ENV`
- `CONFIG_VERSION`
- `IMAGE_VERSION`
- `REPLICAS`
- `HPA_MIN_REPLICAS`
- `HPA_MAX_REPLICAS`
- `HPA_CPU_AVG`
- `HPA_MEM_AVG`

## 渲染

```bash
kustomize build deploy/service/seed-box/kustomize/overlays/dev
kustomize build deploy/service/seed-box/kustomize/overlays/integration
kustomize build deploy/service/seed-box/kustomize/overlays/prod
```

## 拆分独立 Pod 指引

当某个领域服务需要独立发布或扩缩容时，按以下原则拆分：

1. 复制 `base/` 形成新的服务基础模板
2. 复用同一套参数键与 overlays 结构
3. 更新 `deploy/shared/process_domain_mapping.yaml`，保持 domain 唯一归属
4. 保持领域 API 路径与契约不变
