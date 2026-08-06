import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_upload_queue.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// Chat 的 UI 类别只负责投影到 canonical MediaAsset 类型；大小、MIME 与错误语义
/// 均由 metadata 生成的 [ContentMediaUploadPolicy] 经 application validator 决定。
String? validateUpload({
  required MediaCategory category,
  required int fileSize,
  required String mimeType,
}) {
  try {
    validateContentMediaUploadPolicy(
      mediaType: contentMediaTypeForCategory(category),
      mimeType: mimeType,
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

MediaType contentMediaTypeForCategory(MediaCategory category) {
  return switch (category) {
    MediaCategory.chatVoice => MediaType.audio,
    MediaCategory.chatVideo => MediaType.video,
    MediaCategory.chatFile => MediaType.file,
    MediaCategory.chatImage => MediaType.image,
  };
}
