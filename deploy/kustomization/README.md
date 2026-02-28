# Kustomization 入口

多云部署入口，按 `{cloud}.{env}.yaml` 命名。resources 使用相对路径引用 `../service/seed-box/kustomize/overlays/{env}`。

**当前 CI/CD**：仅使用阿里云入口（`aliyun.integration.yaml`、`aliyun.prod.yaml`）。volcengine、huaweicloud 保留供本地或手动切换。

| 文件 | 云 | 环境 |
|------|----|------|
| aliyun.integration.yaml | 阿里云 ACK | integration |
| aliyun.prod.yaml | 阿里云 ACK | prod |
| volcengine.integration.yaml | 火山引擎 VKE | integration |
| volcengine.prod.yaml | 火山引擎 VKE | prod |
| huaweicloud.integration.yaml | 华为云 CCE | integration |
| huaweicloud.prod.yaml | 华为云 CCE | prod |

**使用**：
```bash
# integration
kustomize build -f deploy/kustomization/aliyun.integration.yaml
make deploy-integration CLOUD_PROVIDER=aliyun

# prod
kustomize build -f deploy/kustomization/aliyun.prod.yaml
```
