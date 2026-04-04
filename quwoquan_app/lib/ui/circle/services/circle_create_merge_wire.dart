/// 创建圈子后合并 wire 与远端返回，供 [CircleDto.fromMap] 使用。
Map<String, dynamic> mergeCreateCircleWireWithCreated(
  Map<String, dynamic> wire,
  Map<String, dynamic> created,
) {
  return <String, dynamic>{
    ...wire,
    ...created,
    'role': created['role'] ?? 'owner',
    'joinStatus': created['joinStatus'] ?? 'joined',
    'isFollowed': created['isFollowed'] ?? true,
    'memberCount': created['memberCount'] ?? 1,
    'postCount': created['postCount'] ?? 0,
    'weeklyActiveCount': created['weeklyActiveCount'] ?? 0,
    'createdAt': created['createdAt'] ?? DateTime.now().toIso8601String(),
    'updatedAt': created['updatedAt'] ?? DateTime.now().toIso8601String(),
  };
}
