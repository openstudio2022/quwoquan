import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

CircleDto circleDtoFromHubMockMap(Map<String, Object?> circle) {
  return CircleDto.fromMap({
    ...Map<String, dynamic>.from(circle),
    'description': circle['description'] ?? circle['desc'],
  });
}

/// 合并圈子名到 wire 行，供 [CircleHubFeedPostEntry.fromMap] 使用。
Map<String, dynamic> mergeCircleStoryRaw(
  Map<String, Object?> item,
  String circleName,
) {
  return <String, dynamic>{
    ...Map<String, dynamic>.from(item),
    if (!item.containsKey('circleName')) 'circleName': circleName,
  };
}

String hubCircleStoryTypeLabel(Map<String, dynamic> item) {
  final type = (item['type'] ?? item['contentType'] ?? '').toString();
  switch (type) {
    case 'photo':
    case 'image':
      return UITextConstants.discoveryTabPhoto;
    case 'video':
      return UITextConstants.discoveryTabVideo;
    case 'article':
      return UITextConstants.creationSubArticle;
    case 'moment':
    case 'micro':
      final hasVideo = (item['videoUrl']?.toString().trim() ?? '').isNotEmpty;
      final imageUrls = item['imageUrls'];
      final hasImages = imageUrls is List && imageUrls.isNotEmpty;
      if (hasVideo) return UITextConstants.discoveryTabVideo;
      if (hasImages) return UITextConstants.discoveryTabPhoto;
      return UITextConstants.creationSubMicro;
    default:
      return UITextConstants.homeCirclesStoryTypeCreation;
  }
}

PostBaseDto? hubTryParsePostBaseDto(Map<String, dynamic> item) {
  try {
    return postBaseDtoFromMap(item);
  } catch (_) {
    return null;
  }
}
