import 'package:quwoquan_app/cloud/runtime/generated/content/content_app_config_client_dto.g.dart';

/// `GetAppConfig`（`/v1/config/app`）响应的端侧具名类型。
///
/// 仍承载完整 JSON 对象；与自发 `Map<String, dynamic>` 区分，便于 Repository API 表达契约。
class ContentAppConfigWire {
  const ContentAppConfigWire._(this.raw);

  /// 自 HTTP JSON 对象解码结果构造（浅拷贝）。
  factory ContentAppConfigWire.fromResponseObject(Map<String, dynamic> decoded) {
    return ContentAppConfigWire._(Map<String, dynamic>.from(decoded));
  }

  final Map<String, dynamic> raw;

  /// 解析 `content` 下 feature_flags / gray_release / client_state_sync（metadata SSOT 同目录 YAML）。
  ContentAppConfigClientParsed get clientParsed =>
      ContentAppConfigClientParsed.fromRootMap(raw);
}
