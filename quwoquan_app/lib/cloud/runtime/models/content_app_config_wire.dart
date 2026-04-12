import 'package:quwoquan_app/cloud/runtime/generated/content/content_app_config_client_dto.g.dart';

/// `/v1/config/app` 响应根类型（wire 边界，非业务状态）。
typedef ContentAppConfigWireRoot = Map<String, Object?>;

/// `GetAppConfig`（`/v1/config/app`）响应的端侧具名封装。
///
/// 结构化消费请使用 [clientParsed]；[wireRoot] 仅在需遍历开放 JSON 子树时使用。
class ContentAppConfigWire {
  const ContentAppConfigWire._(this.wireRoot);

  /// 自 HTTP JSON 对象解码结果构造（浅拷贝为 [ContentAppConfigWireRoot]）。
  factory ContentAppConfigWire.fromResponseObject(Map<String, dynamic> decoded) {
    return ContentAppConfigWire._(
      Map<String, Object?>.from(
        decoded.map((k, v) => MapEntry(k.toString(), v as Object?)),
      ),
    );
  }

  /// 解码根（与 HTTP JSON 同形；值为 JSON 叶子或嵌套 Map/List）。
  final ContentAppConfigWireRoot wireRoot;

  /// 解析 `content` 下 feature_flags / gray_release / client_state_sync（metadata SSOT）。
  ContentAppConfigClientParsed get clientParsed =>
      ContentAppConfigClientParsed.fromRootMap(
        Map<String, dynamic>.from(wireRoot),
      );
}
