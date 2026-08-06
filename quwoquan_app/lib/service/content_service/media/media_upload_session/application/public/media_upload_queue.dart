enum MediaCategory { chatVoice, chatImage, chatVideo, chatFile }

enum UploadStatus { pending, uploading, completed, failed }

final class UploadTask {
  UploadTask({
    required this.localPath,
    required this.category,
    required this.mimeType,
    required this.fileSize,
    this.status = UploadStatus.pending,
    this.retryCount = 0,
  });

  final String localPath;
  final MediaCategory category;
  final String mimeType;
  final int fileSize;

  UploadStatus status;
  String? assetId;
  String? error;
  int retryCount;
}

/// Public upload queue used by application coordinators.
///
/// Connectivity, retry scheduling and object-storage adapters stay hidden in
/// the media-upload object and are installed only by runtime DI.
abstract interface class MediaUploadQueue {
  String? validate({
    required MediaCategory category,
    required int fileSize,
    required String mimeType,
  });

  Future<UploadTask> enqueue(UploadTask task);

  Stream<UploadTask> get onTaskUpdate;
}
