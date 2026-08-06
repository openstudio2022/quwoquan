import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Pure application seam for deriving a durable idempotency key from the
/// canonical storage payload. The hashing implementation belongs to adapters.
typedef ContentBehaviorClientEventIdDeriver =
    String Function(Map<String, dynamic> canonicalPayload);

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
  publishResult,
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
      case ReferralSource.publishResult:
        return 'publish_result';
    }
  }
}

/// 对象面 objectType → 来源 [ReferralSource] 的统一映射（N10）。
///
/// 用户 / 圈子 / 实体对象面（对象页交集 section、对象交集列表页）共享此映射，
/// 去除各展示位 `organicFeed` 一刀切硬编，按当前所在对象面精确归因（R23/R32）。
/// 用现有闭集最近邻：user→authorProfile、circle→circlePost、entity/entity_homepage/homepage→entityPage。
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
  BehaviorEvent({
    required this.contentId,
    required this.action,
    this.clientEventId,
    DateTime? occurredAt,
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
    this.policyDigest,
    this.recallPath,
    this.supplySource,
    this.commentLength,
    this.authorId,
    this.referralSource,
    this.engagementDepth,
    this.consumedRatio,
    this.totalUnits,
    this.effectivePlayMs,
    this.playbackSessionId,
    this.feedSessionId,
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
    this.taxonomyReleaseId,
    this.motionDirection,
    this.motionProfile,
    this.settleMs,
    this.reducedMotion,
    this.committed,
  }) : occurredAt = (occurredAt ?? DateTime.now()).toUtc() {
    final digest = policyDigest;
    if (digest != null && !isCanonicalSha256Digest(digest)) {
      throw const FormatException(
        'policyDigest must be a canonical SHA-256 digest',
      );
    }
  }

  final String contentId;
  final BehaviorEventType action;

  /// Client-generated idempotency key. Remote service de-duplicates by this id.
  final String? clientEventId;

  /// 客户端事实发生时间；离线补传必须保留该时间，禁止由服务端接收时间代替。
  final DateTime occurredAt;

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

  /// feed 下发的唯一推荐策略内容摘要（来源 DiscoveryFeedPage.policyDigest）；
  /// 闭合「召回 → 下发 → 曝光 → 互动」AB / replay 归因。
  final String? policyDigest;

  /// item 下发召回路径（如 tag_recall/collab_i2i/collab_u2i/repository_fallback）。
  final String? recallPath;

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

  /// 前台、可见、非 buffering/seek 的实际播放累计候选。
  final int? effectivePlayMs;

  /// 播放器会话标识；只用于有效播放幂等，不承担 App trace 会话语义。
  final String? playbackSessionId;

  /// 推荐 feed 拉取会话；Repository 在提交或持久化前注入到每个事件。
  final String? feedSessionId;

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

  /// 首启兴趣目录与 taxonomy snapshot 的唯一不可变发布身份。
  final String? taxonomyReleaseId;

  /// Client-side pageflip motion telemetry, used by video-book comfort audits.
  final String? motionDirection;
  final String? motionProfile;
  final int? settleMs;
  final bool? reducedMotion;
  final bool? committed;

  /// App 自有离线补传队列的持久化形状；不是 Cloud request encoder。
  ///
  /// 真正出站只能经 [toWire] 构造 generated request entity，禁止调用方把
  /// 此 Map 直接交给 transport。
  Map<String, dynamic> toStorageJson({
    required ContentBehaviorClientEventIdDeriver deriveClientEventId,
  }) {
    final payload = <String, dynamic>{
      'contentId': contentId,
      'action': action.wireName,
      if (state != null && state!.isNotEmpty) 'state': state,
      if (contentType != null && contentType!.isNotEmpty)
        'contentType': contentType,
      if (objectId != null && objectId!.isNotEmpty) 'objectId': objectId,
      if (objectKind != null && objectKind!.isNotEmpty)
        'objectKind': objectKind,
      if (displayName != null && displayName!.isNotEmpty)
        'displayName': displayName,
      if (sourceSurface != null && sourceSurface!.isNotEmpty)
        'sourceSurface': sourceSurface,
      if (tags != null && tags!.isNotEmpty) 'tagRefs': tags,
      if (duration != null && duration! > 0) 'duration': duration,
      if (feedRequestId != null) 'feedRequestId': feedRequestId,
      if (position != null) 'position': position,
      if (channelId != null && channelId!.isNotEmpty) 'channelId': channelId,
      if (policyDigest != null) 'policyDigest': policyDigest,
      if (recallPath != null && recallPath!.isNotEmpty)
        'recallPath': recallPath,
      if (supplySource != null && supplySource!.isNotEmpty)
        'supplySource': supplySource,
      if (commentLength != null) 'commentLength': commentLength,
      if (authorId != null && authorId!.isNotEmpty) 'authorId': authorId,
      if (referralSource != null) 'referralSource': referralSource!.value,
      if (engagementDepth != null) 'engagementDepth': engagementDepth,
      if (consumedRatio != null) 'consumedRatio': consumedRatio,
      if (totalUnits != null) 'totalUnits': totalUnits,
      if (effectivePlayMs != null) 'effectivePlayMs': effectivePlayMs,
      if (playbackSessionId != null && playbackSessionId!.isNotEmpty)
        'playbackSessionId': playbackSessionId,
      if (feedSessionId != null && feedSessionId!.isNotEmpty)
        'feedSessionId': feedSessionId,
      if (entityRefs != null && entityRefs!.isNotEmpty)
        'entityRefs': entityRefs,
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
      if (taxonomyReleaseId != null && taxonomyReleaseId!.isNotEmpty)
        'taxonomyReleaseId': taxonomyReleaseId,
      if (motionDirection != null && motionDirection!.isNotEmpty)
        'direction': motionDirection,
      if (motionProfile != null && motionProfile!.isNotEmpty)
        'motionProfile': motionProfile,
      if (settleMs != null) 'settleMs': settleMs,
      if (reducedMotion != null) 'reducedMotion': reducedMotion,
      if (committed != null) 'committed': committed,
      'occurredAt': occurredAt.toIso8601String(),
    };
    payload['clientEventId'] = _resolvedClientEventId(
      payload,
      deriveClientEventId,
    );
    return payload;
  }

  ContentBehaviorEventWire toWire({
    required ContentBehaviorClientEventIdDeriver deriveClientEventId,
  }) {
    final storagePayload = toStorageJson(
      deriveClientEventId: deriveClientEventId,
    );
    final rawContentType = contentType?.trim();
    final rawIntersectionDimension = intersectionDimension?.trim();
    return ContentBehaviorEventWire(
      clientEventId: storagePayload['clientEventId']! as String,
      occurredAt: occurredAt,
      contentId: contentId,
      action: action,
      state: state,
      contentType: rawContentType == null || rawContentType.isEmpty
          ? null
          : ContentType.fromWire(
              rawContentType,
              'ContentBehaviorEventWire.contentType',
            ),
      objectId: objectId,
      objectKind: objectKind,
      displayName: displayName,
      sourceSurface: sourceSurface,
      tagRefs: tags,
      duration: duration,
      feedRequestId: feedRequestId,
      position: position,
      channelId: channelId,
      policyDigest: policyDigest,
      recallPath: recallPath,
      supplySource: supplySource,
      commentLength: commentLength,
      authorId: authorId,
      referralSource: referralSource?.value,
      engagementDepth: engagementDepth,
      consumedRatio: consumedRatio,
      totalUnits: totalUnits,
      effectivePlayMs: effectivePlayMs,
      feedSessionId: feedSessionId,
      playbackSessionId: playbackSessionId,
      entityRefs: entityRefs,
      pageVisitId: pageVisitId,
      intersectionDimension:
          rawIntersectionDimension == null || rawIntersectionDimension.isEmpty
          ? null
          : IntersectionDimension.fromWire(
              rawIntersectionDimension,
              'ContentBehaviorEventWire.intersectionDimension',
            ),
      intersectionSourceRef: intersectionSourceRef,
      intersectionTagRefs: intersectionTagRefs,
      intersectionId: intersectionId,
      intersectionClass: intersectionClass,
      intersectionEvidenceId: intersectionEvidenceId,
      subjectId: subjectId,
      feedbackKind: feedbackKind,
      taxonomyReleaseId: taxonomyReleaseId,
      direction: motionDirection,
      motionProfile: motionProfile,
      settleMs: settleMs,
      reducedMotion: reducedMotion,
      committed: committed,
    );
  }

  String _resolvedClientEventId(
    Map<String, dynamic> storagePayload,
    ContentBehaviorClientEventIdDeriver deriveClientEventId,
  ) {
    final explicitID = clientEventId?.trim() ?? '';
    return explicitID.isNotEmpty
        ? explicitID
        : deriveClientEventId(
            Map<String, dynamic>.unmodifiable(storagePayload),
          );
  }

  BehaviorEvent withFeedSessionId(String value) {
    final normalized = value.trim();
    if (normalized.isEmpty || feedSessionId == normalized) {
      return this;
    }
    return BehaviorEvent(
      contentId: contentId,
      action: action,
      clientEventId: clientEventId,
      occurredAt: occurredAt,
      state: state,
      contentType: contentType,
      objectId: objectId,
      objectKind: objectKind,
      displayName: displayName,
      sourceSurface: sourceSurface,
      tags: tags,
      duration: duration,
      feedRequestId: feedRequestId,
      position: position,
      channelId: channelId,
      policyDigest: policyDigest,
      recallPath: recallPath,
      supplySource: supplySource,
      commentLength: commentLength,
      authorId: authorId,
      referralSource: referralSource,
      engagementDepth: engagementDepth,
      consumedRatio: consumedRatio,
      totalUnits: totalUnits,
      effectivePlayMs: effectivePlayMs,
      playbackSessionId: playbackSessionId,
      feedSessionId: normalized,
      entityRefs: entityRefs,
      pageVisitId: pageVisitId,
      intersectionDimension: intersectionDimension,
      intersectionSourceRef: intersectionSourceRef,
      intersectionTagRefs: intersectionTagRefs,
      intersectionId: intersectionId,
      intersectionClass: intersectionClass,
      intersectionEvidenceId: intersectionEvidenceId,
      subjectId: subjectId,
      feedbackKind: feedbackKind,
      taxonomyReleaseId: taxonomyReleaseId,
      motionDirection: motionDirection,
      motionProfile: motionProfile,
      settleMs: settleMs,
      reducedMotion: reducedMotion,
      committed: committed,
    );
  }
}

/// 推荐反馈唯一网络出口。Tracker 只依赖本端口，不直接依赖存储/HTTP Repository。
abstract interface class BehaviorReporter {
  Future<void> reportEvents({required List<BehaviorEvent> events});
}

/// 行为耐久队列端口；云端命令只能委托 generated writer。
abstract class BehaviorRepository implements BehaviorReporter {
  @override
  Future<void> reportEvents({required List<BehaviorEvent> events});

  /// 确认型首启行为：失败向调用方返回，绝不静默入尽力队列。
  Future<void> submitOnboardingInterest({
    required String clientEventId,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  });

  Future<void> clearPendingForLogout();

  Future<void> reportSingle({
    required String contentId,
    required BehaviorEventType action,
    List<String>? tags,
    double? duration,
    String? contentType,
    String? authorId,
    ReferralSource? referralSource,
    int? position,
    String? channelId,
    String? policyDigest,
    String? recallPath,
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
          policyDigest: policyDigest,
          recallPath: recallPath,
          supplySource: supplySource,
          feedRequestId: feedRequestId,
        ),
      ],
    );
  }
}
