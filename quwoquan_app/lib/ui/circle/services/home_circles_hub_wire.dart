import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

String hubCircleStoryTypeLabel(PostBaseDto post) {
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
