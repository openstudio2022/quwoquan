import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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

  /// 从 generated `ContentAppConfig` 解析首页频道覆盖列表。
  /// 按 order 升序排序。超过 [maximumChannelCount]、重复 id 或任一
  /// feed query 字段无效时整份覆盖无效，
  /// 由调用方回退端默认；禁止部分接受。
  static List<HomeChannelConfig>? fromAppConfig(ContentAppConfig config) {
    final raw = config.homeChannels;
    if (raw == null || raw.isEmpty || raw.length > maximumChannelCount) {
      return null;
    }

    final channels = <HomeChannelConfig>[];
    final channelIds = <String>{};
    for (final entry in raw) {
      final id = entry.id.trim();
      if (id.isEmpty) return null;
      if (!channelIds.add(id)) return null;
      final feedQuery = _parseFeedQuery(entry.feedQuery);
      if (feedQuery == null) return null;
      channels.add(
        HomeChannelConfig(
          id: id,
          labelKey: entry.labelKey ?? '',
          template: entry.template ?? '',
          layoutTemplate: entry.layoutTemplate ?? '',
          phoneColumns: entry.phoneColumns ?? 0,
          supportsFullSpanModules: entry.supportsFullSpanModules ?? false,
          intersectionModulePolicy: entry.intersectionModulePolicy ?? '',
          contentCardPolicy: entry.contentCardPolicy ?? '',
          feedQuery: feedQuery,
          moodCopyKey: entry.moodCopyKey ?? '',
          order: entry.order ?? 0,
        ),
      );
    }
    if (channels.isEmpty) return null;
    channels.sort((a, b) => a.order.compareTo(b.order));
    return channels;
  }

  static Map<String, String>? _parseFeedQuery(Map<String, Object?>? raw) {
    if (raw == null) return <String, String>{};
    final result = <String, String>{};
    for (final entry in raw.entries) {
      if (entry.value is! String) return null;
      result[entry.key] = entry.value! as String;
    }
    return result;
  }
}
