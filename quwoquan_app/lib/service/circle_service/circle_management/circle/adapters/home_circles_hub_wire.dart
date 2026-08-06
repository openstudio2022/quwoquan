import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

String hubCircleStoryTypeLabel(ContentPostViewData post) {
  if (post.isVideoLike || post.hasVideo) {
    return DiscoveryText.discoveryTabVideo;
  }
  if (post.hasImages) {
    return DiscoveryText.discoveryTabPhoto;
  }
  if (post.isArticleLike) {
    return ProfileText.creationSubArticle;
  }
  if (post.type == 'micro') {
    return ProfileText.creationSubMicro;
  }
  return DiscoveryText.homeCirclesStoryTypeCreation;
}
