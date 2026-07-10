import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/media/upload_policy.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

void main() {
  group('MediaUploadManager chat upload', () {
    test('init / upload / complete 都走 chat 契约', () async {
      final tempDir = Directory.systemTemp.createTempSync('qwq-chat-upload-');
      addTearDown(() => tempDir.deleteSync(recursive: true));
      final filePath = '${tempDir.path}/clip.mp4';
      File(filePath).writeAsBytesSync(<int>[1, 2, 3, 4]);

      http.BaseRequest? initRequest;
      http.BaseRequest? completeRequest;
      http.BaseRequest? uploadRequest;
      final apiClient = MockClient((request) async {
        if (request.url.path == ChatApiMetadata.initChatUploadPath) {
          initRequest = request;
          final body =
              jsonDecode(utf8.decode(request.bodyBytes))
                  as Map<String, dynamic>;
          expect(body['mediaType'], equals('video'));
          expect(body['assetScope'], equals('draft'));
          expect(body['sourceKind'], equals('chat_attachment'));
          expect(body['fileName'], equals('clip.mp4'));
          expect(
            request.headers['X-Client-Page-Id'],
            equals(ChatRequestPageIds.initChatUpload),
          );
          return http.Response(
            jsonEncode(<String, dynamic>{
              'sessionId': 'chat_session_1',
              'mediaId': 'chat_media_1',
              'uploadUrl': 'https://upload.example.com/chat_session_1',
              'presignUrl': 'https://upload.example.com/chat_session_1',
              'objectKey': 'uploads/chat/chat_session_1/clip.mp4',
              'temporaryObjectKey': 'uploads/chat/chat_session_1/clip.mp4',
            }),
            200,
            headers: const <String, String>{'content-type': 'application/json'},
          );
        }
        if (request.url.path == ChatApiMetadata.completeChatUploadPath) {
          completeRequest = request;
          final body =
              jsonDecode(utf8.decode(request.bodyBytes))
                  as Map<String, dynamic>;
          expect(body['sessionId'], equals('chat_session_1'));
          expect(body['mediaType'], equals('video'));
          expect(body['assetScope'], equals('draft'));
          expect(body['sourceKind'], equals('chat_attachment'));
          expect(
            request.headers['X-Client-Page-Id'],
            equals(ChatRequestPageIds.completeChatUpload),
          );
          return http.Response(
            jsonEncode(<String, dynamic>{
              'sessionId': 'chat_session_1',
              'status': 'ready',
              'cdnUrl':
                  'https://cdn.example.com/uploads/chat/chat_session_1/clip.mp4',
              'assetId': 'chat_media_1',
            }),
            200,
            headers: const <String, String>{'content-type': 'application/json'},
          );
        }
        return http.Response('not found', 404);
      });

      final uploadClient = MockClient((request) async {
        uploadRequest = request;
        expect(request.method, equals('PUT'));
        expect(request.url.path, equals('/chat_session_1'));
        return http.Response('', 200);
      });

      final manager = MediaUploadManager(
        httpClient: CloudHttpClient(client: apiClient),
        rawClient: uploadClient,
        maxConcurrent: 1,
      );
      final task = UploadTask(
        localPath: filePath,
        category: MediaCategory.chatVideo,
        contentType: 'video/mp4',
        fileSize: 4,
        ownerId: 'user_1',
        fileName: 'clip.mp4',
      );
      final completed = Completer<UploadTask>();
      final sub = manager.onTaskUpdate.listen((update) {
        if (update.localPath == filePath &&
            update.status == UploadStatus.completed &&
            !completed.isCompleted) {
          completed.complete(update);
        }
      });

      await manager.enqueue(task);
      final result = await completed.future.timeout(const Duration(seconds: 5));
      await sub.cancel();

      expect(initRequest, isNotNull);
      expect(completeRequest, isNotNull);
      expect(uploadRequest, isNotNull);
      expect(result.sessionId, equals('chat_session_1'));
      expect(result.assetId, equals('chat_media_1'));
      expect(
        result.cdnUrl,
        equals('https://cdn.example.com/uploads/chat/chat_session_1/clip.mp4'),
      );
    });
  });
}
