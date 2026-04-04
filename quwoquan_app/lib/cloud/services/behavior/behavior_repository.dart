import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// Behavior event for recommendation pipeline.
class BehaviorEvent {
  const BehaviorEvent({
    required this.contentId,
    required this.action,
    this.tags,
    this.duration,
  });

  final String contentId;

  /// One of: impression, click, dwell, like, favorite, share, dislike, report
  final String action;
  final List<String>? tags;

  /// Dwell time in seconds (for dwell action)
  final double? duration;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contentId': contentId,
    'action': action,
    if (tags != null && tags!.isNotEmpty) 'tags': tags,
    if (duration != null && duration! > 0) 'duration': duration,
  };
}

/// Behavior Repository (三层模式: Abstract → Mock → Remote)
///
/// 端侧行为上报，对接云侧 POST /v1/content/behaviors。
/// sessionId 通过 CloudRequestHeaders 自动注入。
abstract class BehaviorRepository {
  Future<void> reportEvents({required List<BehaviorEvent> events});

  Future<void> reportSingle({
    required String contentId,
    required String action,
    List<String>? tags,
    double? duration,
  }) {
    return reportEvents(
      events: <BehaviorEvent>[
        BehaviorEvent(
          contentId: contentId,
          action: action,
          tags: tags,
          duration: duration,
        ),
      ],
    );
  }
}

/// Mock 实现：本地记录，不发 HTTP 请求。
class MockBehaviorRepository extends BehaviorRepository {
  final List<BehaviorEvent> recorded = <BehaviorEvent>[];

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    recorded.addAll(events);
  }
}

/// Remote 实现：对接云侧 POST /v1/content/behaviors。
const String kBehaviorPendingQueueBoxName = 'behavior_pending_queue';

class RemoteBehaviorRepository extends BehaviorRepository {
  RemoteBehaviorRepository({
    OpsEventRepository? eventRepository,
    String currentUserId = '',
    String experimentBucket = '',
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
       _eventRepository = eventRepository,
       _currentUserId = currentUserId.trim(),
       _experimentBucket = experimentBucket.trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final OpsEventRepository? _eventRepository;
  final String _currentUserId;
  final String _experimentBucket;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Future<Box<String>> _ensureQueueBox() async {
    if (!Hive.isBoxOpen(kBehaviorPendingQueueBoxName)) {
      try {
        await Hive.initFlutter();
      } catch (_) {}
      return Hive.openBox<String>(kBehaviorPendingQueueBoxName);
    }
    return Hive.box<String>(kBehaviorPendingQueueBoxName);
  }

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    if (events.isEmpty) return;

    final uri = _uri(ContentApiMetadata.reportBehaviorsPath);
    final body = <String, dynamic>{
      'sessionId': CloudRequestHeaders.sessionId,
      'events': events.map((e) => e.toJson()).toList(),
    };

    try {
      await _flushPending();
      await _httpClient.postJson(
        uri,
        headers: CloudRequestHeaders.forPage(
          ContentRequestPageIds.reportBehaviors,
        ),
        body: body,
      );
    } catch (_) {
      await _enqueue(events);
    }

    final eventRepository = _eventRepository;
    if (eventRepository != null) {
      final now = DateTime.now().toUtc();
      unawaited(
        eventRepository.reportEventBatch(
          events: events
              .asMap()
              .entries
              .map((entry) {
                final event = entry.value;
                return OpsEventRecordInput(
                  eventId:
                      'behavior:${event.contentId}:${event.action}:${now.microsecondsSinceEpoch}:${entry.key}',
                  eventType: 'behavior',
                  eventName: 'content_${event.action}',
                  eventVersion: 'v1',
                  priority: 'P1',
                  producer: 'app.content_behavior',
                  source: 'content_behavior',
                  userIdHash: _hashUserId(_currentUserId),
                  sessionId: CloudRequestHeaders.sessionId,
                  targetType: 'content',
                  targetKey: event.contentId,
                  entityType: 'post',
                  entityId: event.contentId,
                  experimentBucket: _experimentBucket,
                  occurredAt: now.toIso8601String(),
                  clientSentAt: now.toIso8601String(),
                  payload: event.toJson(),
                  metrics: <String, dynamic>{
                    if (event.duration != null) 'duration': event.duration,
                  },
                );
              })
              .toList(growable: false),
        ),
      );
    }
  }

  String _hashUserId(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty || trimmed == 'anonymous') {
      return '';
    }
    return sha256.convert(utf8.encode(trimmed)).toString().substring(0, 16);
  }

  Future<void> _flushPending() async {
    final box = await _ensureQueueBox();
    final keys = box.keys.map((key) => key.toString()).toList(growable: false)
      ..sort();
    for (final key in keys) {
      final raw = box.get(key);
      if (raw == null || raw.isEmpty) {
        await box.delete(key);
        continue;
      }
      try {
        final events = (jsonDecode(raw) as List)
            .whereType<Map>()
            .map((item) => _behaviorEventFromJson(item.cast<String, dynamic>()))
            .toList(growable: false);
        await _httpClient.postJson(
          _uri(ContentApiMetadata.reportBehaviorsPath),
          headers: CloudRequestHeaders.forPage(
            ContentRequestPageIds.reportBehaviors,
          ),
          body: <String, dynamic>{
            'sessionId': CloudRequestHeaders.sessionId,
            'events': events.map((event) => event.toJson()).toList(growable: false),
          },
        );
        await box.delete(key);
      } catch (_) {
        break;
      }
    }
  }

  Future<void> _enqueue(List<BehaviorEvent> events) async {
    final box = await _ensureQueueBox();
    final key = DateTime.now().microsecondsSinceEpoch.toString();
    await box.put(
      key,
      jsonEncode(events.map((event) => event.toJson()).toList(growable: false)),
    );
    const maxBacklog = 200;
    if (box.length > maxBacklog) {
      final keys = box.keys.map((value) => value.toString()).toList(growable: false)
        ..sort();
      final overflow = box.length - maxBacklog;
      for (var i = 0; i < overflow; i++) {
        await box.delete(keys[i]);
      }
    }
  }

  BehaviorEvent _behaviorEventFromJson(Map<String, dynamic> json) {
    return BehaviorEvent(
      contentId: (json['contentId'] ?? '').toString(),
      action: (json['action'] ?? '').toString(),
      tags: (json['tags'] as List?)?.map((item) => item.toString()).toList(),
      duration: (json['duration'] as num?)?.toDouble(),
    );
  }
}
