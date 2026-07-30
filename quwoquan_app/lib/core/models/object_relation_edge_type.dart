/// 对象关系边类型闭集。
///
/// 真相源是 `contracts/metadata/_shared/types.yaml` 的 `ObjectRelationEdgeType`，
/// parity 由 `quwoquan_ops/gate/verify_object_relation_edge_type_contract.py` 守。
///
/// 收敛前 `ObjectRelationEdge.edgeType` 是裸 String，词表实际分裂成两个互不相交的
/// 半边：服务侧物化器只写 semantic_co_mention / tag_overlap / geo_proximity，端侧
/// switch 只认 author_of / posted_to_circle / ...，两边各自消费自己那半且都不报错。
/// 收成枚举之后新增类型必须同时落到 metadata、Go 与这里，穷举 switch 会在编译期
/// 逼出未处理分支。
enum ObjectRelationEdgeType {
  authorOf('author_of'),
  postedToCircle('posted_to_circle'),
  resharedToCircle('reshared_to_circle'),
  mentionsEntity('mentions_entity'),
  commentAboutEntity('comment_about_entity'),
  circleUnderEntity('circle_under_entity'),
  memberOf('member_of'),
  reviewOf('review_of'),
  locatedIn('located_in'),
  partOf('part_of'),
  near('near'),
  routeStop('route_stop'),
  semanticCoMention('semantic_co_mention'),
  tagOverlap('tag_overlap'),
  geoProximity('geo_proximity'),
  behaviorCoEngagement('behavior_co_engagement');

  const ObjectRelationEdgeType(this.wire);

  final String wire;

  /// 把 wire 值收敛为枚举；不在闭集内返回 null。
  ///
  /// 返回 null 而不是回落到某个默认类型：未登记的 edgeType 说明服务端词表已经漂移，
  /// 此时静默按别的关系渲染会给用户一句错的关系描述，不如整条边不展示。
  static ObjectRelationEdgeType? tryParse(String? raw) {
    final value = raw?.trim() ?? '';
    if (value.isEmpty) {
      return null;
    }
    for (final candidate in ObjectRelationEdgeType.values) {
      if (candidate.wire == value) {
        return candidate;
      }
    }
    return null;
  }

  /// 断言型空间边：描述实体间固有地理关系，不随信号衰减退场。
  ///
  /// [geoProximity] 不在其列——它是「同域」算出来的共现信号，不等于两个实体真的挨着。
  bool get isSpatial => switch (this) {
    ObjectRelationEdgeType.locatedIn ||
    ObjectRelationEdgeType.partOf ||
    ObjectRelationEdgeType.near ||
    ObjectRelationEdgeType.routeStop => true,
    _ => false,
  };
}
