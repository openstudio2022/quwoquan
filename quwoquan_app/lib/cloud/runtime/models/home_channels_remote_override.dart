import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';

/// 首页频道运营远程覆盖解析。
///
/// 真相源：端默认为 [ContentUIConfig.homeChannels]（发布自带 fallback）；
/// 运营经 `GET /config/app` 的 `content.home_channels` 远程整体覆盖（不发版即生效）。
/// 与 `ui_config.home_channels` 同 schema（id/label_key/template/layout_template/
/// phone_columns/intersection_module_policy/content_card_policy/feed_query/mood_copy_key/order）。
/// 解析失败 / 缺失 / 空列表 → 返回 null，调用方回退端默认。
class HomeChannelsRemoteOverride {
  const HomeChannelsRemoteOverride._();

  /// 与首页频道滚动锚点预算一致：默认 7 个频道，并保留 1 个运营扩展位。
  static const int maximumChannelCount = 8;

  /// 从 `/config/app` 响应根（wireRoot）解析首页频道覆盖列表。
  /// 仅接受 snake_case；按 order 升序排序。超过 [maximumChannelCount]
  /// 、重复 id 或任一条目/字段解析失败时整份覆盖无效，
  /// 由调用方回退端默认；禁止部分接受。
  static List<HomeChannelConfig>? fromAppConfigRoot(Map<String, Object?> root) {
    final rawContent = root['content'];
    if (rawContent != null && rawContent is! Map) return null;
    final content = _asStringObjectMap(rawContent);
    if (rawContent != null && content == null) return null;
    final raw = content?['home_channels'];
    if (raw is! List || raw.isEmpty || raw.length > maximumChannelCount) {
      return null;
    }

    final channels = <HomeChannelConfig>[];
    final channelIds = <String>{};
    for (final entry in raw) {
      final m = _asStringObjectMap(entry);
      if (m == null || !_hasCanonicalFieldTypes(m)) return null;
      final id = (m['id'] as String).trim();
      if (id.isEmpty) return null;
      if (!channelIds.add(id)) return null;
      final feedQuery = _parseFeedQuery(m['feed_query']);
      if (feedQuery == null) return null;
      channels.add(
        HomeChannelConfig(
          id: id,
          labelKey: (m['label_key'] as String?) ?? '',
          template: (m['template'] as String?) ?? '',
          layoutTemplate: (m['layout_template'] as String?) ?? '',
          phoneColumns: _asInt(m['phone_columns']),
          supportsFullSpanModules:
              (m['supports_full_span_modules'] as bool?) ?? false,
          intersectionModulePolicy:
              (m['intersection_module_policy'] as String?) ?? '',
          contentCardPolicy: (m['content_card_policy'] as String?) ?? '',
          feedQuery: feedQuery,
          moodCopyKey: (m['mood_copy_key'] as String?) ?? '',
          order: _asInt(m['order']),
        ),
      );
    }
    if (channels.isEmpty) return null;
    channels.sort((a, b) => a.order.compareTo(b.order));
    return channels;
  }

  static Map<String, Object?>? _asStringObjectMap(Object? raw) {
    if (raw is! Map) return null;
    final result = <String, Object?>{};
    for (final entry in raw.entries) {
      if (entry.key is! String) return null;
      result[entry.key as String] = entry.value;
    }
    return result;
  }

  static bool _hasCanonicalFieldTypes(Map<String, Object?> value) {
    if (value['id'] is! String) return false;
    for (final key in <String>[
      'label_key',
      'template',
      'layout_template',
      'intersection_module_policy',
      'content_card_policy',
      'mood_copy_key',
    ]) {
      final field = value[key];
      if (field != null && field is! String) return false;
    }
    for (final key in <String>['phone_columns', 'order']) {
      final field = value[key];
      if (field != null && field is! int) return false;
    }
    final fullSpan = value['supports_full_span_modules'];
    return fullSpan == null || fullSpan is bool;
  }

  static Map<String, String>? _parseFeedQuery(Object? raw) {
    if (raw == null) return <String, String>{};
    final map = _asStringObjectMap(raw);
    if (map == null) return null;
    final result = <String, String>{};
    for (final entry in map.entries) {
      if (entry.value is! String) return null;
      result[entry.key] = entry.value! as String;
    }
    return result;
  }

  static int _asInt(Object? value) {
    if (value is int) return value;
    return 0;
  }
}
