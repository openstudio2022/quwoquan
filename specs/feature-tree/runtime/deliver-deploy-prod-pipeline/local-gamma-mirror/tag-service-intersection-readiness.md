# tag-service 交集真打 · local-gamma 接入与环境就绪清单

> V4 历史债统一清理（G3）产出。本文件登记 tag-service 在门禁与 local-gamma 的接入现状、
> 交集 `sharedTags` 真打闭环的操作步骤，以及需 Docker/Colima/patrol 的环境后续项。
> 与 R03/R02「登记显性化」一致：可门禁验证项已闭合，需运行环境的项显性登记、步骤就绪。

## 1. 已闭合（零环境，随门禁验证）

- **构建**：`tag-service` 已入根 `quwoquan_service/Makefile` 的 `build` 目标（`go build ./services/tag-service/...`）。
- **测试入门禁**：`quwoquan_service/scripts/gate.sh` 增 `go test ./services/tag-service/... -count=1`。
  - 无 Docker 本地：`testmain_test.go` 优雅 `os.Exit(0)` skip；
  - CI（`CI=true` / `GITHUB_ACTIONS=true`）：强制起 mongo testcontainer，缺 Docker 即 panic 暴露。
- **501 闭合**：`search / related / search-by-tags / graph/cooccurrence / related-objects` 已基于
  只读 `TagNode` / `ObjectTagIndex` 实现并补 api_integration contract 断言；`feedback` 保留 501（见 §4）。
- **端云一致性**：前端 `test/cloud/tag/tag_repository_consistency_test.dart`（local_contract）锁定 Mock 行为
  与后端 `*View` → 前端 DTO `fromJson` 字段映射。
- **local-gamma 拓扑接入（静态验证通过）**：
  - 端口：`quwoquan_ops/environments/local_env_port_manifest.yaml` 新增 `tag-service` role（service plane,
    slot 270 → gamma `19270`）；`quwoquan_ops/cli/print_local_port_profile.py` 导出 `LOCAL_GAMMA_TAG_PORT`。
  - 容器：`quwoquan_service/docker-compose.gamma-local.yaml` 新增 `tag-service`（go run, `:18092`,
    healthz 探活），`gamma-proxy` 依赖其 healthy。
  - 配置：`start_local_gamma_mirror.sh` 的 `prepare_config_root` 落 `tag-service` default/gamma/release。
  - 路由：`prepare_caddyfile` 在 `gamma-api` 与 `:80` 两个 server 块加 `@api_tag path /tag*`
    → `tag-service:18092`。
  - podman fallback 分支同步新增 `tag-service` 启动与就绪等待。

## 2. 交集 `sharedTags` 真打闭环（需 Docker/Colima）

```bash
# 1) 起 local-gamma 镜像栈（含 tag-service）
bash quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh

# 2) 灌入路径制 taxonomy → tag_nodes（幂等可重跑）
cd quwoquan_service && \
  TAG_MONGO_PORT="$(python3 ../quwoquan_ops/cli/print_local_port_profile.py --profile gamma-local --format json | python3 -c 'import json,sys;print(json.load(sys.stdin)["ports"]["mongodb"])')" && \
  go run ./services/tag-service/cmd/import \
    --tags-dir ../quwoquan_data/control_plane/governance/taxonomy \
    --mongo-uri "mongodb://127.0.0.1:${TAG_MONGO_PORT}/?directConnection=true" \
    --db quwoquan_tag

# 3) 经网关真打验证（resolve / shared-tags / 5 个新增 API）
GW="http://127.0.0.1:$(python3 quwoquan_ops/cli/print_local_port_profile.py --profile gamma-local --format json | python3 -c 'import json,sys;print(json.load(sys.stdin)["ports"]["api-edge"])')"
curl -s "$GW/v1/tag/resolve?tagRef=Topic/旅行"
curl -s "$GW/v1/tag/shared-tags?objectAId=u1&objectAType=user&objectBId=u2&objectBType=user"
curl -s "$GW/v1/tag/search?q=旅"
```

端侧 `objectSharedReasonsProvider` → `tag-service /tag/shared-tags` 在 `APP_RUNTIME_ENV=gamma`
下经网关真打（不再读 Dart mock）。

## 3. 环境补齐步骤（Colima / 镜像源 / patrol）

- **Colima**：`colima start --cpu 4 --memory 8 --disk 60`，确认 `docker context show == colima`；
  start 脚本会自动起 127.0.0.1 SSH 隧道映射 gateway/product-ops/media-edge 端口。
- **镜像源**：Go `GOPROXY=https://goproxy.cn,direct`、`GOSUMDB=sum.golang.google.cn`；
  基础镜像走 `docker.m.daocloud.io/library`（`LOCAL_GAMMA_DOCKER_LIBRARY_PREFIX` 可覆盖）。
- **无 Docker 的 api_integration**：本机 MongoDB 时 `make -C quwoquan_service test-contract-local`，或
  `TEST_MONGO_URI=mongodb://localhost:27017 go test ./services/tag-service/... -count=1`。
- **patrol（user_acceptance）**：`dart pub global activate patrol_cli` + 启动 iOS/Android 模拟器，
  交集 user_acceptance case 经 `quwoquan_ops/cli/gamma/run_gamma_patrol_matrix_ci.py` 矩阵执行。

## 4. 当前能力边界

- **object_tag_index 对象打标 seed**：新增写能力与离线导入工具，gamma 自动灌库：
  - 写能力：`repository.ObjectTagIndexWriter.UpsertObjectTags` + `MongoObjectTagIndexStore.UpsertObjectTags`
    （按 `{objectId, objectType}` 唯一键幂等 upsert，派生倒排可重建）。
  - 导入工具：`services/tag-service/cmd/import-objects`，从 manifest（contract fixture 或数据工程扁平 manifest）
    幂等灌入 `object_tag_index`；默认源为 `contracts/metadata/tag/test_fixtures/scenarios/tag_scenarios.json`，
    与契约测试 / app mock 同源。
  - gamma 自动化：`start_local_gamma_mirror.sh` 在 host ready 后 `seed_tag_service_data()` 自动灌
    `tag_nodes`（control-plane taxonomy）+ `object_tag_index`（fixture）；导入失败必须阻断环境就绪。
  - 端到端真数据对齐以 gamma user seed 的真实 userId 和交集卡动态验证为准。
- **`feedback` 写路径**：`POST /tag/feedback` 保留 501。它是写操作（点击/忽略/修正），与
  tag-service「只读消费导入产物」定位冲突，落地需新增写存储或路由到 behavior/recommendation 域，
  待架构评审；前端 `MockTagRepository.feedback` 为 alpha 乐观占位，Remote 为休眠代码、无 UI 消费。
- **交集 user_acceptance patrol case**：对象页交集卡的端到端真打用例待补入 gamma patrol 矩阵。
