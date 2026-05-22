import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';
import 'dart:math' as math;

import 'package:crypto/crypto.dart';
import 'package:flutter/widgets.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// Behavior action types aligned with behaviors.yaml.
///
/// Wire values use snake_case to match Go-side `supportedBehaviorActions`.
enum BehaviorAction {
  impression('impression'),
  click('click'),
  dwell('dwell'),
  like('like'),
  favorite('favorite'),
  share('share'),
  dislike('dislike'),
  report('report'),
  skip('skip'),
  comment('comment'),
  follow('follow'),
  authorView('author_view'),
  entityPageView('entity_page_view'),
  tagClick('tag_click'),
  playProgress('play_progress'),
  contentDepth('content_depth');

  const BehaviorAction(this.wireValue);

  final String wireValue;

  static final Map<String, BehaviorAction> _byWire = {
    for (final v in values) v.wireValue: v,
  };

  /// Parse from wire-format string; returns null for unknown values.
  static BehaviorAction? fromWireValue(String? wire) =>
      wire == null ? null : _byWire[wire];
}

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
    this.contentType,
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
    this.pageVisitId,
  });

  final String contentId;
  final BehaviorAction action;

  /// Content format: photo, video, article, moment (for ENER type stats)
  final String? contentType;

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

  /// Page visit ID for ops event correlation
  final String? pageVisitId;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contentId': contentId,
    'action': action.wireValue,
    if (contentType != null && contentType!.isNotEmpty)
      'contentType': contentType,
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
    if (pageVisitId != null && pageVisitId!.isNotEmpty)
      'pageVisitId': pageVisitId,
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
    required BehaviorAction action,
    List<String>? tags,
    double? duration,
    String? authorId,
    ReferralSource? referralSource,
    int? position,
    String? feedRequestId,
  }) {
    return reportEvents(
      events: <BehaviorEvent>[
        BehaviorEvent(
          contentId: contentId,
          action: action,
          tags: tags,
          duration: duration,
          authorId: authorId,
          referralSource: referralSource,
          position: position,
          feedRequestId: feedRequestId,
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

/// Non-retryable behavior report error (e.g. 400 schema mismatch).
class BehaviorReportException implements Exception {
  BehaviorReportException(
    this.statusCode,
    this.reason, {
    this.retryable = false,
  });
  final int statusCode;
  final String reason;
  final bool retryable;

  @override
  String toString() =>
      'BehaviorReportException($statusCode, $reason, retryable=$retryable)';
}

/// Remote 实现：对接云侧 POST /v1/content/behaviors。
const String kBehaviorPendingQueueBoxName = 'behavior_pending_queue';
const int _maxRetries = 3;
const int _gzipThreshold = 512;

class RemoteBehaviorRepository extends BehaviorRepository
    with WidgetsBindingObserver {
  RemoteBehaviorRepository({
    OpsEventRepository? eventRepository,
    String currentUserId = '',
    String experimentBucket = '',
    CloudHttpClient? httpClient,
    String? baseUrl,
    String Function()? feedSessionIdProvider,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
       _eventRepository = eventRepository,
       _currentUserId = currentUserId.trim(),
       _experimentBucket = experimentBucket.trim(),
       _feedSessionIdProvider = feedSessionIdProvider {
    _bindLifecycle();
  }

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final OpsEventRepository? _eventRepository;
  final String _currentUserId;
  final String _experimentBucket;
  final String Function()? _feedSessionIdProvider;

  /// Canonical session ID for cross-service tracing (matches HTTP header).
  String get _resolvedSessionId => CloudRequestHeaders.sessionId;

  /// Feed-scoped session for recommendation attribution (30min rolling UUID).
  String get _resolvedFeedSessionId => _feedSessionIdProvider?.call() ?? '';

  void _bindLifecycle() {
    try {
      WidgetsBinding.instance.addObserver(this);
    } catch (_) {}
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive) {
      unawaited(_flushPending());
    }
  }

  void dispose() {
    try {
      WidgetsBinding.instance.removeObserver(this);
    } catch (_) {}
  }

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
    final feedSid = _resolvedFeedSessionId;
    final body = <String, dynamic>{
      'sessionId': _resolvedSessionId,
      if (feedSid.isNotEmpty) 'feedSessionId': feedSid,
      'events': events.map((e) => e.toJson()).toList(),
    };

    try {
      await _flushPending();
      await _postWithRetry(uri, body);
    } on BehaviorReportException catch (e) {
      if (e.retryable) {
        await _enqueue(events);
      }
    } catch (e) {
      developer.log(
        'behavior reportEvents failed, enqueuing: $e',
        name: 'BehaviorRepository',
      );
      await _enqueue(events);
    }

    final eventRepository = _eventRepository;
    if (eventRepository != null) {
      final now = DateTime.now().toUtc();
      final traceCtx = AppTraceContextStore.instance;
      final batchTraceId =
          'behavior:${traceCtx.sessionId}:${now.microsecondsSinceEpoch}';
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
                  sessionId: _resolvedSessionId,
                  traceId: batchTraceId,
                  pageVisitId: event.pageVisitId ?? '',
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
    var consecutiveFailures = 0;
    for (final key in keys) {
      final raw = box.get(key);
      if (raw == null || raw.isEmpty) {
        await box.delete(key);
        continue;
      }
      try {
        final envelope = jsonDecode(raw);
        List<dynamic> eventsList;
        String sessionId;
        String feedSessionId = '';
        if (envelope is Map && envelope.containsKey('sessionId')) {
          sessionId = (envelope['sessionId'] ?? '').toString();
          feedSessionId = (envelope['feedSessionId'] ?? '').toString();
          eventsList = (envelope['events'] as List?) ?? <dynamic>[];
        } else {
          sessionId = _resolvedSessionId;
          eventsList = envelope as List;
        }
        final events = eventsList
            .whereType<Map>()
            .map((item) => _behaviorEventFromJson(item.cast<String, dynamic>()))
            .toList(growable: false);
        final uri = _uri(ContentApiMetadata.reportBehaviorsPath);
        final body = <String, dynamic>{
          'sessionId': sessionId,
          if (feedSessionId.isNotEmpty) 'feedSessionId': feedSessionId,
          'events': events
              .map((event) => event.toJson())
              .toList(growable: false),
        };
        await _postWithRetry(uri, body);
        await box.delete(key);
        consecutiveFailures = 0;
      } on BehaviorReportException catch (e) {
        if (!e.retryable) {
          await box.delete(key);
          continue;
        }
        consecutiveFailures++;
        if (consecutiveFailures >= 3) break;
      } catch (e) {
        developer.log(
          'behavior flushPending failed (consecutive=$consecutiveFailures): $e',
          name: 'BehaviorRepository',
        );
        consecutiveFailures++;
        if (consecutiveFailures >= 3) break;
      }
    }
  }

  Future<void> _enqueue(List<BehaviorEvent> events) async {
    final box = await _ensureQueueBox();
    final key = DateTime.now().microsecondsSinceEpoch.toString();
    final feedSid = _resolvedFeedSessionId;
    final envelope = <String, dynamic>{
      'sessionId': _resolvedSessionId,
      if (feedSid.isNotEmpty) 'feedSessionId': feedSid,
      'events': events.map((event) => event.toJson()).toList(growable: false),
    };
    await box.put(key, jsonEncode(envelope));
    const maxBacklog = 200;
    if (box.length > maxBacklog) {
      final keys =
          box.keys.map((value) => value.toString()).toList(growable: false)
            ..sort();
      final overflow = box.length - maxBacklog;
      for (var i = 0; i < overflow; i++) {
        await box.delete(keys[i]);
      }
    }
  }

  Future<void> _postWithRetry(Uri uri, Map<String, dynamic> body) async {
    final jsonStr = jsonEncode(body);
    final headers = Map<String, String>.from(
      CloudRequestHeaders.forPage(ContentRequestPageIds.reportBehaviors),
    );

    final useGzip = jsonStr.length > _gzipThreshold;
    List<int> payload;
    if (useGzip) {
      payload = gzip.encode(utf8.encode(jsonStr));
      headers['Content-Encoding'] = 'gzip';
      headers['Content-Type'] = 'application/json';
    } else {
      payload = utf8.encode(jsonStr);
      headers['Content-Type'] = 'application/json';
    }

    for (var attempt = 0; attempt <= _maxRetries; attempt++) {
      try {
        final response = await _httpClient.postBytes(
          uri,
          headers: headers,
          body: payload,
        );
        if (response.statusCode >= 200 && response.statusCode < 300) return;
        if (response.statusCode == 400) {
          throw BehaviorReportException(
            response.statusCode,
            'schema error',
            retryable: false,
          );
        }
        if (response.statusCode == 429) {
          throw BehaviorReportException(
            response.statusCode,
            'rate limited',
            retryable: true,
          );
        }
        if (response.statusCode >= 400 && response.statusCode < 500) {
          throw BehaviorReportException(
            response.statusCode,
            'client error',
            retryable: false,
          );
        }
        if (response.statusCode >= 500) {
          developer.log(
            'behavior POST 5xx: ${response.statusCode} (attempt ${attempt + 1}/${_maxRetries + 1})',
            name: 'BehaviorRepository',
          );
          throw BehaviorReportException(
            response.statusCode,
            'server error',
            retryable: true,
          );
        }
      } catch (e) {
        if (e is BehaviorReportException && !e.retryable) rethrow;
        if (attempt == _maxRetries) rethrow;
      }
      final delayMs = math.min(1000 * math.pow(2, attempt).toInt(), 8000);
      await Future<void>.delayed(Duration(milliseconds: delayMs));
    }
  }

  BehaviorEvent _behaviorEventFromJson(Map<String, dynamic> json) {
    final action =
        BehaviorAction.fromWireValue((json['action'] ?? '').toString()) ??
        BehaviorAction.impression;
    return BehaviorEvent(
      contentId: (json['contentId'] ?? '').toString(),
      action: action,
      contentType: json['contentType'] as String?,
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
      pageVisitId: json['pageVisitId'] as String?,
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
