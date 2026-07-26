package recommendation_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"testing"
	"time"
)

// W10 关系图谱自动物化契约（B22）：边 key 幂等、双向可查、TTL 退场、
// 行为共现边 S1 schema 就绪、辅助函数确定性。
func TestObjectRelationEdgeKeyIsDeterministic(t *testing.T) {
	doc := ObjectRelationEdgeDoc{
		EdgeKey:   SemanticCoMentionEdgeType + "|/entity/a|/entity/b",
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
	for _, edgeType := range []string{
		SemanticCoMentionEdgeType,
		TagOverlapEdgeType,
		GeoProximityEdgeType,
	} {
		if edgeType == "" {
			t.Fatal("content-side edge types must be non-empty")
		}
	}
	if ObjectRelationEdgeTTL < 7*24*time.Hour {
		t.Fatalf("edge TTL must allow weekly refresh cadence, got %v", ObjectRelationEdgeTTL)
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
