/// 同频/广场社交连接领域只读视图模型。
///
/// 原型阶段端侧先行：字段为强类型（守 R04，禁 Map 穿透）；后端契约（service.yaml /
/// fields.yaml / errors.yaml）、codegen DTO 与 fixture seed 化登记 backlog，
/// 待方向确认后由 circle / persona-follow-graph 域承接。
library;

/// 行动阶梯 CTA：`actionKey` 来自 `IntersectionActionKeys` 闭集，
/// `label` 由 `DiscoveryFeedText.intersectionActionLabel` 解析，端不二次造表。
class ConnectionActionHint {
  const ConnectionActionHint({
    required this.actionKey,
    required this.label,
    this.isPrimary = true,
  });

  final String actionKey;
  final String label;
  final bool isPrimary;
}

/// 人际连接：同趣（无位置）与附近（带模糊位置）共用。
///
/// - [distanceLabel] 非空 ⇒「附近」语义，展示模糊距离（如「约 1.2km」）。
/// - [mutualConsentRequired] ⇒ 破冰需双向同意，UI 提示「打招呼后对方同意才可继续」。
/// - [privacyBlurred] ⇒ 头像/昵称弱化展示（陌生人隐私默认收敛）。
class PeerConnection {
  const PeerConnection({
    required this.id,
    required this.displayName,
    required this.avatarUrl,
    required this.headline,
    required this.sharedSummary,
    required this.sharedInterests,
    required this.actions,
    this.distanceLabel,
    this.activeStatusLabel,
    this.mutualConsentRequired = false,
    this.privacyBlurred = false,
  });

  final String id;
  final String displayName;

  /// 头像 URL；mock 留空，UI 以首字母色块优雅降级（不硬编码外链）。
  final String avatarUrl;

  /// 一句话签名 / 个性标签。
  final String headline;

  /// 同趣结论句（如「你们都喜欢徒步与川西自驾」）。
  final String sharedSummary;
  final List<String> sharedInterests;
  final List<ConnectionActionHint> actions;

  /// 附近语义下的模糊距离标签；同趣（无位置）为 null。
  final String? distanceLabel;
  final String? activeStatusLabel;
  final bool mutualConsentRequired;
  final bool privacyBlurred;

  bool get isNearby => (distanceLabel ?? '').trim().isNotEmpty;
}

/// 结伴 / 行程机会：围绕一个目的地实体，沉淀「想去 / 正在去 / 结伴」的人。
class CompanionTrip {
  const CompanionTrip({
    required this.id,
    required this.destinationName,
    required this.destinationEntityId,
    required this.coverImageUrl,
    required this.dateRangeLabel,
    required this.companionSummary,
    required this.organizerName,
    required this.organizerAvatarUrl,
    required this.companionAvatars,
    required this.tags,
    required this.actions,
  });

  final String id;
  final String destinationName;

  /// 目的地实体 id（复用实体主页网络，徽章可点回实体页）。
  final String destinationEntityId;
  final String coverImageUrl;

  /// 行程时间窗（如「下周五–周日」）。
  final String dateRangeLabel;

  /// 同行结论句（如「5 人下周也去稻城亚丁」）。
  final String companionSummary;
  final String organizerName;
  final String organizerAvatarUrl;
  final List<String> companionAvatars;
  final List<String> tags;
  final List<ConnectionActionHint> actions;
}

/// 线下局：可报名的同城聚会 / 活动。
class OfflineMeetup {
  const OfflineMeetup({
    required this.id,
    required this.title,
    required this.placeName,
    required this.timeLabel,
    required this.attendanceLabel,
    required this.hostName,
    required this.hostAvatarUrl,
    required this.coverImageUrl,
    required this.tags,
    required this.actions,
  });

  final String id;
  final String title;
  final String placeName;
  final String timeLabel;

  /// 报名进度（如「3/8 人已报名」）。
  final String attendanceLabel;
  final String hostName;
  final String hostAvatarUrl;
  final String coverImageUrl;
  final List<String> tags;
  final List<ConnectionActionHint> actions;
}

/// 同频连接中心四 tab 计数摘要（红点 / 角标驱动）。
class ConnectionHubSummary {
  const ConnectionHubSummary({
    required this.affinityCount,
    required this.companionCount,
    required this.nearbyCount,
    required this.meetupCount,
  });

  final int affinityCount;
  final int companionCount;
  final int nearbyCount;
  final int meetupCount;

  int get total => affinityCount + companionCount + nearbyCount + meetupCount;
}
