package recommendation_test

import (
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

// W10 关系图谱自动物化契约（B22）：边 key 幂等、双向可查、TTL 退场、
// 行为共现边 S1 schema 就绪、辅助函数确定性。
func TestObjectRelationEdgeKeyIsDeterministic(t *testing.T) {
	doc := ObjectRelationEdgeDoc{
		EdgeKey:   string(SemanticCoMentionEdgeType) + "|/entity/a|/entity/b",
		EdgeType:  SemanticCoMentionEdgeType,
		SourceRef: "/entity/a",
		TargetRef: "/entity/b",
	}
	if doc.EdgeKey != "semantic_co_mention|/entity/a|/entity/b" {
		t.Fatalf("edge key layout drifted: %s", doc.EdgeKey)
	}
}

func TestBehaviorCoEngagementEdgeSchemaIsReadyForS1(t *testing.T) {
	// S1 触发开启的行为共现边：类型契约必须已锁定（开启只加物化实现，
	// 消费方读接口不变——阶段门"可开启不重构"判据）。
	if BehaviorCoEngagementEdgeType != "behavior_co_engagement" {
		t.Fatalf("behavior co-engagement edge type drifted: %s", BehaviorCoEngagementEdgeType)
	}
}

func TestContentSideEdgeTypesAreClosedSet(t *testing.T) {
	// 此前这个测试只断言非空，所以"闭集"是个空承诺：内容侧随便造一个新字符串也能过，
	// 而端侧 switch 永远认不出来。现在每个内容侧类型必须能被共享闭集解析。
	for _, edgeType := range []rtrec.ObjectRelationEdgeType{
		SemanticCoMentionEdgeType,
		TagOverlapEdgeType,
		GeoProximityEdgeType,
		BehaviorCoEngagementEdgeType,
	} {
		if _, ok := rtrec.ParseObjectRelationEdgeType(string(edgeType)); !ok {
			t.Fatalf("content-side edge type %q is outside ObjectRelationEdgeType", edgeType)
		}
	}
	if ObjectRelationEdgeTTL < 7*24*time.Hour {
		t.Fatalf("edge TTL must allow weekly refresh cadence, got %v", ObjectRelationEdgeTTL)
	}
}

func TestSpatialEdgeTypesAreDistinctFromComputedProximity(t *testing.T) {
	// located_in/part_of/near/route_stop 是断言型空间关系；geo_proximity 是
	// conditionProfile.regions 相同算出来的共现信号。把两者混同会让"位于/属于"
	// 这类地理包含被当成会 TTL 退场的弱信号。
	for _, spatial := range []rtrec.ObjectRelationEdgeType{
		rtrec.EdgeTypeLocatedIn,
		rtrec.EdgeTypePartOf,
		rtrec.EdgeTypeNear,
		rtrec.EdgeTypeRouteStop,
	} {
		if _, ok := rtrec.ParseObjectRelationEdgeType(string(spatial)); !ok {
			t.Fatalf("spatial edge type %q must be part of the closed set", spatial)
		}
		if !spatial.IsSpatial() {
			t.Fatalf("edge type %q must be classified as spatial", spatial)
		}
	}
	if rtrec.EdgeTypeGeoProximity.IsSpatial() {
		t.Fatal("geo_proximity is a computed co-occurrence signal, not a spatial assertion")
	}
}

func TestUnknownEdgeTypeIsRejectedRatherThanCoerced(t *testing.T) {
	for _, raw := range []string{"", "co_tagged", "GEO_PROXIMITY", "located-in"} {
		if parsed, ok := rtrec.ParseObjectRelationEdgeType(raw); ok {
			t.Fatalf("edge type %q must not parse, got %q", raw, parsed)
		}
	}
}

func TestSharedStringsIsDeterministicAndDeduped(t *testing.T) {
	shared := SharedStrings(
		[]string{"Topic/旅行", "Topic/摄影", "Topic/旅行"},
		[]string{"Topic/摄影", "Topic/旅行", "Topic/美食"},
	)
	if len(shared) != 2 || shared[0] != "Topic/摄影" || shared[1] != "Topic/旅行" {
		t.Fatalf("SharedStrings must be sorted+deduped, got %v", shared)
	}
}

func TestMaterializerNilFailsOpen(t *testing.T) {
	var m *ObjectRelationEdgeMaterializer
	counts, err := m.MaterializeAll(t.Context())
	if err != nil || counts != nil {
		t.Fatalf("nil materializer must fail open, counts=%v err=%v", counts, err)
	}
	var reader *ObjectRelationEdgeReader
	edges, err := reader.EdgesFrom(t.Context(), "/entity/a", 5)
	if err != nil || edges != nil {
		t.Fatalf("nil reader must fail open, edges=%v err=%v", edges, err)
	}
}
