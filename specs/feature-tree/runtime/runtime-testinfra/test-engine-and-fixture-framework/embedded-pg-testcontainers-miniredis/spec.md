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
