# L4 对象任务：embedded-pg-testcontainers-miniredis

## 功能说明
- **pg_suite.go**：使用 embedded-postgres 启动内存 PostgreSQL，执行 migration DDL，提供 truncate 清理，支持并发测试隔离。
- **mongo_suite.go**：使用 testcontainers-go 启动 MongoDB 容器，创建索引，提供 cleanup 删除测试数据。
- **redis_suite.go**：使用 miniredis 启动内存 Redis，支持 flush、时间控制（用于 TTL 测试）。

## 实现要点
- **embedded-postgres**：内嵌 PG 二进制，按 test_infra.yaml 配置端口、数据目录。
- **testcontainers**：拉取 mongo 镜像，按配置启动，执行索引脚本。
- **miniredis**：纯 Go 实现，无外部依赖，支持 FastForward 模拟时间。

## 约束
- 引擎选型与 _shared/test_infra.yaml 一致。
- 每个测试独立，Seed → Execute → Assert → Cleanup。

## 验收标准
- A1：三种引擎均可正常启动/CRUD/清理。
- A7：配置与 test_infra.yaml 一致。
- A8：各引擎自测通过。

## Folded current node `codegen-test-and-ci-integration`

# L5 横切：codegen-test-and-ci-integration

## 功能说明
- **Codegen 集成**：runtime-codegen 的 testmain.go.tmpl、fixture.go.tmpl、contract_test.go.tmpl 生成测试骨架，与 runtime-testinfra 的 TestSuite、Fixture、EventSpy 集成。
- **make test-contract**：一键运行全部契约测试，按聚合组织，使用 testinfra 引擎。
- **CI 集成**：GitHub Actions 或类似 CI 在每次 PR 时自动运行 make test-contract。

## 实现要点
- **Codegen 模板**：生成 TestMain 调用 pg_suite/mongo_suite/redis_suite；fixture 使用 testutil.Fixture；contract_test 含基本 CRUD 断言。
- **make test-contract**：遍历契约测试目录，执行 go test。
- **CI**：.github/workflows 或 Makefile 中定义 test-contract 步骤。

## 约束
- 生成的测试骨架与 test_infra.yaml、fields.yaml 一致。
- 业务代码零修改，仅切换连接地址。

## 验收标准
- A7：codegen 生成的 TestMain/fixture 与 metadata 一致。
- A8：make test-contract 一键运行；CI 每次 PR 自动运行。
