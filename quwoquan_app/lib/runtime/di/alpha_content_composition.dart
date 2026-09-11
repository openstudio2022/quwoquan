import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_bundled.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_bundled.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_bundled.dart';

/// 仅由 Alpha 隔离入口安装；在线入口不引用本文件或包内 adapter。
void installAlphaContentComposition() {
  final posts = BundledContentPostReader(loadBundle: OfflineContentBundle.load);
  final profiles = BundledProfileQuery(loadBundle: OfflineContentBundle.load);
  ContentProductionComposition.installReadComposition(
    config: const _AlphaContentConfigReader(),
    feed: BundledContentDiscoveryFeedQuery(
      loadBundle: OfflineContentBundle.load,
    ),
    detail: posts,
    authorPosts: posts,
  );
  UserProductionComposition.installReadComposition(
    profile: profiles,
    persona: profiles,
  );
}

final class _AlphaContentConfigReader implements AppContentConfigReader {
  const _AlphaContentConfigReader();

  @override
  Future<AppContentConfigSnapshot?> readActiveSnapshot() async => null;

  @override
  Future<AppContentConfigSnapshot> refresh() async =>
      (await OfflineContentBundle.load()).configuration;
}
