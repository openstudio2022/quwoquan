/// 圈子统计列表页（成员 / 群组 / 点赞动态）的跨对象公开行视图模型。
///
/// 关注状态不进行视图模型持有：真相源是 `userRelationshipStateProvider`，
/// 由页面按 personaId 实时读取。
class CircleStatsMemberRowViewData {
  const CircleStatsMemberRowViewData({
    required this.id,
    required this.name,
    required this.avatarUrl,
    required this.worksCountLabel,
    required this.fansCountLabel,
    required this.likesCountLabel,
  });

  final String id;
  final String name;
  final String avatarUrl;
  final String worksCountLabel;
  final String fansCountLabel;
  final String likesCountLabel;
}

class CircleStatsGroupRowViewData {
  const CircleStatsGroupRowViewData({
    required this.id,
    required this.name,
    required this.memberCountLabel,
    this.conversationId,
  });

  final String id;
  final String name;
  final String memberCountLabel;

  /// 群会话绑定（Chat 反向写回）；未绑定时为 null，行不提供聊天导航。
  final String? conversationId;
}

class CircleStatsLikeRowViewData {
  const CircleStatsLikeRowViewData({
    required this.id,
    required this.userName,
    required this.userAvatarUrl,
    required this.content,
    required this.targetTitle,
    required this.time,
  });

  final String id;
  final String userName;
  final String userAvatarUrl;
  final String content;
  final String targetTitle;
  final String time;
}
