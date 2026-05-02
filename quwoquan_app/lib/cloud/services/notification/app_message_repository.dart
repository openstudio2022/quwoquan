import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/app_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/notification_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/notification_request_page_ids.g.dart';

abstract class AppMessageRepository {
  Future<List<AppMessageWire>> listAppMessages({
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<AppMessageWire> getAppMessage(String messageId);
  Future<AppMessageWire> ackAppMessage(String messageId);
  Future<AppMessageWire> readAppMessage(String messageId);
  Future<int> getUnreadCount();
}

class MockAppMessageRepository implements AppMessageRepository {
  final List<AppMessageWire> _messages = <AppMessageWire>[
    const AppMessageWire(
      messageId: 'msg_mock_assistant_1',
      userId: 'mock-user',
      messageType: 'assistant',
      source: 'assistant_turn',
      sourceId: 'atn_mock_1',
      destination: AppMessageDestinationWire(type: 'user', id: 'mock-user'),
      title: '小趣提醒',
      summary: '你关注的主题有新进展。',
      target: AppMessageTargetWire(
        targetType: 'assistant_turn',
        targetId: 'atn_mock_1',
      ),
      read: false,
      createdAt: '2026-04-29T02:00:00Z',
    ),
  ];

  @override
  Future<AppMessageWire> ackAppMessage(String messageId) async {
    return getAppMessage(messageId);
  }

  @override
  Future<AppMessageWire> getAppMessage(String messageId) async {
    return _messages.firstWhere((message) => message.messageId == messageId);
  }

  @override
  Future<int> getUnreadCount() async {
    return _messages.where((message) => !message.read).length;
  }

  @override
  Future<List<AppMessageWire>> listAppMessages({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _messages.take(limit).toList(growable: false);
  }

  @override
  Future<AppMessageWire> readAppMessage(String messageId) async {
    return getAppMessage(messageId);
  }
}

class RemoteAppMessageRepository implements AppMessageRepository {
  final http.Client _client;

  RemoteAppMessageRepository({http.Client? client})
    : _client = client ?? http.Client();

  @override
  Future<List<AppMessageWire>> listAppMessages({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      NotificationApiMetadata.listAppMessagesPath,
      <String, String>{'limit': '$limit'},
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        NotificationRequestPageIds.listAppMessages,
      ),
    );
    final data = _decode(resp);
    final items = (data['items'] as List? ?? const <Object?>[])
        .whereType<Map>()
        .map((item) => AppMessageWire.fromJson(item.cast<String, dynamic>()))
        .toList(growable: false);
    return items;
  }

  @override
  Future<AppMessageWire> getAppMessage(String messageId) async {
    final resp = await _client.get(
      _uri(NotificationApiMetadata.getAppMessagePath(messageId: messageId)),
      headers: CloudRequestHeaders.forPage(
        NotificationRequestPageIds.getAppMessage,
      ),
    );
    return AppMessageWire.fromJson(_decode(resp));
  }

  @override
  Future<AppMessageWire> ackAppMessage(String messageId) async {
    final resp = await _client.post(
      _uri(NotificationApiMetadata.ackAppMessagePath(messageId: messageId)),
      headers: CloudRequestHeaders.forPage(
        NotificationRequestPageIds.ackAppMessage,
      ),
    );
    return AppMessageWire.fromJson(_decode(resp));
  }

  @override
  Future<AppMessageWire> readAppMessage(String messageId) async {
    final resp = await _client.post(
      _uri(NotificationApiMetadata.readAppMessagePath(messageId: messageId)),
      headers: CloudRequestHeaders.forPage(
        NotificationRequestPageIds.readAppMessage,
      ),
    );
    return AppMessageWire.fromJson(_decode(resp));
  }

  @override
  Future<int> getUnreadCount() async {
    final resp = await _client.get(
      _uri(NotificationApiMetadata.getAppMessageUnreadCountPath),
      headers: CloudRequestHeaders.forPage(
        NotificationRequestPageIds.getAppMessageUnreadCount,
      ),
    );
    return (_decode(resp)['unreadCount'] as num?)?.toInt() ?? 0;
  }

  Uri _uri(String path, [Map<String, String>? query]) {
    final base = Uri.parse(CloudRuntimeConfig.gatewayBaseUrl);
    return base.replace(path: path, queryParameters: query);
  }

  Map<String, dynamic> _decode(http.Response resp) {
    final body = jsonDecode(resp.body);
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw StateError('AppMessage request failed: ${resp.statusCode}');
    }
    if (body is Map<String, dynamic>) return body;
    throw StateError('AppMessage response must be an object');
  }
}
