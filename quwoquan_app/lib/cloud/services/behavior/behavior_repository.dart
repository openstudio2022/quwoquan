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
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
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
  share('share'),
  dislike('dislike'),
  hideAuthor('hide_author'),
  hideContentType('hide_content_type'),
  report('report'),
  skip('skip'),
  comment('comment'),
  follow('follow'),
  authorView('author_view'),
  entityPageView('entity_page_view'),
  tagClick('tag_click'),
  playProgress('play_progress'),
  contentDepth('content_depth'),
  // 交集转化三类行动（S6）：关注人 follow / 进圈子 join_circle / 加联系人 add_contact，
  // 独立 BehaviorAction 以拆分交集转化漏斗。
  joinCircle('join_circle'),
  addContact('add_contact'),
  // 小艺对话浮现兴趣回流（P3）：payload 仅带 tagRefs，不绑定具体 post。
  assistantInterest('assistant_interest'),
  // 交集条目负反馈（F 推荐与交集配对差异化）：不绑定具体 post，
  // subjectId 为交集主体对象、feedbackKind ∈ registry.feedbackKinds 闭集
  // （notInterested/dismiss/rejectGreeting/leaveCircle），驱动云侧 rec:ineg 冷却过滤。
  intersectionFeedback('intersection_feedback'),
  // 显式「想去 / 收藏 / 计划去」是 coWishlistedEntity 的真实意图源。
  // 统一走 BehaviorRepository，不新增并行 API。
  wishlistAdd('wishlist_add'),
  wishlistRemove('wishlist_remove');

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
  myIntersections,
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
      case ReferralSource.myIntersections:
        return 'my_intersections';
    }
  }
}

/// 对象面 objectType → 来源 [ReferralSource] 的统一映射（N10）。
///
/// 用户 / 圈子 / 实体对象面（对象页交集 section、对象交集列表页）共享此映射，
/// 去除各展示位 `organicFeed` 一刀切硬编，按当前所在对象面精确归因（R23/R32）。
/// 用现有闭集最近邻：user→authorProfile、circle→circlePost、entity/homepage→entityPage。
ReferralSource referralSourceForObjectType(String objectType) {
  switch (objectType.trim()) {
    case 'circle':
      return ReferralSource.circlePost;
    case 'entity':
    case 'homepage':
      return ReferralSource.entityPage;
    default:
      return ReferralSource.authorProfile;
  }
}

/// Behavior event for recommendation pipeline.
class BehaviorEvent {
  const BehaviorEvent({
    required this.contentId,
    required this.action,
    this.clientEventId,
    this.state,
    this.contentType,
    this.objectId,
    this.objectKind,
    this.displayName,
    this.sourceSurface,
    this.tags,
    this.duration,
    this.feedRequestId,
    this.position,
    this.channelId,
    this.rankingVersion,
    this.reasonVersion,
    this.recallPath,
    this.contentVertical,
    this.supplySource,
    this.commentLength,
    this.authorId,
    this.referralSource,
    this.engagementDepth,
    this.consumedRatio,
    this.totalUnits,
    this.entityRefs,
    this.pageVisitId,
    this.intersectionDimension,
    this.intersectionSourceRef,
    this.intersectionTagRefs,
    this.intersectionId,
    this.intersectionClass,
    this.intersectionEvidenceId,
    this.subjectId,
    this.feedbackKind,
    this.motionDirection,
    this.motionProfile,
    this.settleMs,
    this.reducedMotion,
    this.committed,
  });

  final String contentId;
  final BehaviorAction action;

  /// Client-generated idempotency key. Remote service de-duplicates by this id.
  final String? clientEventId;

  /// Closed feedback state: visible/impressed/click/dwell/interaction/negative.
  final String? state;

  /// Content format: photo, video, article, moment (for ENER type stats)
  final String? contentType;

  /// Wishlist target object id. Defaults to [contentId] for want-to-go events.
  final String? objectId;

  /// Wishlist target object kind, e.g. homepage/place/route.
  final String? objectKind;

  /// Human-readable target name for `entity_wishlist_events.displayName`.
  final String? displayName;

  /// Surface id / page id where the explicit intent was submitted.
  final String? sourceSurface;

  final List<String>? tags;

  /// Dwell time in seconds (for dwell/skip action)
  final double? duration;

  /// Feed request UUID for attribution
  final String? feedRequestId;

  /// Position in feed list (0-based)
  final int? position;

  /// 首页推荐频道 id（following/moment/work/photo/video/article 等）；非首页 feed 面为空字符串。
  final String? channelId;

