import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// `AssistantUsePolicy` 在端侧的唯一解码入口。
///
/// canonical 取值只有 `inherit` / `exclude`（`_shared/types.yaml#enums`），缺省时
/// 由 Post 契约的 `DEFAULT_INHERIT` 约束落到 [AssistantUsePolicy.inherit]。任何
/// 其它取值都必须在解码阶段就被拒绝：`AssistantUsePolicy.fromWire` 抛出的
/// `FormatException` 经 App runtime mapper 映射为 `APP.CONTRACT.invalid_json`，
/// 不允许在这里做兼容映射或静默回退。
AssistantUsePolicy assistantUsePolicyFromWire(Object? raw, String path) {
  final text = raw?.toString().trim() ?? '';
  if (text.isEmpty) return AssistantUsePolicy.inherit;
  return AssistantUsePolicy.fromWire(text, path);
}
