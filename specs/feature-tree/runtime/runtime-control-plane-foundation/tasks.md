# 开发任务：runtime-control-plane-foundation

## 当前 /dev 交付任务

### 阶段 0：准入与基线确认
- [x] T0 确认控制面 metadata 唯一基线目录为 `quwoquan_service/contracts/metadata/_control_plane/`
  - 目标：明确 `_control_plane/` 为实现基线，`_shared/*.yaml` 仅作探索残留，不作为 codegen 真相源
  - 关联验收：A2、A7
  - Red 测试入口：`go test ./tools/verify_metadata/...`

### 阶段 1：metadata 校验器
- [x] T1 Red：为 `tools/verify_metadata` 增加控制面 metadata 失败用例
  - 目标：先让以下情况稳定失败
    - 缺失 `portal_shell.yaml` / `portal_menu.yaml`
    - `approval_mode` 非法
    - `route_path` / `menu_id` 重复
    - `dashboard` 与 `object_type` / `route` 关联缺失
  - 关联验收：A1、A2、A6、A7
  - Red 命令：`go test ./tools/verify_metadata/... -run ControlPlane`

- [x] T2 Green：扩展 `tools/verify_metadata`，正式校验 `_control_plane/` 目录
  - 目标：使校验器覆盖：
    - `portal_shell.yaml`
    - `portal_menu.yaml`
    - `platform/control_plane.yaml`
    - `platform/config_schema.yaml`
    - `product/control_plane.yaml`
    - `product/config_schema.yaml`
    - `product/workflow.yaml`
    - `product/audit_schema.yaml`
  - 关联验收：A1、A2、A5、A6、A7
  - 绿灯命令：`make verify-metadata`

### 阶段 2：ops portal codegen
- [x] T3 Red：为 `tools/codegen_ops_portal_metadata` 增加生成失败/输出断言测试
  - 目标：先验证当前 metadata 无法被可靠转换为门户生成物时，测试应失败
  - 重点断言：
    - 生成 `portalShell.generated.ts`
    - 生成 `portalMenu.generated.ts`
    - 生成 platform/product 的 control plane、workflow、audit、config TS 模块
    - 生成 `index.ts`
  - 关联验收：A1、A4、A7
  - Red 命令：`go test ./tools/codegen_ops_portal_metadata/...`

- [x] T4 Green：对齐 `codegen_ops_portal_metadata` 与 `_control_plane/` schema
  - 目标：支持门户风格语义、dashboard 编排、对象跳转、platform/product 控制面 generated TS 输出
  - 关联验收：A1、A4、A7、A8
  - 绿灯命令：`make codegen-ops-portal`

### 阶段 3：全量 codegen 基线
- [x] T5 运行 G1 基线并修复生成问题
  - 顺序：
    - `make verify-metadata`
    - `make codegen`
    - `make codegen-app`
  - 目标：控制面 metadata 进入正式 verify/codegen 流程
  - 关联验收：A2、A5、A7、A8

### 阶段 4：统一门户集成就绪
- [x] T6 建立门户生成物集成冒烟入口
  - 目标：确认 `apps/ops-portal/src/generated/control-plane/` 产物齐全，且能作为门户实现输入
  - 关联验收：A1、A4、A7、A8
  - T2/T3 证据：生成文件清单、route/menu/dashboard schema 可解析

- [x] T7 收口统一集成前置条件
  - 目标：确认本节点达到“具备全面集成条件”
  - 收口项：
    - metadata 真相源唯一
    - verify/codegen 流程打通
    - dashboard schema 可生成
    - 风格语义约束已进入门户生成边界
    - 部署映射与对象跳转规则已可验证
  - 关联验收：A1-A8

## 每个任务完成后的自动卡点
- `make build`
- `make test-contract`
- 若修改了 `quwoquan_app/lib/**/*.dart`，追加：`flutter test test/cloud/ test/components/ test/ui/`

## 当前实现策略
- 先打通 metadata → verify → codegen
- 再确认门户 generated artifacts 可作为统一门户输入
- 本会话不展开 `platform-ops` / `product-ops` 全量业务页面实现，而先完成“统一基础设施可被全面集成”的实现闭环

## 当前进度
- 已完成：T0-T7
- 根仓 `make gate-full`：PASS

## 与子会话的边界

### 交给 `platform-ops` 子会话
- `Platform Ops` 详细产品规格
- `sys.*` 配置模型
- 配置包、灰度、回滚、SLO、告警、CI/CD 门禁
- 面向 `platform-control-plane` 的详细对象与流程

### 交给 `product-ops` 子会话
- `Product Ops` 详细产品规格
- `ops.*` 业务策略模型
- 审核、处罚、申诉、恢复工作流
- 推荐运营与实验运营的详细对象与流程

### 回到本会话统一收口
- 门户壳层是否与两个子系统规格一致
- 元数据对象是否被双方共同消费
- codegen 目标是否统一
- 三类面是否在全部领域具备一致约束
- 部署组合与集成验收口径是否闭环