  /// feed 下发精排管线版本（来源 DiscoveryFeedPage.rankingVersion）；
  /// 闭合「召回 → 下发(rankingVersion) → 曝光 → 互动」AB / replay 归因。
  final String? rankingVersion;

  /// feed 下发理由生成版本（envelope.reasonVersion），用于解释理由效果归因。
  final String? reasonVersion;

  /// item 下发召回路径（如 tag_recall/collab_i2i/collab_u2i/repository_fallback）。
  final String? recallPath;

  /// item 推荐垂类（如 general/travel_photography）。
  final String? contentVertical;

  /// item 供给来源（ugc/data_engineering/product_ops 等）。
  final String? supplySource;

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

  /// 交集行动归因（B3）：触发该行为的交集维度（identity/location/content/interest/relationship）。
  /// 替代旧 reasonType 闭集枚举，回流到推荐管线用于交集解释与归因。
  final String? intersectionDimension;

  /// 交集漏斗归因（§5.4 标准 kind）：触发该行为的最强事实交集 sourceRef。
  /// 与曝光/点击/展开同名字段一致，使「交集曝光 → 点击 → 转化」可按同一 kind 下钻。
  final String? intersectionSourceRef;

  /// 交集行动归因（B3）：触发该行为的路径制 tagRef 锚点（来自统一 taxonomy）。
  final List<String>? intersectionTagRefs;

  /// 交集漏斗归因（曝光/点击）：触发该行为的交集稳定标识（intersectionId）。
  final String? intersectionId;

  /// 交集漏斗归因：交集类别 fact|affinity（事实/概率），用于冷却窗口与分通道观测。
  final String? intersectionClass;

  /// 交集漏斗归因：被点击/曝光的事实证据项标识（intersectionEvidenceId）。
  final String? intersectionEvidenceId;

  /// 交集负反馈主体对象 id（intersection_feedback 专属，F 推荐差异化）：
  /// 与 reason.subjectId / actionTargetId 同源（person/circle/place…）。
  /// 不绑定具体 post，云侧据此写 rec:ineg 交集负反馈冷却集。
  final String? subjectId;

  /// 交集负反馈类型（intersection_feedback 专属）：属于 registry.feedbackKinds 闭集
  /// （intersectionFeedbackKinds，端云同源），驱动 subject 跨会话降权 / 冷却。
  final String? feedbackKind;

  /// Client-side pageflip motion telemetry, used by video-book comfort audits.
  final String? motionDirection;
  final String? motionProfile;
  final int? settleMs;
  final bool? reducedMotion;
  final bool? committed;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contentId': contentId,
    'action': action.wireValue,
    if (clientEventId != null && clientEventId!.isNotEmpty)
      'clientEventId': clientEventId,
    if (state != null && state!.isNotEmpty) 'state': state,
    if (contentType != null && contentType!.isNotEmpty)
      'contentType': contentType,
    if (objectId != null && objectId!.isNotEmpty) 'objectId': objectId,
    if (objectKind != null && objectKind!.isNotEmpty) 'objectKind': objectKind,
    if (displayName != null && displayName!.isNotEmpty)
      'displayName': displayName,
    if (sourceSurface != null && sourceSurface!.isNotEmpty)
      'sourceSurface': sourceSurface,
    if (tags != null && tags!.isNotEmpty) 'tagRefs': tags,
    if (duration != null && duration! > 0) 'duration': duration,
    if (feedRequestId != null) 'feedRequestId': feedRequestId,
    if (position != null) 'position': position,
    if (channelId != null && channelId!.isNotEmpty) 'channelId': channelId,
    if (rankingVersion != null && rankingVersion!.isNotEmpty)
      'rankingVersion': rankingVersion,
    if (reasonVersion != null && reasonVersion!.isNotEmpty)
      'reasonVersion': reasonVersion,
    if (recallPath != null && recallPath!.isNotEmpty) 'recallPath': recallPath,
    if (contentVertical != null && contentVertical!.isNotEmpty)
      'contentVertical': contentVertical,
    if (supplySource != null && supplySource!.isNotEmpty)
      'supplySource': supplySource,
    if (commentLength != null) 'commentLength': commentLength,
    if (authorId != null && authorId!.isNotEmpty) 'authorId': authorId,
    if (referralSource != null) 'referralSource': referralSource!.value,
    if (engagementDepth != null) 'engagementDepth': engagementDepth,
    if (consumedRatio != null) 'consumedRatio': consumedRatio,
    if (totalUnits != null) 'totalUnits': totalUnits,
    if (entityRefs != null && entityRefs!.isNotEmpty) 'entityRefs': entityRefs,
    if (pageVisitId != null && pageVisitId!.isNotEmpty)
      'pageVisitId': pageVisitId,
    if (intersectionDimension != null && intersectionDimension!.isNotEmpty)
      'intersectionDimension': intersectionDimension,
    if (intersectionSourceRef != null && intersectionSourceRef!.isNotEmpty)
      'intersectionSourceRef': intersectionSourceRef,
    if (intersectionTagRefs != null && intersectionTagRefs!.isNotEmpty)
      'intersectionTagRefs': intersectionTagRefs,
    if (intersectionId != null && intersectionId!.isNotEmpty)
      'intersectionId': intersectionId,
    if (intersectionClass != null && intersectionClass!.isNotEmpty)
      'intersectionClass': intersectionClass,
    if (intersectionEvidenceId != null && intersectionEvidenceId!.isNotEmpty)
      'intersectionEvidenceId': intersectionEvidenceId,
    if (subjectId != null && subjectId!.isNotEmpty) 'subjectId': subjectId,
    if (feedbackKind != null && feedbackKind!.isNotEmpty)
      'feedbackKind': feedbackKind,
    if (motionDirection != null && motionDirection!.isNotEmpty)
      'direction': motionDirection,
    if (motionProfile != null && motionProfile!.isNotEmpty)
      'motionProfile': motionProfile,
    if (settleMs != null) 'settleMs': settleMs,
    if (reducedMotion != null) 'reducedMotion': reducedMotion,
    if (committed != null) 'committed': committed,
  };
}

