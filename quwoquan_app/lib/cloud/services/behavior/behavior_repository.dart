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

/// Referral source indicating how the user arrived at the content.
enum ReferralSource {
  organicFeed,
  friendShare,
  chatLink,
  circlePost,
  authorProfile,
  entityPage,
  search,
  pushNotification,
  deepLink,
}

extension ReferralSourceExt on ReferralSource {
  String get value {
    switch (this) {
      case ReferralSource.organicFeed:
        return 'organic_feed';
      case ReferralSource.friendShare:
        return 'friend_share';
      case ReferralSource.chatLink:
        return 'chat_link';
      case ReferralSource.circlePost:
        return 'circle_post';
      case ReferralSource.authorProfile:
        return 'author_profile';
      case ReferralSource.entityPage:
        return 'entity_page';
      case ReferralSource.search:
        return 'search';
      case ReferralSource.pushNotification:
        return 'push_notification';
      case ReferralSource.deepLink:
        return 'deep_link';
    }
  }
}

/// Behavior event for recommendation pipeline.
class BehaviorEvent {
  const BehaviorEvent({
    required this.contentId,
    required this.action,
    this.tags,
    this.duration,
    this.feedRequestId,
    this.position,
    this.commentLength,
    this.authorId,
    this.referralSource,
    this.engagementDepth,
    this.consumedRatio,
    this.totalUnits,
    this.entityRefs,
  });

  final String contentId;

  /// One of: impression, click, dwell, like, favorite, share, dislike, report,
  /// skip, comment, follow, author_view, tag_click, play_progress, content_depth
  final String action;
  final List<String>? tags;

  /// Dwell time in seconds (for dwell/skip action)
  final double? duration;

  /// Feed request UUID for attribution
  final String? feedRequestId;

  /// Position in feed list (0-based)
  final int? position;

  /// Comment text length (for comment action)
  final int? commentLength;

  /// Author of the content being interacted with
  final String? authorId;

  /// How the user arrived at this content
  final ReferralSource? referralSource;

  /// Normalized engagement depth level (0=L0 glance, 4=L4 full consumption)
  final int? engagementDepth;

  /// Raw consumed ratio (0.0-1.0+): pages/total, images/total, playPos/duration
  final double? consumedRatio;

  /// Total units of content (pages, images, duration in seconds)
  final int? totalUnits;

  /// Entity references from the content (for interest propagation)
  final List<String>? entityRefs;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contentId': contentId,
    'action': action,
    if (tags != null && tags!.isNotEmpty) 'tags': tags,
    if (duration != null && duration! > 0) 'duration': duration,
    if (feedRequestId != null) 'feedRequestId': feedRequestId,
    if (position != null) 'position': position,
    if (commentLength != null) 'commentLength': commentLength,
    if (authorId != null && authorId!.isNotEmpty) 'authorId': authorId,
    if (referralSource != null) 'referralSource': referralSource!.value,
    if (engagementDepth != null) 'engagementDepth': engagementDepth,
    if (consumedRatio != null) 'consumedRatio': consumedRatio,
    if (totalUnits != null) 'totalUnits': totalUnits,
    if (entityRefs != null && entityRefs!.isNotEmpty) 'entityRefs': entityRefs,
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
      feedRequestId: json['feedRequestId'] as String?,
      position: (json['position'] as num?)?.toInt(),
      commentLength: (json['commentLength'] as num?)?.toInt(),
      authorId: json['authorId'] as String?,
      referralSource: _parseReferralSource(json['referralSource'] as String?),
      engagementDepth: (json['engagementDepth'] as num?)?.toInt(),
      consumedRatio: (json['consumedRatio'] as num?)?.toDouble(),
      totalUnits: (json['totalUnits'] as num?)?.toInt(),
      entityRefs: (json['entityRefs'] as List?)
          ?.map((item) => item.toString())
          .toList(),
    );
  }

  static ReferralSource? _parseReferralSource(String? value) {
    if (value == null || value.isEmpty) return null;
    for (final source in ReferralSource.values) {
      if (source.value == value) return source;
    }
    return null;
  }
}
