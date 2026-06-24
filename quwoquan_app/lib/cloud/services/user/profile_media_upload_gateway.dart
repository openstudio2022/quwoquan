import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

enum ProfileMediaTarget { avatar, cover }

class ProfileMediaUploadResult {
  const ProfileMediaUploadResult({required this.assetId, required this.cdnUrl});

  final String assetId;
  final String cdnUrl;
}

abstract class ProfileMediaUploadGateway {
  Future<ProfileMediaUploadResult> uploadImage({
    required String localPath,
    required ProfileMediaTarget target,
  });
}

class ContentProfileMediaUploadGateway implements ProfileMediaUploadGateway {
  ContentProfileMediaUploadGateway(
    this._contentRepository, {
    http.Client? rawClient,
  }) : _rawClient = rawClient ?? http.Client();

  final ContentRepository _contentRepository;
  final http.Client _rawClient;

  @override
  Future<ProfileMediaUploadResult> uploadImage({
    required String localPath,
    required ProfileMediaTarget target,
  }) async {
    final path = localPath.trim();
    if (path.isEmpty) {
      throw StateError('profile media path is empty');
    }
    if (_isRemote(path)) {
      throw StateError('profile media must be uploaded from a local selection');
    }
    final init = await _contentRepository.initMediaUpload(
      mediaType: 'image',
      assetScope: switch (target) {
        ProfileMediaTarget.avatar => 'profile_avatar',
        ProfileMediaTarget.cover => 'profile_cover',
      },
    );
    final sessionId = init.sessionId.trim();
    final presignUrl = (init.presignUrl ?? init.uploadUrl ?? '').trim();
    if (sessionId.isEmpty || presignUrl.isEmpty) {
      throw StateError('profile media upload session is incomplete');
    }
    try {
      final file = File(path);
      final bytes = await file.readAsBytes();
      final response = await _rawClient.put(
        Uri.parse(presignUrl),
        headers: const <String, String>{'Content-Type': 'image/jpeg'},
        body: bytes,
      );
      if (response.statusCode != 200 && response.statusCode != 201) {
        throw HttpException(
          'profile media upload failed: ${response.statusCode}',
        );
      }
      final completed = await _contentRepository.completeMediaUpload(
        sessionId: sessionId,
      );
      final assetId = (completed.assetId ?? init.mediaId ?? '').trim();
      if (assetId.isEmpty) {
        throw StateError('profile media upload completed without assetId');
      }
      return ProfileMediaUploadResult(
        assetId: assetId,
        cdnUrl: (completed.cdnUrl ?? '').trim(),
      );
    } catch (_) {
      await _contentRepository.abortMediaUpload(sessionId: sessionId);
      rethrow;
    }
  }
}

class MockProfileMediaUploadGateway implements ProfileMediaUploadGateway {
  const MockProfileMediaUploadGateway();

  @override
  Future<ProfileMediaUploadResult> uploadImage({
    required String localPath,
    required ProfileMediaTarget target,
  }) async {
    final suffix = DateTime.now().millisecondsSinceEpoch;
    final scope = switch (target) {
      ProfileMediaTarget.avatar => 'profile_avatar',
      ProfileMediaTarget.cover => 'profile_cover',
    };
    final assetId = 'mock_${scope}_$suffix';
    return ProfileMediaUploadResult(
      assetId: assetId,
      cdnUrl: 'media/profile/$scope/$assetId',
    );
  }
}

bool _isRemote(String value) {
  final lower = value.toLowerCase();
  return lower.startsWith('http://') ||
      lower.startsWith('https://') ||
      lower.startsWith('media/');
}
