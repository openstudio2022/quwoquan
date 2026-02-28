# Kustomization 入口

多云部署入口，按 `{cloud}-{env}/` 目录命名，每目录含 `kustomization.yaml`。kustomize build 仅接受目录参数，不接受 -f 文件。

**当前 CI/CD**：仅使用阿里云入口（`aliyun-integration`、`aliyun-prod`）。volcengine、huaweicloud 保留供本地或手动切换。

| 目录 | 云 | 环境 |
|------|----|------|
| aliyun-integration | 阿里云 ACK | integration |
| aliyun-prod | 阿里云 ACK | prod |
| volcengine-integration | 火山引擎 VKE | integration |
| volcengine-prod | 火山引擎 VKE | prod |
| huaweicloud-integration | 华为云 CCE | integration |
| huaweicloud-prod | 华为云 CCE | prod |

**使用**：
```bash
# integration
kustomize build deploy/kustomization/aliyun-integration
make deploy-integration CLOUD_PROVIDER=aliyun

# prod
kustomize build deploy/kustomization/aliyun-prod
```
