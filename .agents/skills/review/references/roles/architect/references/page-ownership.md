# 页面归属与 typed presentation

页面在本仓库的实际位置：

- `quwoquan_app/lib/service/<domain>_service/**/presentation/**/*_page.dart`（主体）
- `quwoquan_app/lib/runtime/shell/*.dart`（应用壳）
- `quwoquan_app/lib/design_system/**/*_page.dart`

仅占位 export 的 barrel 与 `chat_display_fallbacks.dart` 不算独立页面。

## 唯一真相源

| 关注点 | 真相源 |
|---|---|
| 行为规格 | `specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md` |
| 页面对象 | `quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml` |
| 路由与 Surface | `app_routes.yaml`、`ui_surfaces.yaml` |
| 页面集合 | 上述目录的**实时扫描结果** |

[MUST NOT] 新增页面矩阵、inventory、checklist 或任何人工页面索引。
页面集合由扫描得出，人工台账必然漂移。

## MUST

gate: `make verify-app-page-horizontal-quality`

1. `page_object_contract.yaml` 声明 owner、对象、Query Slice、typed presentation、
   鉴权、能力、观测与装配证据。
2. route/surface 只改 metadata 再 codegen；页面与 Router 不维护第二份字符串表。
3. 页面不得以 `Map` / `dynamic` 充当业务展示模型，不得回退 Mock
   （见 [production-wiring-and-test-doubles.md](production-wiring-and-test-doubles.md)）。
4. 响应式、语义 token、等待恢复、可访问性与 iOS 原生壳由实现和测试证明
   （视觉规则归 ux，见
   [../../ux/references/flutter-design-system.md](../../ux/references/flutter-design-system.md)）。
5. 未完成能力写入所属 L3 `spec.md` 的 `OPEN`，完成后转成现行 `REQ/GWT` 并删除 `OPEN`。

## 门禁构成

`make verify-app-page-horizontal-quality` 与 `bash quwoquan_ops/gate/gate_repo.sh --scope app`
背后是四个脚本：

- `verify_page_object_contract.py` — 磁盘页面必须由 metadata 唯一拥有，且对象、Query Slice、
  typed presentation、route、surface、权限与观测引用有效。
- `verify_page_abc_governance.py` — 扫描页面实现的结构、布局与弱类型回归。
- `verify_ios_native_surface_gate.py` — iOS 壳。
- `verify_dart_semantic.py` / `verify_ui_mock_isolation.py` — 语义 token 与 Mock 隔离。
