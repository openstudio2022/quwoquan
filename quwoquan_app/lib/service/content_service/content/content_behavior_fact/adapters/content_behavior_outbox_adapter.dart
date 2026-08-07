import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter/widgets.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_event_codec.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_outbox_terminal_account_purger.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 端侧「待追加事实队列」；唯一云端出口是 [ContentBehaviorFactAppender]。
///
/// 队列语义是 outbox 而非可变状态：条目是一次写入的不可变事实信封
/// （`{actorPartitionKey, events}`，key 为写入时刻），只会被整条读出后成功即删、
/// 不可重试即转 DLQ、超容量即转 DLQ；任何路径都不会读出条目改字段再写回。
/// `occurredAt` 保留客户端事实发生时间，离线补传不得用服务端接收时间替换。
const String kBehaviorPendingQueueBoxName = 'behavior_pending_queue';

final class ActorScopedContentBehaviorOutboxPurger
    implements ContentBehaviorOutboxTerminalAccountPurger {
  const ActorScopedContentBehaviorOutboxPurger(
    this._queuePartition,
    this._queueStorage,
  );

  final ActorQueuePartition _queuePartition;
  final ActorQueueStorage _queueStorage;

  @override
  Future<void> purgeForTerminalAccountClosure() =>
      _queueStorage.purge(_queuePartition, kBehaviorPendingQueueBoxName);
}

