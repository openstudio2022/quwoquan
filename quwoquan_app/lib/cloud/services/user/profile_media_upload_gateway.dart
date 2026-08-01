import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum ProfileMediaTarget { avatar, cover }

class ProfileMediaUploadResult {
  const ProfileMediaUploadResult({required this.assetId});

  final String assetId;
}

abstract class ProfileMediaUploadGateway {
  Future<ProfileMediaUploadResult> uploadImage({
    required String localPath,
    required ProfileMediaTarget target,
  });
}

class ContentProfileMediaUploadGateway implements ProfileMediaUploadGateway {
  const ContentProfileMediaUploadGateway(
    this._coordinator,
    this._sourceReader,
    this._uploadStream,
  );

  final ContentMediaUploadCoordinator _coordinator;
  final ContentMediaSourceReader _sourceReader;
  final ContentMediaStreamObjectUpload _uploadStream;

  @override
  Future<ProfileMediaUploadResult> uploadImage({
    required String localPath,
    required ProfileMediaTarget target,
  }) async {
    final path = localPath.trim();
    if (path.isEmpty) {
      throw StateError('profile media path is empty');
    }
    final source = await _sourceReader.prepare(path);
    final uploaded = await _coordinator.uploadPreparedSource(
      source: source,
      mediaType: ContentMediaType.image,
      mimeType: _profileImageContentType(path),
      uploadStream: _uploadStream,
      accessPolicy: switch (target) {
        ProfileMediaTarget.avatar ||
        ProfileMediaTarget.cover => ContentMediaAccessPolicy.ownerOnly,
      },
    );
    return ProfileMediaUploadResult(assetId: uploaded.assetId);
  }
}

String _profileImageContentType(String path) {
  final lower = path.toLowerCase();
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.webp')) return 'image/webp';
  if (lower.endsWith('.heic') || lower.endsWith('.heif')) return 'image/heic';
  if (lower.endsWith('.gif')) return 'image/gif';
  return 'image/jpeg';
}
