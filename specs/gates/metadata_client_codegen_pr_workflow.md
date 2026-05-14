# 契约元数据变更 → 客户端生成 → 手写代码（PR 必循流程）

单一真相源：`quwoquan_service/contracts/metadata/`。

## 1. 修改 API / 字段时的顺序

1. **先改 YAML**：`fields.yaml`、`service.yaml`、`errors.yaml`、各实体下 `projections/*.yaml` 等（按实际影响面）。
2. **云侧校验**：在仓库根或 `quwoquan_service` 下执行  
   `make -C quwoquan_service verify-metadata`  
   （等价：`cd quwoquan_service && go run ./tools/verify_metadata/ contracts/metadata`）。
3. **生成 Flutter 契约产物**：  
   `make codegen-app`  
   （等价：`cd quwoquan_service && go run ./tools/codegen_app_metadata --metadata-dir contracts/metadata --app-dir ../quwoquan_app --integration-service-dir ./services/integration-service`）。
4. **再改手写代码**：Repository 实现、UI、测试等；接口签名优先使用 codegen DTO 或在 metadata `client_projection` 中登记的读模型。

根目录 `bash quwoquan_service/scripts/contract/verify_contract_metadata.sh` 会在通过目录/YAML 结构校验后，**在已安装 Go 时自动执行** `verify-metadata`，与上述第 2 步对齐。

## 2. 不要做的事

- 在未跑通 `verify-metadata` 与 `codegen-app` 的情况下，仅在 Dart/Go 里改 path、operation 名或 DTO 字段并指望与云一致。
- 在 Repository 公共 API 上长期保留 `Map<String, dynamic>` 作为正式返回类型（过渡期除外，且须在 gap 清单中登记）。

## 3. 相关入口

- `quwoquan_service/Makefile`：`verify-metadata`、`codegen-app`
- `quwoquan_app/lib/cloud/runtime/generated/**`：codegen-app 输出（勿手改）
- `specs/gates/metadata_driven_ui_gap_inventory.yaml`：未纳入生成的缺口登记
