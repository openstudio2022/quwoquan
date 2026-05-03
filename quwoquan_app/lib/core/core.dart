// Core types and utilities

/// Media item model
class MediaItem {
  final String type; // 'image' or 'video'
  final String url;
  final String? thumbnailUrl;
  final double? aspectRatio;

  const MediaItem({
    required this.type,
    required this.url,
    this.thumbnailUrl,
    this.aspectRatio,
  });
}

/// 图片上传发布状态机，覆盖编辑预览、上传、派生、发布、取消与失败。
enum ImageUploadPublishStage {
  localPreview,
  uploadInitializing,
  uploading,
  uploadCompleted,
  derivativeProcessing,
  derivativeReady,
  publishing,
  published,
  aborting,
  aborted,
  retrying,
  failed,
}

/// 原图查看/保存状态机，覆盖授权、过期、拒绝、限流与下载结果。
enum OriginalImageAccessStage {
  idle,
  requestingPermission,
  permissionGranted,
  permissionDenied,
  rateLimited,
  expired,
  downloading,
  ready,
  cancelled,
  failed,
}

class OriginalImageAccessProgress {
  const OriginalImageAccessProgress({
    required this.stage,
    this.totalBytes,
    this.receivedBytes,
    this.attempt = 1,
    this.errorCode,
    this.errorMessage,
  });

  final OriginalImageAccessStage stage;
  final int? totalBytes;
  final int? receivedBytes;
  final int attempt;
  final String? errorCode;
  final String? errorMessage;

  bool get isTerminal {
    switch (stage) {
      case OriginalImageAccessStage.ready:
      case OriginalImageAccessStage.cancelled:
      case OriginalImageAccessStage.failed:
      case OriginalImageAccessStage.permissionDenied:
      case OriginalImageAccessStage.rateLimited:
      case OriginalImageAccessStage.expired:
        return true;
      default:
        return false;
    }
  }

  double? get fraction {
    final total = totalBytes;
    final received = receivedBytes;
    if (total == null || received == null || total <= 0) return null;
    return (received / total).clamp(0, 1).toDouble();
  }
}
