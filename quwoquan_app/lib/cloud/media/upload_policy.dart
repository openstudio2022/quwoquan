/// Client-side upload policy pre-validation (mirrors Go runtime/media policies).
/// Prevents invalid uploads before network round-trip.
class UploadPolicy {
  final int maxFileSize;
  final List<String> allowedTypes;
  final int maxDurationMs;
  final int maxWidth;
  final int maxHeight;

  const UploadPolicy({
    required this.maxFileSize,
    this.allowedTypes = const [],
    this.maxDurationMs = 0,
    this.maxWidth = 0,
    this.maxHeight = 0,
  });
}

enum MediaCategory {
  chatVoice,
  chatImage,
  chatVideo,
  chatFile,
  post,
  avatar,
  circle,
}

const _mb = 1024 * 1024;

const Map<MediaCategory, UploadPolicy> defaultPolicies = {
  MediaCategory.chatVoice: UploadPolicy(
    maxFileSize: 10 * _mb,
    allowedTypes: ['audio/aac', 'audio/mp4', 'audio/x-m4a', 'audio/mpeg'],
    maxDurationMs: 120000,
  ),
  MediaCategory.chatImage: UploadPolicy(
    maxFileSize: 20 * _mb,
    allowedTypes: [
      'image/jpeg',
      'image/png',
      'image/gif',
      'image/webp',
      'image/heic',
    ],
    maxWidth: 8192,
    maxHeight: 8192,
  ),
  MediaCategory.chatVideo: UploadPolicy(
    maxFileSize: 100 * _mb,
    allowedTypes: ['video/mp4', 'video/quicktime'],
    maxDurationMs: 600000,
  ),
  MediaCategory.chatFile: UploadPolicy(
    maxFileSize: 100 * _mb,
  ),
  MediaCategory.post: UploadPolicy(
    maxFileSize: 50 * _mb,
    allowedTypes: [
      'image/jpeg',
      'image/png',
      'image/gif',
      'image/webp',
      'image/heic',
      'video/mp4',
      'video/quicktime',
    ],
  ),
  MediaCategory.avatar: UploadPolicy(
    maxFileSize: 5 * _mb,
    allowedTypes: ['image/jpeg', 'image/png', 'image/webp'],
    maxWidth: 2048,
    maxHeight: 2048,
  ),
  MediaCategory.circle: UploadPolicy(
    maxFileSize: 50 * _mb,
    allowedTypes: [
      'image/jpeg',
      'image/png',
      'image/gif',
      'image/webp',
      'video/mp4',
    ],
  ),
};

/// Validates an upload against its category policy.
/// Returns null if valid, or an error message string.
String? validateUpload({
  required MediaCategory category,
  required int fileSize,
  required String contentType,
}) {
  final policy = defaultPolicies[category];
  if (policy == null) return '不支持的媒体类别';

  if (fileSize > policy.maxFileSize) {
    final maxMb = policy.maxFileSize ~/ _mb;
    return '文件大小超过限制（最大 $maxMb MB）';
  }

  if (policy.allowedTypes.isNotEmpty &&
      !policy.allowedTypes.contains(contentType.toLowerCase())) {
    return '不支持的文件类型';
  }

  return null;
}
