# Design: environment-process-domain-mapping

## 设计动因

服务既要支持开发态解耦（独立服务开发测试），又要支持集成/发布态组合部署。此前缺少统一拓扑声明，容易出现：
- 同一 domain 被重复挂载到多个进程
- 集成环境与生产拓扑不一致
- 部署拓扑变化影响对外接口认知

## 设计决策

1. **统一拓扑配置**
   - 使用 `deploy/shared/process_domain_mapping.yaml` 作为唯一真相
   - 结构为：`environments -> deploy_process -> domains`
   - deploy 目录分层为 `shared/service/app`，避免部署资产与领域代码耦合
   - `recommendation` domain 仅允许绑定 `recommendation-service`

2. **三态模型**
   - `dev`：默认独立服务进程（服务名即进程名）
   - `integration`：按发布拓扑运行，用于集成测试
   - `prod`：与 integration 拓扑一致，仅环境参数不同
   - `recommendation-service` 在三态均保持独立 Python 进程，不并入 Go 组合进程

3. **接口稳定原则**
   - 部署进程是运维抽象，不是领域抽象
   - 对外 API 继续按领域服务暴露，不随部署组合改变
   - Python/Go 语言差异不得影响 domain 契约语义（请求/响应/错误码）

4. **门禁策略**
   - 校验同一环境内 domain 唯一归属
   - 校验 process 名称规范（`*-service` 或 `quwoquan_service`）
   - 校验 `integration == prod` 映射
   - 接入 `make verify` 与 `scripts/gate_repo.sh`
   - `make gate-full` 必须包含并通过 `recommendation-service` Python 测试
   - recommendation-service 启动前执行配置分层与版本兼容校验；失败即 fail-fast

## 配置示例

```yaml
environments:
  dev:
    content-service:
      domains: [content]
    recommendation-service:
      domains: [recommendation]
  integration:
    recommendation-service:
      domains: [recommendation]
    quwoquan_service:
      domains: [content, chat, integration, user, circle, assistant, gateway, orchestrator]
  prod:
    recommendation-service:
      domains: [recommendation]
    quwoquan_service:
      domains: [content, chat, integration, user, circle, assistant, gateway, orchestrator]
```

## 适用场景与约束

适用：
- 单仓多服务，既要独立开发又要可组合发布

约束：
- 不允许一个 domain 在同一环境中多归属
- 不允许 integration/prod 拓扑漂移
- 不允许通过部署拓扑改写领域路由契约
