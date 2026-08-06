/// 圈子统计列表页（成员 / 群组 / 点赞动态）行视图模型。
class CircleStatsMemberRowViewData {
  CircleStatsMemberRowViewData({
    required this.id,
    required this.name,
    required this.avatarUrl,
    required this.worksCountLabel,
    required this.fansCountLabel,
    required this.likesCountLabel,
    required this.isFollowed,
  });

  final String id;
  final String name;
  final String avatarUrl;
  final String worksCountLabel;
  final String fansCountLabel;
  final String likesCountLabel;
  bool isFollowed;
}

class CircleStatsGroupRowViewData {
  const CircleStatsGroupRowViewData({
    required this.id,
    required this.name,
    required this.memberCountLabel,
  });

  final String id;
  final String name;
  final String memberCountLabel;
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
