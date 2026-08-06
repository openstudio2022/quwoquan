import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/home_feed_scroll_anchor.dart';

/// 首页频道切换共用同一个小型、有界锚点仓；生命周期由 ProviderContainer 托管。
final homeFeedScrollAnchorStoreProvider = Provider<HomeFeedScrollAnchorStore>(
  (ref) => HomeFeedScrollAnchorStore(),
);