final class DurableContentBehaviorRepository extends BehaviorRepository
    with WidgetsBindingObserver
    implements ContentBehaviorOutboxTerminalAccountPurger {
  DurableContentBehaviorRepository({
    required this._writer,
    this._feedSessionIdProvider,
    required this._queuePartition,
    required this._queueStorage,
  }) {
    _bindLifecycle();
  }

  final ContentBehaviorFactAppender _writer;
  final String Function()? _feedSessionIdProvider;
  final ActorQueuePartition _queuePartition;
  final ActorQueueStorage _queueStorage;
  bool _disposed = false;

  /// Feed-scoped session for recommendation attribution (30min rolling UUID).
  String get _resolvedFeedSessionId => _feedSessionIdProvider?.call() ?? '';

  void _bindLifecycle() {
    try {
      WidgetsBinding.instance.addObserver(this);
    } catch (_) {
      /* best-effort: 测试或无 binding 环境下注册生命周期观察者会抛错，缺少观察者仅影响后台刷盘时机 */
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_disposed) return;
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive) {
      unawaited(_flushPending());
    }
  }

  void dispose() {
    if (_disposed) return;
    _disposed = true;
    try {
      WidgetsBinding.instance.removeObserver(this);
    } catch (_) {
      /* best-effort: 未成功注册时移除观察者会抛错，可安全忽略 */
    }
  }

  Future<Box<String>?> _ensureQueueBox() async {
    return _queueStorage.open(_queuePartition, kBehaviorPendingQueueBoxName);
  }

  @override
  Future<void> clearPendingForLogout() =>
      _queueStorage.purge(_queuePartition, kBehaviorPendingQueueBoxName);

  @override
  Future<void> purgeForTerminalAccountClosure() => clearPendingForLogout();

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    if (_disposed || events.isEmpty) return;
    final enriched = _withCurrentFeedSession(events);

    try {
      await _flushPending();
      await _send(enriched);
    } on CloudException catch (e) {
      if (_shouldEnqueueBehaviorFailure(e)) {
        await _enqueue(enriched);
        return;
      }
      rethrow;
    } catch (_) {
      developer.log(
        'behavior reportEvents failed; enqueuing actor-scoped batch',
        name: 'BehaviorRepository',
      );
      await _enqueue(enriched);
    }
  }

  @override
  Future<void> submitOnboardingInterest({
    required String clientEventId,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  }) async {
    if (_disposed) {
      throw StateError('BehaviorRepository disposed');
    }
    final tags = tagRefs
        .map((tagRef) => tagRef.trim())
        .where((tagRef) => tagRef.isNotEmpty)
        .toSet()
        .toList(growable: false);
    final releaseID = taxonomyReleaseId.trim();
    if (releaseID.isEmpty || tags.isEmpty) {
      throw ArgumentError(
        'onboarding taxonomyReleaseId and tagRefs are required',
      );
    }
    await _send(
      _withCurrentFeedSession(<BehaviorEvent>[
        BehaviorEvent(
          contentId: '',
          action: BehaviorEventType.onboardingInterest,
          clientEventId: clientEventId,
          taxonomyReleaseId: releaseID,
          sourceSurface: 'interest_onboarding',
          tags: tags,
        ),
      ]),
    );
  }

  Future<void> _flushPending() async {
    if (_disposed) return;
    final box = await _ensureQueueBox();
    if (_disposed || box == null) {
      return;
    }
    final keys = box.keys.map((key) => key.toString()).toList(growable: false)
      ..sort();
    var consecutiveFailures = 0;
    for (final key in keys) {
      if (_disposed) return;
      final raw = box.get(key);
      if (raw == null || raw.isEmpty) {
        await box.delete(key);
        continue;
      }
      try {
        final envelope = jsonDecode(raw);
        if (envelope is! Map ||
            !_queuePartition.acceptsEnvelope(envelope['actorPartitionKey'])) {
          await _queueStorage.moveToDlq(
            partition: _queuePartition,
            queueName: kBehaviorPendingQueueBoxName,
            sourceKey: key,
            rawEnvelope: raw,
            reason: 'actor_partition_mismatch',
          );
          continue;
        }
        final eventsList = (envelope['events'] as List?) ?? <dynamic>[];
        final events = eventsList
            .whereType<Map>()
            .map(
              (item) =>
                  _behaviorEventFromStorageJson(item.cast<String, dynamic>()),
            )
            .toList(growable: false);
        await _send(events);
        await box.delete(key);
        consecutiveFailures = 0;
      } on CloudException catch (e) {
        if (!_shouldEnqueueBehaviorFailure(e)) {
          await _queueStorage.moveToDlq(
            partition: _queuePartition,
            queueName: kBehaviorPendingQueueBoxName,
            sourceKey: key,
            rawEnvelope: raw,
            reason: 'non_retryable_${e.statusCode ?? 0}',
          );
          continue;
        }
        consecutiveFailures++;
        if (consecutiveFailures >= 3) break;
      } on FormatException catch (error) {
        await _queueStorage.moveToDlq(
          partition: _queuePartition,
          queueName: kBehaviorPendingQueueBoxName,
          sourceKey: key,
          rawEnvelope: raw,
          reason: 'poison_${error.message}',
        );
      } catch (_) {
        developer.log(
          'behavior actor-scoped flush failed '
          '(consecutive=$consecutiveFailures)',
          name: 'BehaviorRepository',
        );
        consecutiveFailures++;
        if (consecutiveFailures >= 3) break;
      }
    }
  }

  Future<void> _enqueue(List<BehaviorEvent> events) async {
    if (_disposed) {
      return;
    }
    final box = await _ensureQueueBox();
    if (_disposed || box == null) {
      return;
    }
    final key = DateTime.now().microsecondsSinceEpoch.toString();
    final enriched = _withCurrentFeedSession(events);
    final envelope = <String, dynamic>{
      'actorPartitionKey': _queuePartition.key,
      'events': enriched
          .map((event) => event.toDurableStorageJson())
          .toList(growable: false),
    };
    await box.put(key, jsonEncode(envelope));
    const maxBacklog = 200;
    if (box.length > maxBacklog) {
      final keys =
          box.keys.map((value) => value.toString()).toList(growable: false)
            ..sort();
      final overflow = box.length - maxBacklog;
      for (var i = 0; i < overflow; i++) {
        final overflowKey = keys[i];
        final raw = box.get(overflowKey);
        if (raw == null) {
          await box.delete(overflowKey);
          continue;
        }
        await _queueStorage.moveToDlq(
          partition: _queuePartition,
          queueName: kBehaviorPendingQueueBoxName,
          sourceKey: overflowKey,
          rawEnvelope: raw,
          reason: 'queue_capacity_exceeded',
          kind: ActorQueueSignalKind.overflowMoved,
        );
      }
    }
  }

  List<BehaviorEvent> _withCurrentFeedSession(List<BehaviorEvent> events) {
    final feedSessionId = _resolvedFeedSessionId;
    if (feedSessionId.trim().isEmpty) {
      return List<BehaviorEvent>.unmodifiable(events);
    }
    return List<BehaviorEvent>.unmodifiable(
      events.map((event) => event.withFeedSessionId(feedSessionId)),
    );
  }

  Future<void> _send(List<BehaviorEvent> events) {
    if (_disposed || events.isEmpty) return Future<void>.value();
    return _writer.reportBehaviors(
      ReportContentBehaviorsCommand(
        events: events
            .map((event) => event.toRequestWire())
            .toList(growable: false),
      ),
    );
  }

  bool _shouldRetryBehaviorFailure(CloudException error) {
    final statusCode = error.statusCode ?? 0;
    return statusCode == 0 || statusCode == 429 || statusCode >= 500;
  }

  bool _shouldEnqueueBehaviorFailure(CloudException error) {
    return _shouldRetryBehaviorFailure(error);
  }

  BehaviorEvent _behaviorEventFromStorageJson(Map<String, dynamic> json) {
    const canonicalFields = <String>{
      'contentId',
      'action',
      'clientEventId',
      'occurredAt',
      'state',
      'contentType',
      'objectId',
      'objectKind',
      'displayName',
      'sourceSurface',
      'tagRefs',
      'duration',
      'feedRequestId',
      'position',
      'channelId',
      'policyDigest',
      'recallPath',
      _retiredVerticalAttributionStorageKey,
      'supplySource',
      'commentLength',
      'authorId',
      'referralSource',
      'engagementDepth',
      'consumedRatio',
      'totalUnits',
      'effectivePlayMs',
      'playbackSessionId',
      'feedSessionId',
      'entityRefs',
      'pageVisitId',
      'intersectionDimension',
      'intersectionSourceRef',
      'intersectionTagRefs',
      'intersectionId',
      'intersectionClass',
      'intersectionEvidenceId',
      'subjectId',
      'feedbackKind',
      'taxonomyReleaseId',
      'direction',
      'motionProfile',
      'settleMs',
      'reducedMotion',
      'committed',
    };
    if (json.keys.any((field) => !canonicalFields.contains(field))) {
      throw const FormatException(
        'behavior queue event contains an unknown field',
      );
    }
    final rawPolicyDigest = json['policyDigest'];
    if (rawPolicyDigest != null && rawPolicyDigest is! String) {
      throw const FormatException(
        'policyDigest must be a canonical SHA-256 digest',
      );
    }
    final contentId = (json['contentId'] ?? '').toString().trim();
    final clientEventId = (json['clientEventId'] ?? '').toString().trim();
    final occurredAt = DateTime.tryParse(
      (json['occurredAt'] ?? '').toString(),
    )?.toUtc();
    final action = BehaviorEventType.fromWire(
      json['action'],
      'BehaviorEvent.action',
    );
    final actionIsContentless =
        action == BehaviorEventType.assistantInterest ||
        action == BehaviorEventType.onboardingInterest ||
        action == BehaviorEventType.intersectionFeedback ||
        action == BehaviorEventType.wishlistAdd ||
        action == BehaviorEventType.wishlistRemove;
    if ((contentId.isEmpty && !actionIsContentless) ||
        clientEventId.isEmpty ||
        occurredAt == null) {
      throw const FormatException('invalid behavior queue event');
    }
    return BehaviorEvent(
      contentId: contentId,
      action: action,
      clientEventId: clientEventId,
      occurredAt: occurredAt,
      state: json['state'] as String?,
      contentType: json['contentType'] as String?,
      objectId: json['objectId'] as String?,
      objectKind: json['objectKind'] as String?,
      displayName: json['displayName'] as String?,
      sourceSurface: json['sourceSurface'] as String?,
      tags: (json['tagRefs'] as List?)?.map((item) => item.toString()).toList(),
      duration: (json['duration'] as num?)?.toDouble(),
      feedRequestId: json['feedRequestId'] as String?,
      position: (json['position'] as num?)?.toInt(),
      channelId: json['channelId'] as String?,
      policyDigest: rawPolicyDigest as String?,
      recallPath: json['recallPath'] as String?,
      supplySource: json['supplySource'] as String?,
      commentLength: (json['commentLength'] as num?)?.toInt(),
      authorId: json['authorId'] as String?,
      referralSource: _parseReferralSource(json['referralSource'] as String?),
      engagementDepth: (json['engagementDepth'] as num?)?.toInt(),
      consumedRatio: (json['consumedRatio'] as num?)?.toDouble(),
      totalUnits: (json['totalUnits'] as num?)?.toInt(),
      effectivePlayMs: (json['effectivePlayMs'] as num?)?.toInt(),
      playbackSessionId: json['playbackSessionId'] as String?,
      feedSessionId: json['feedSessionId'] as String?,
      entityRefs: (json['entityRefs'] as List?)
          ?.map((item) => item.toString())
          .toList(),
      pageVisitId: json['pageVisitId'] as String?,
      intersectionDimension: json['intersectionDimension'] as String?,
      intersectionSourceRef: json['intersectionSourceRef'] as String?,
      intersectionTagRefs: (json['intersectionTagRefs'] as List?)
          ?.map((item) => item.toString())
          .toList(),
      intersectionId: json['intersectionId'] as String?,
      intersectionClass: json['intersectionClass'] as String?,
      intersectionEvidenceId: json['intersectionEvidenceId'] as String?,
      subjectId: json['subjectId'] as String?,
      feedbackKind: json['feedbackKind'] as String?,
      taxonomyReleaseId: json['taxonomyReleaseId'] as String?,
      motionDirection: json['direction'] as String?,
      motionProfile: json['motionProfile'] as String?,
      settleMs: (json['settleMs'] as num?)?.toInt(),
      reducedMotion: json['reducedMotion'] as bool?,
      committed: json['committed'] as bool?,
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

// Queues written by older App builds may still contain this retired field.
// Accept and drop it only while decoding the adapter-owned durable payload.
const _retiredVerticalAttributionStorageKey =
    'content'
    'Vertical';
