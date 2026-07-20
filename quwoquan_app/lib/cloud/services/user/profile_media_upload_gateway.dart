import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/platform/content_addressed_upload_headers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
  ContentProfileMediaUploadGateway(this._media, {CloudHttpClient? httpClient})
    : _httpClient = httpClient ?? CloudHttpClient(),
      _ownsHttpClient = httpClient == null;

  final ContentMediaFacet _media;
  final CloudHttpClient _httpClient;
  final bool _ownsHttpClient;

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
    final file = File(path);
    final fileSize = await file.length();
    if (fileSize <= 0) {
      throw const FileSystemException('profile media source is empty');
    }
    final contentType = _profileImageContentType(path);
    final digest = await sha256.bind(file.openRead()).first;
    final init = await _media.initUpload(
      InitContentMediaUploadCommand(
        mediaType: ContentMediaType.image,
        contentType: contentType,
        fileSize: fileSize,
        expectedSha256: digest.toString(),
      ),
    );
    final sessionId = init.sessionId.trim();
    final uploadUrl = init.uploadUrl;
    if (sessionId.isEmpty || uploadUrl == null) {
      throw StateError('profile media upload session is incomplete');
    }
    try {
      final uploadHeaders = ContentAddressedUploadHeaders(
        contentType: contentType,
        expectedSha256: digest.toString(),
      );
      final request = http.StreamedRequest('PUT', uploadUrl)
        ..headers.addAll(uploadHeaders.toHttpHeaders())
        ..contentLength = fileSize;
      final responseFuture = _httpClient.send(request);
      await request.sink.addStream(file.openRead());
      await request.sink.close();
      final response = await responseFuture;
      await response.stream.drain<void>();
      if (response.statusCode != 200 && response.statusCode != 201) {
        throw const HttpException('profile media upload rejected');
      }
      final completed = await _media.completeUpload(
        CompleteContentMediaUploadCommand(sessionId: sessionId),
      );
      final assetId = (completed.assetId ?? '').trim();
      if (assetId.isEmpty) {
        throw StateError('profile media upload completed without assetId');
      }
      return ProfileMediaUploadResult(
        assetId: assetId,
        cdnUrl: completed.cdnUrl?.toString().trim() ?? '',
      );
    } catch (_) {
      await _media.abortUpload(
        AbortContentMediaUploadCommand(sessionId: sessionId),
      );
      rethrow;
    }
  }

  void dispose() {
    if (_ownsHttpClient) {
      _httpClient.close();
    }
  }
}

bool _isRemote(String value) {
  final lower = value.toLowerCase();
  return lower.startsWith('http://') ||
      lower.startsWith('https://') ||
      lower.startsWith('media/');
}

String _profileImageContentType(String path) {
  final lower = path.toLowerCase();
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.webp')) return 'image/webp';
  if (lower.endsWith('.heic') || lower.endsWith('.heif')) return 'image/heic';
  if (lower.endsWith('.gif')) return 'image/gif';
  return 'image/jpeg';
}
