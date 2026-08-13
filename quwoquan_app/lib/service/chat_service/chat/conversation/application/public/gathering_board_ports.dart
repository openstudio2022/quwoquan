/// Chat 活动看板的只读 application boundary。
///
/// Board 只组合各 owner 提供的 typed slice；它不拥有 Gathering、Plan、
/// Announcement、Message、MediaAsset 或 Calendar 写状态。
abstract interface class GatheringBoardQuery {
  Future<GatheringBoardSnapshot> load(GatheringBoardQueryRequest request);
}

/// Chat owner 提供的 Board slice；请求身份只认 contextual conversation。
abstract interface class GatheringBoardChatReader {
  Future<GatheringBoardChatSlice> loadChat(String conversationId);
}

/// Circle owner 提供的 Board slice；请求身份来自 Chat access 中的 gatheringId。
abstract interface class GatheringBoardCircleReader {
  Future<GatheringBoardCircleSlice> loadCircle(String gatheringId);
}

class GatheringBoardQueryRequest {
  const GatheringBoardQueryRequest({required this.conversationId});

  final String conversationId;
}

enum GatheringBoardAccessMode { active, readOnly }

enum GatheringBoardCapabilityState { available, unavailable }

enum GatheringBoardCapabilityUnavailableReason {
  none,
  notConfigured,
  unsupported,
  permissionDenied,
  temporarilyUnavailable,
}

enum GatheringBoardAssetKind { image, video, file }

class GatheringBoardActivitySlice {
  const GatheringBoardActivitySlice({
    required this.gatheringId,
    required this.title,
    required this.scheduleLabel,
    required this.placeLabel,
  });

  final String gatheringId;
  final String title;
  final String scheduleLabel;
  final String placeLabel;
}

class GatheringBoardParticipationSlice {
  const GatheringBoardParticipationSlice({
    required this.activeCount,
    required this.maxParticipants,
    required this.remainingSeats,
    required this.summaryLabel,
  });

  final int activeCount;
  final int maxParticipants;
  final int remainingSeats;
  final String summaryLabel;
}

class GatheringBoardPlanItem {
  const GatheringBoardPlanItem({
    required this.planItemId,
    required this.title,
    required this.detail,
    required this.completed,
  });

  final String planItemId;
  final String title;
  final String detail;
  final bool completed;
}

class GatheringBoardCapabilitySummary {
  const GatheringBoardCapabilitySummary({
    required this.state,
    required this.summaryLabel,
    this.unavailableReason = GatheringBoardCapabilityUnavailableReason.none,
    this.unavailableLabel = '',
    this.itemCount = 0,
  });

  final GatheringBoardCapabilityState state;
  final GatheringBoardCapabilityUnavailableReason unavailableReason;
  final String summaryLabel;
  final String unavailableLabel;
  final int itemCount;

  bool get isAvailable => state == GatheringBoardCapabilityState.available;
}

class GatheringBoardPlanSlice {
  const GatheringBoardPlanSlice({
    required this.capability,
    this.items = const <GatheringBoardPlanItem>[],
  });

  final GatheringBoardCapabilitySummary capability;
  final List<GatheringBoardPlanItem> items;
}

class GatheringBoardChatAccessSummary {
  const GatheringBoardChatAccessSummary({
    required this.gatheringId,
    required this.conversationId,
    required this.accessMode,
    required this.viewerRole,
    required this.canPost,
    required this.statusLabel,
  });

  final String gatheringId;
  final String conversationId;
  final GatheringBoardAccessMode accessMode;
  final String viewerRole;
  final bool canPost;
  final String statusLabel;

  bool get isReadOnly => accessMode == GatheringBoardAccessMode.readOnly;
}

class GatheringBoardPinnedAnnouncement {
  const GatheringBoardPinnedAnnouncement({
    required this.content,
    required this.updatedBy,
    required this.updatedAt,
  });

  final String content;
  final String updatedBy;
  final DateTime updatedAt;
}

class GatheringBoardAssetIndexItem {
  const GatheringBoardAssetIndexItem({
    required this.messageId,
    required this.mediaAssetId,
    required this.kind,
    required this.displayLabel,
    required this.createdAt,
  });

  final String messageId;
  final String mediaAssetId;
  final GatheringBoardAssetKind kind;
  final String displayLabel;
  final DateTime createdAt;
}

class GatheringBoardChatSlice {
  const GatheringBoardChatSlice({
    required this.access,
    this.pinnedAnnouncement,
    this.assets = const <GatheringBoardAssetIndexItem>[],
  });

  final GatheringBoardChatAccessSummary access;
  final GatheringBoardPinnedAnnouncement? pinnedAnnouncement;
  final List<GatheringBoardAssetIndexItem> assets;
}

class GatheringBoardCircleSlice {
  const GatheringBoardCircleSlice({
    required this.activity,
    required this.participation,
    required this.plan,
    required this.mapCapability,
    required this.calendarCapability,
  });

  final GatheringBoardActivitySlice activity;
  final GatheringBoardParticipationSlice participation;
  final GatheringBoardPlanSlice plan;
  final GatheringBoardCapabilitySummary mapCapability;
  final GatheringBoardCapabilitySummary calendarCapability;
}

class GatheringBoardSnapshot {
  const GatheringBoardSnapshot({
    required this.activity,
    required this.participation,
    required this.plan,
    required this.chat,
    required this.mapCapability,
    required this.calendarCapability,
  });

  final GatheringBoardActivitySlice activity;
  final GatheringBoardParticipationSlice participation;
  final GatheringBoardPlanSlice plan;
  final GatheringBoardChatSlice chat;
  final GatheringBoardCapabilitySummary mapCapability;
  final GatheringBoardCapabilitySummary calendarCapability;
}

class GatheringBoardNavigationTarget {
  const GatheringBoardNavigationTarget({
    required this.gatheringId,
    required this.conversationId,
  });

  final String gatheringId;
  final String conversationId;
}

typedef GatheringBoardTargetNavigation =
    Future<void> Function(GatheringBoardNavigationTarget target);
typedef GatheringBoardAssetNavigation =
    Future<void> Function(GatheringBoardAssetIndexItem asset);

/// Board 自身不写 owner 状态；所有操作只交给 owner 页面或 typed command 入口。
class GatheringBoardNavigationCallbacks {
  const GatheringBoardNavigationCallbacks({
    this.openAnnouncement,
    this.openPlan,
    this.openMap,
    this.openCalendar,
    this.openMembers,
    this.openAsset,
    this.openRecapComposer,
  });

  final GatheringBoardTargetNavigation? openAnnouncement;
  final GatheringBoardTargetNavigation? openPlan;
  final GatheringBoardTargetNavigation? openMap;
  final GatheringBoardTargetNavigation? openCalendar;
  final GatheringBoardTargetNavigation? openMembers;
  final GatheringBoardAssetNavigation? openAsset;

  /// 发布回顾入口：携带 (gatheringId, gatheringTitle) 进入创作流，
  /// 内容经 gatheringRef 回流到行动详情共同经历聚合区。
  final void Function(String gatheringId, String gatheringTitle)?
  openRecapComposer;
}
