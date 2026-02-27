# L3：metadata-domain-restructure

## 功能说明

将现有 `contracts/metadata/` 的平铺结构重组为以域服务为根节点的层级结构。
投影 YAML 迁入对应实体目录，OpenAPI 与 metadata 并置，codegen 工具路径同步更新。

## 范围

- 创建 `contracts/metadata/content/` 域目录，移入 `post/`
- `_projections/{photo,video,article,moment}_post.yaml` → `content/post/projections/`
- `openapi/content-service.v1.yaml` → `contracts/metadata/content/openapi.yaml`
- `_shared/errors/` 子目录（common_codes.yaml + http_mapping.yaml）
- 更新 codegen 工具默认路径，`make codegen-app` 产物不变

## 验收标准

- A1：`contracts/metadata/content/post/projections/` 含4个投影 YAML
- A2：codegen 工具读取新路径，`make codegen-app` 产物与重组前完全一致（hash 相同）
- A3：`contracts/metadata/content/openapi.yaml` 存在
- A4：`make verify-metadata` PASS
