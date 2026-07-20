import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum MediaCategory { chatVoice, chatImage, chatVideo, chatFile }

/// Chat 的 UI 类别只负责投影到 canonical MediaAsset 类型；大小、MIME 与错误语义
/// 均由 metadata 生成的 [ContentMediaUploadPolicy] 经 application validator 决定。
String? validateUpload({
  required MediaCategory category,
  required int fileSize,
  required String contentType,
}) {
  try {
    validateContentMediaUploadPolicy(
      mediaType: contentMediaTypeForCategory(category),
      contentType: contentType,
      fileSize: fileSize,
    );
    return null;
  } on RuntimeFailureBase catch (failure) {
    final errorCode = ContentErrorCode.fromCode(failure.code);
    return ContentErrorMessages.zh[errorCode] ??
        ContentErrorMessages.zh[ContentErrorCode.unknown] ??
        failure.semanticReason;
  }
}

ContentMediaType contentMediaTypeForCategory(MediaCategory category) {
  return switch (category) {
    MediaCategory.chatVoice => ContentMediaType.audio,
    MediaCategory.chatVideo => ContentMediaType.video,
    MediaCategory.chatFile => ContentMediaType.file,
    MediaCategory.chatImage => ContentMediaType.image,
  };
}
