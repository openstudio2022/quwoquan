# 开发任务：config-provider-layering

## 统一门禁矩阵（简版）

| 阶段命令 | 必过项（最小集） | 不通过处理 |
|---|---|---|
| `/opsx-ff` | ① `tasks.md` 含目录/环境变量/版本映射任务；② `acceptance.yaml` 含对应验收项 | 阻断 FF，先补文档 |
| `/opsx-apply` | ① 每服务 `default/local/integration/prod` 目录齐；② 加载顺序与 APP_ENV 校验有测试；③ 门禁脚本可执行 | 阻断 apply，先补实现与测试 |
| `submit-with-gate` | ① strict gate 通过；② `CONFIG_VERSION` 文件存在且可映射；③ 配置-镜像兼容校验通过 | 禁止提交入库 |

## 当前交付任务（按 Wave 执行）

### Wave 1 — 规范与加载约束（先完成）

- [x] C1 定义配置目录规范（default/local/integration/prod）
- [x] C2 定义统一加载顺序（default -> env -> version -> env vars）
- [x] C3 定义 `APP_ENV` / `CONFIG_VERSION` / `IMAGE_VERSION` 运行时约束
- [x] C4 建立“高风险配置需滚动发布”边界清单

### Wave 2 — 门禁与测试（第二阶段）

- [ ] C5 落地自动化测试矩阵（本地/集成/生产配置加载）
- [x] C5.1 新建服务自动配置引导
  - 新增 `scripts/bootstrap_service_config_layout.sh`
  - S04 新建服务流程自动调用，生成 `default/local/integration/prod/config.yaml`
  - 同步创建 `releases/config/<service>/` 版本目录骨架
- [x] C6 落地门禁脚本（目录、环境变量、版本映射、兼容性）
  - `scripts/verify_service_config_layout.sh`
  - `scripts/verify_service_env_contract.sh`
  - `scripts/verify_config_release_version_mapping.sh`
  - `scripts/verify_config_image_compat.sh`
- [x] C7 将配置门禁接入 `make gate` / `make gate-full`
- [x] C7.1 增加部署拓扑门禁
  - `deploy/shared/process_domain_mapping.yaml` 声明三态映射
  - `scripts/verify_deployment_domain_mapping.sh` 校验 domain 唯一归属与 integration/prod 一致
  - 接入 `make verify` 与 `scripts/gate_repo.sh`
- [x] C7.2 recommendation-service（python）与 recommendation domain 命名和映射对齐
- [x] C7.3 gate-full 纳入 recommendation-service Python 测试必过

### Wave 3 — 进入 deliver 前置

- [x] C8 验证单服务（content-service）通过完整 gate
- [ ] C9 验证“灰度新老版本并行绑定”流程可执行（与 platform-ops 任务联调）
- [ ] C10 输出 deliver 输入清单（测试报告、门禁报告、回滚演练记录）

## 搁置任务（带规划）

- [ ] C11 运行时热更新能力：仅针对低风险配置，待配置中心稳定后接入
  - 搁置原因：当前优先完成发布化与灰度回滚闭环

## 未来演进任务

- [ ] C12 提炼为 `runtime/config` 通用库，其他服务复用
- [ ] C13 增加配置漂移检测（Git 期望值 vs 实际运行值）
