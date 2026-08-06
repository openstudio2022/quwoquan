import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_upload_service.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_media_upload_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class ContentProfileMediaUploadGateway implements ProfileMediaUploadGateway {
  const ContentProfileMediaUploadGateway(
    this._uploadService,
    this._sourceReader,
    this._uploadStream,
  );

  final ContentMediaUploadService _uploadService;
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
    final uploaded = await _uploadService.uploadPreparedSource(
      source: source,
      mediaType: MediaType.image,
      mimeType: _profileImageContentType(path),
      uploadStream: _uploadStream,
      accessPolicy: switch (target) {
        ProfileMediaTarget.avatar ||
        ProfileMediaTarget.cover => MediaAssetAccessPolicy.ownerOnly,
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
