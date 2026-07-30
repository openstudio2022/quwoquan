package recommendation

// 对象关系边类型闭集，真相源 contracts/metadata/_shared/types.yaml 的
// ObjectRelationEdgeType，parity 由 quwoquan_ops/gate/verify_object_relation_edge_type_contract.py 守。
//
// 收敛前 edgeType 是无约束 string，词表实际分裂成两个互不相交的半边：物化器只写
// semantic_co_mention / tag_overlap / geo_proximity，端侧 switch 只认
// author_of / posted_to_circle / ...。两边各自消费自己那半，任何一侧都不会报错，
// 于是"对象页关系边"这个共同事实源在生产与消费之间从未真正对上。闭集加上 parity 门
// 让新增类型必须同时落到 metadata、Go 与端侧，drift 变成编译期/门禁期错误。

// ObjectRelationEdgeType 是边表 edgeType 的类型化取值。
type ObjectRelationEdgeType string

// 断言边：由第一方记录直接得出，不需要推断。
const (
	EdgeTypeAuthorOf           ObjectRelationEdgeType = "author_of"
	EdgeTypePostedToCircle     ObjectRelationEdgeType = "posted_to_circle"
	EdgeTypeResharedToCircle   ObjectRelationEdgeType = "reshared_to_circle"
	EdgeTypeMentionsEntity     ObjectRelationEdgeType = "mentions_entity"
	EdgeTypeCommentAboutEntity ObjectRelationEdgeType = "comment_about_entity"
	EdgeTypeCircleUnderEntity  ObjectRelationEdgeType = "circle_under_entity"
	EdgeTypeMemberOf           ObjectRelationEdgeType = "member_of"
	EdgeTypeReviewOf           ObjectRelationEdgeType = "review_of"
)

// 空间边：实体之间的地理关系。
//
// EdgeTypeNear 与 EdgeTypeGeoProximity 不可互换：后者是 conditionProfile.regions
// 相同算出来的共现信号（会随 TTL 退场），前者是断言两个实体在空间上挨着。
const (
	EdgeTypeLocatedIn ObjectRelationEdgeType = "located_in"
	EdgeTypePartOf    ObjectRelationEdgeType = "part_of"
	EdgeTypeNear      ObjectRelationEdgeType = "near"
	EdgeTypeRouteStop ObjectRelationEdgeType = "route_stop"
)

// 计算边：从既有信号派生，带 confidence 与 evidenceRefs，随 TTL 退场。
const (
	EdgeTypeSemanticCoMention    ObjectRelationEdgeType = "semantic_co_mention"
	EdgeTypeTagOverlap           ObjectRelationEdgeType = "tag_overlap"
	EdgeTypeGeoProximity         ObjectRelationEdgeType = "geo_proximity"
	EdgeTypeBehaviorCoEngagement ObjectRelationEdgeType = "behavior_co_engagement"
)

// objectRelationEdgeTypes 保持与 metadata 完全一致的顺序，parity 门按序比对。
var objectRelationEdgeTypes = []ObjectRelationEdgeType{
	EdgeTypeAuthorOf,
	EdgeTypePostedToCircle,
	EdgeTypeResharedToCircle,
	EdgeTypeMentionsEntity,
	EdgeTypeCommentAboutEntity,
	EdgeTypeCircleUnderEntity,
	EdgeTypeMemberOf,
	EdgeTypeReviewOf,
	EdgeTypeLocatedIn,
	EdgeTypePartOf,
	EdgeTypeNear,
	EdgeTypeRouteStop,
	EdgeTypeSemanticCoMention,
	EdgeTypeTagOverlap,
	EdgeTypeGeoProximity,
	EdgeTypeBehaviorCoEngagement,
}

// spatialObjectRelationEdgeTypes 是断言型空间边。它们描述实体间的固有地理关系，
// 不随信号衰减，因此不参与计算边的 TTL 退场。
var spatialObjectRelationEdgeTypes = map[ObjectRelationEdgeType]bool{
	EdgeTypeLocatedIn: true,
	EdgeTypePartOf:    true,
	EdgeTypeNear:      true,
	EdgeTypeRouteStop: true,
}

// ObjectRelationEdgeTypes 返回闭集副本，顺序与 metadata 一致。
func ObjectRelationEdgeTypes() []ObjectRelationEdgeType {
	out := make([]ObjectRelationEdgeType, len(objectRelationEdgeTypes))
	copy(out, objectRelationEdgeTypes)
	return out
}

// ObjectRelationEdgeTypeStrings 返回闭集的 wire 取值，便于构造 BSON 过滤与断言。
func ObjectRelationEdgeTypeStrings() []string {
	out := make([]string, 0, len(objectRelationEdgeTypes))
	for _, value := range objectRelationEdgeTypes {
		out = append(out, string(value))
	}
	return out
}

// ParseObjectRelationEdgeType 把 wire 值收敛为闭集成员；不认识的取值返回 false，
// 由调用方决定丢弃还是报错，禁止静默当作合法类型继续流转。
func ParseObjectRelationEdgeType(raw string) (ObjectRelationEdgeType, bool) {
	candidate := ObjectRelationEdgeType(raw)
	for _, value := range objectRelationEdgeTypes {
		if value == candidate {
			return value, true
		}
	}
	return "", false
}

// IsSpatial 判定是否为断言型空间边。
func (t ObjectRelationEdgeType) IsSpatial() bool {
	return spatialObjectRelationEdgeTypes[t]
}
