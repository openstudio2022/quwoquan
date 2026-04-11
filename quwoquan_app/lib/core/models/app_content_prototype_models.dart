/// 应用级原型数据强类型视图（与 [PrototypeMockData] 同源，不经由 `Map` 对外暴露）。

/// 圈子详情页原型「circleInfo」切片（CirclePageV2 对齐）。
class CirclePagePrototypeInfo {
  const CirclePagePrototypeInfo({
    required this.name,
    required this.id,
    required this.avatar,
    required this.cover,
    required this.desc,
    required this.stats,
    required this.hasNewMessages,
  });

  final String name;
  final String id;
  final String avatar;
  final String cover;
  final String desc;
  final CirclePrototypeStats stats;
  final bool hasNewMessages;
}

class CirclePrototypeStats {
  const CirclePrototypeStats({
    required this.members,
    required this.groups,
    required this.fans,
    required this.likes,
  });

  final String members;
  final String groups;
  final String fans;
  final String likes;
}

/// 圈子动态活动卡片（MOCK_ACTIVITIES）。
class CircleActivityPrototypeRow {
  const CircleActivityPrototypeRow({
    required this.id,
    required this.type,
    required this.title,
    required this.status,
    required this.circleId,
    required this.circleName,
    required this.participants,
    required this.image,
  });

  final String id;
  final String type;
  final String title;
  final String status;
  final String circleId;
  final String circleName;
  final int participants;
  final String image;
}

/// 帮读摘要维度内一条事实。
class HelperReadFactItemPrototype {
  const HelperReadFactItemPrototype({
    required this.raw,
  });

  /// 保留原型键（actorName、titleOrDescription、likes、workId 等），避免手写第二套字段树。
  final Map<String, Object?> raw;
}

/// 帮读摘要一个维度块。
class HelperReadDimensionPrototype {
  const HelperReadDimensionPrototype({
    required this.dimensionKey,
    required this.title,
    required this.items,
  });

  final String dimensionKey;
  final String title;
  final List<HelperReadFactItemPrototype> items;
}

/// 帮读摘要原型根。
class HelperReadSummaryPrototype {
  const HelperReadSummaryPrototype({
    required this.oneLiner,
    required this.dimensions,
  });

  final String oneLiner;
  final List<HelperReadDimensionPrototype> dimensions;
}

/// 助理 Tab 记忆行。
class AssistantPrototypeMemoryRow {
  const AssistantPrototypeMemoryRow({
    required this.memoryKey,
    required this.title,
    this.kind,
    this.dateLabel,
    this.iconEmoji,
  });

  final String memoryKey;
  final String title;
  final String? kind;
  final String? dateLabel;
  final String? iconEmoji;
}

/// 助理 Tab 任务行。
class AssistantPrototypeTaskRow {
  const AssistantPrototypeTaskRow({
    required this.taskKey,
    required this.title,
    this.time,
    required this.status,
    this.category,
  });

  final String taskKey;
  final String title;
  final String? time;
  final String status;
  final String? category;
}

/// 助理 Tab 技能目录行。
class AssistantPrototypeSkillRow {
  const AssistantPrototypeSkillRow({
    required this.skillId,
    required this.name,
    this.description,
    required this.active,
  });

  final String skillId;
  final String name;
  final String? description;
  final bool active;
}
