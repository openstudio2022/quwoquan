import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';

/// 首页频道运营远程覆盖解析。
///
/// 真相源：端默认为 [ContentUIConfig.homeChannels]（发布自带 fallback）；
/// 运营经 `GET /v1/config/app` 的 `content.home_channels` 远程整体覆盖（不发版即生效）。
/// 与 `ui_config.home_channels` 同 schema（id/label_key/template/layout_template/
/// phone_columns/intersection_module_policy/content_card_policy/feed_query/mood_copy_key/order）。
/// 解析失败 / 缺失 / 空列表 → 返回 null，调用方回退端默认。
class HomeChannelsRemoteOverride {
  const HomeChannelsRemoteOverride._();

  /// 从 `/v1/config/app` 响应根（wireRoot）解析首页频道覆盖列表。
  /// 仅接受 snake_case；按 order 升序排序。
  static List<HomeChannelConfig>? fromAppConfigRoot(Map<String, Object?> root) {
    final content = (root['content'] as Map?)?.cast<String, Object?>();
    final raw = content?['home_channels'] ?? root['home_channels'];
    if (raw is! List || raw.isEmpty) return null;

    final channels = <HomeChannelConfig>[];
    for (final entry in raw) {
      if (entry is! Map) continue;
      final m = entry.cast<String, Object?>();
      final id = m['id']?.toString().trim() ?? '';
      if (id.isEmpty) continue;
      channels.add(
        HomeChannelConfig(
          id: id,
          labelKey: (m['label_key'] ?? '').toString(),
          template: (m['template'] ?? '').toString(),
          layoutTemplate: (m['layout_template'] ?? '').toString(),
          phoneColumns: _asInt(m['phone_columns']),
          supportsFullSpanModules:
              _asBool(m['supports_full_span_modules']) ?? false,
          intersectionModulePolicy: (m['intersection_module_policy'] ?? '')
              .toString(),
          contentCardPolicy: (m['content_card_policy'] ?? '').toString(),
          feedQuery: _parseFeedQuery(m['feed_query']),
          moodCopyKey: (m['mood_copy_key'] ?? '').toString(),
          order: _asInt(m['order']),
        ),
      );
    }
    if (channels.isEmpty) return null;
    channels.sort((a, b) => a.order.compareTo(b.order));
    return channels;
  }

  static Map<String, String> _parseFeedQuery(Object? raw) {
    final result = <String, String>{};
    if (raw is Map) {
      raw.forEach((key, value) {
        if (value != null) result[key.toString()] = value.toString();
      });
    }
    return result;
  }

  static int _asInt(Object? value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value) ?? 0;
    return 0;
  }

  static bool? _asBool(Object? value) {
    if (value is bool) return value;
    if (value is String) {
      final normalized = value.trim().toLowerCase();
      if (normalized == 'true') return true;
      if (normalized == 'false') return false;
    }
    return null;
  }
}
