import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_public_media_delivery.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_bundled.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_bundled.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_bundled.dart';

/// 仅由Alpha读取代际安装；不重跑rehearsal/auth/platform初始化。
void Function() installAlphaContentComposition({
  OfflineContentReadScope? scope,
  bool installMedia = false,
}) {
  final owned = scope ?? OfflineContentReadScope();
  final posts = BundledContentPostReader(
    loadBundle: owned.load,
    checkScope: owned.check,
  );
  final profiles = BundledProfileQuery(
    loadBundle: owned.load,
    checkScope: owned.check,
  );
  final clearContent = ContentProductionComposition.installReadComposition(
    config: _AlphaContentConfigReader(owned),
    feed: BundledContentDiscoveryFeedQuery(
      loadBundle: owned.load,
      checkScope: owned.check,
    ),
    detail: posts,
    authorPosts: posts,
  );
  final clearUser = UserProductionComposition.installReadComposition(
    profile: profiles,
    persona: profiles,
  );
  final clearMedia = installMedia
      ? installPublicMediaDelivery(
          BundledPublicMediaDelivery(
            loadBundle: owned.load,
            checkScope: owned.check,
          ),
        )
      : null;
  return () {
    owned.dispose();
    clearContent();
    clearUser();
    clearMedia?.call();
  };
}

final class _AlphaContentConfigReader implements AppContentConfigReader {
  const _AlphaContentConfigReader(this.scope);
  final OfflineContentReadScope scope;

  @override
  Future<AppContentConfigSnapshot?> readActiveSnapshot() async {
    scope.check();
    return null;
  }

  @override
  Future<AppContentConfigSnapshot> refresh() async =>
      (await scope.load()).configuration;
}
