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
- `MODULE_PACKAGE`
- `MODULE_CATALOG_VERSION`
- `REPLICAS`
- `HPA_MIN_REPLICAS`
- `HPA_MAX_REPLICAS`
- `HPA_CPU_AVG`
- `HPA_MEM_AVG`

模块化约束：

- `MODULE_PACKAGE=seed-box` 对应 `deploy/shared/module_package_mapping.yaml` 中的 `seed-box` package。
- package 中启用的 module 必须属于 `process_domain_mapping.yaml` 中 `seed-box.domains`。
- 热点模块可拆分为独立 package，但拆分只改变 module 运行位置，不改变领域 API、Outbox 事实源或 task routing。
- `rec-model-service` 保持 Python sidecar/独立进程，不并入 Go `seed-box`。

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
