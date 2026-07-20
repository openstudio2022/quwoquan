import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

String hubCircleStoryTypeLabel(PostBaseDto post) {
  if (post.isVideoLike || post.hasVideo) {
    return UITextConstants.discoveryTabVideo;
  }
  if (post.hasImages) {
    return UITextConstants.discoveryTabPhoto;
  }
  if (post.isArticleLike) {
    return UITextConstants.creationSubArticle;
  }
  if (post.type == 'micro') {
    return UITextConstants.creationSubMicro;
  }
  return UITextConstants.homeCirclesStoryTypeCreation;
}