/// Behavior Repository (三层模式: Abstract → Mock → Remote)
///
/// 端侧行为上报，对接云侧 POST /v1/content/behaviors。
/// sessionId 通过 CloudRequestHeaders 自动注入。
abstract class BehaviorRepository {
  Future<void> reportEvents({required List<BehaviorEvent> events});

  Future<void> clearPendingForLogout();

  Future<void> reportSingle({
    required String contentId,
    required BehaviorAction action,
    List<String>? tags,
    double? duration,
    String? contentType,
    String? authorId,
    ReferralSource? referralSource,
    int? position,
    String? channelId,
    String? rankingVersion,
    String? reasonVersion,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
    String? feedRequestId,
  }) {
    return reportEvents(
      events: <BehaviorEvent>[
        BehaviorEvent(
          contentId: contentId,
          action: action,
          contentType: contentType,
          tags: tags,
          duration: duration,
          authorId: authorId,
          referralSource: referralSource,
          position: position,
          channelId: channelId,
          rankingVersion: rankingVersion,
          reasonVersion: reasonVersion,
          recallPath: recallPath,
          contentVertical: contentVertical,
          supplySource: supplySource,
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

  @override
  Future<void> clearPendingForLogout() async {
    recorded.clear();
  }
}

/// Remote 实现：对接云侧 POST /v1/content/behaviors。
const String kBehaviorPendingQueueBoxName = 'behavior_pending_queue';
const int _maxRetries = 3;
const int _gzipThreshold = 512;

class RemoteBehaviorRepository extends BehaviorRepository
    with WidgetsBindingObserver {
  RemoteBehaviorRepository({
    this._eventRepository,
    String currentUserId = '',
    String experimentBucket = '',
    required this._httpClient,
    String? baseUrl,
    this._feedSessionIdProvider,
    required this._queuePartition,
    ActorQueueStorage? queueStorage,
  }) : _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
       _currentUserId = currentUserId.trim(),
       _experimentBucket = experimentBucket.trim(),
       _queueStorage = queueStorage ?? ActorQueueStorage() {
    _bindLifecycle();
  }

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final OpsEventRepository? _eventRepository;
  final String _currentUserId;
  final String _experimentBucket;
  final String Function()? _feedSessionIdProvider;
  final ActorQueuePartition _queuePartition;
  final ActorQueueStorage _queueStorage;
  final Map<Timer, Completer<void>> _retryWaits = <Timer, Completer<void>>{};
  bool _disposed = false;

  // ── 双 sessionId 语义（军规 R23 收敛说明）──────────────────────────────
  // 端侧存在两个不同语义、不可混用的会话标识，上报 body 同时携带：
  //   1) sessionId      = CloudRequestHeaders.sessionId（AppTraceContextStore，App 生命周期级、
  //                       跨服务链路追踪，同时进 X-Client-Session-Id 头）。粒度：整个 App 会话。
  //   2) feedSessionId  = FeedSessionProvider 的 30 分钟滚动 UUID。粒度：推荐 feed 拉取会话，
  //                       用于把同一刷流会话内的曝光/点击/停留归因到同一次推荐请求。
  // 关系：feedSessionId ⊂ sessionId 时间轴（一个 App 会话可包含多个 feed 会话）。
  // 推荐 HotPath 归因用 feedSessionId + feedRequestId；跨服务 trace 用 sessionId。
  // 二者名称相近但不等价，禁止互相替代（既往割裂点见 R23）。

  /// Canonical session ID for cross-service tracing (matches HTTP header).
  String get _resolvedSessionId => CloudRequestHeaders.sessionId;

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
    for (final entry in _retryWaits.entries.toList(growable: false)) {
      entry.key.cancel();
      if (!entry.value.isCompleted) {
        entry.value.complete();
      }
    }
    _retryWaits.clear();
    try {
      WidgetsBinding.instance.removeObserver(this);
    } catch (_) {
      /* best-effort: 未成功注册时移除观察者会抛错，可安全忽略 */
    }
  }

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Future<Box<String>?> _ensureQueueBox() async {
    return _queueStorage.open(_queuePartition, kBehaviorPendingQueueBoxName);
  }

  @override
  Future<void> clearPendingForLogout() =>
      _queueStorage.purge(_queuePartition, kBehaviorPendingQueueBoxName);

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    if (_disposed || events.isEmpty) return;

    final uri = _uri(ContentApiMetadata.reportBehaviorsPath);
    final feedSid = _resolvedFeedSessionId;
    final body = <String, dynamic>{
      'sessionId': _resolvedSessionId,
      if (feedSid.isNotEmpty) 'feedSessionId': feedSid,
      'events': events.map((e) => e.toJson()).toList(),
    };

    try {
      await _flushPending();
      await _postBehaviorBatch(uri, body);
    } on CloudException catch (e) {
      if (_shouldEnqueueBehaviorFailure(e)) {
        await _enqueue(events);
      }
    } catch (_) {
      developer.log(
        'behavior reportEvents failed; enqueuing actor-scoped batch',
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
        final sessionId = (envelope['sessionId'] ?? '').toString();
        final feedSessionId = (envelope['feedSessionId'] ?? '').toString();
        final eventsList = (envelope['events'] as List?) ?? <dynamic>[];
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
        await _postBehaviorBatch(uri, body);
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
    final box = await _ensureQueueBox();
    if (box == null) {
      return;
    }
    final key = DateTime.now().microsecondsSinceEpoch.toString();
    final feedSid = _resolvedFeedSessionId;
    final envelope = <String, dynamic>{
      'actorPartitionKey': _queuePartition.key,
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

  Future<void> _postBehaviorBatch(Uri uri, Map<String, dynamic> body) async {
    if (_disposed) return;
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
      if (_disposed) return;
      try {
        final response = await _httpClient.postBytes(
          uri,
          headers: headers,
          body: payload,
        );
        if (response.statusCode >= 200 && response.statusCode < 300) return;
        if (response.statusCode >= 500) {
          developer.log(
            'behavior POST 5xx: ${response.statusCode} (attempt ${attempt + 1}/${_maxRetries + 1})',
            name: 'BehaviorRepository',
          );
        }
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: uri.path,
        );
      } catch (e) {
        if (_disposed) return;
        final cloudError = e is CloudException
            ? e
            : CloudErrorMapper.fromException(e, requestPath: uri.path);
        if (!_shouldRetryBehaviorFailure(cloudError) ||
            attempt == _maxRetries) {
          throw cloudError;
        }
      }
      final delayMs = math.min(1000 * math.pow(2, attempt).toInt(), 8000);
      await _waitBeforeRetry(Duration(milliseconds: delayMs));
    }
  }

  Future<void> _waitBeforeRetry(Duration duration) {
    if (_disposed) return Future<void>.value();
    final completer = Completer<void>();
    late final Timer timer;
    timer = Timer(duration, () {
      _retryWaits.remove(timer);
      if (!completer.isCompleted) {
        completer.complete();
      }
    });
    _retryWaits[timer] = completer;
    return completer.future;
  }

  bool _shouldRetryBehaviorFailure(CloudException error) {
    final statusCode = error.statusCode ?? 0;
    return statusCode == 0 || statusCode == 429 || statusCode >= 500;
  }

  bool _shouldEnqueueBehaviorFailure(CloudException error) {
    return _shouldRetryBehaviorFailure(error);
  }

  BehaviorEvent _behaviorEventFromJson(Map<String, dynamic> json) {
    final contentId = (json['contentId'] ?? '').toString().trim();
    final action = BehaviorAction.fromWireValue(
      (json['action'] ?? '').toString(),
    );
    if (contentId.isEmpty || action == null) {
      throw const FormatException('invalid behavior queue event');
    }
    return BehaviorEvent(
      contentId: contentId,
      action: action,
      clientEventId: json['clientEventId'] as String?,
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
      rankingVersion: json['rankingVersion'] as String?,
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
