import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

String hubCircleStoryTypeLabel(ContentPostViewData post) {
  return switch (post.type) {
    ContentType.video => DiscoveryText.discoveryTabVideo,
    ContentType.image => DiscoveryText.discoveryTabPhoto,
    ContentType.article => ProfileText.creationSubArticle,
  };
}
