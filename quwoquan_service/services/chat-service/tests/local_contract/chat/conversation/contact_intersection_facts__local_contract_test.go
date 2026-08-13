// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/spec.md#req-003
// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/spec.md#req-001
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

// ContactIntersectionFacts 是联系首页/1v1 会话头 typed `ContactIntersectionFact`
// 的唯一 wire 收敛口径：≤2 条、只透传云侧 primaryText、身份字段缺失整条丢弃
//（Chat 不拼句、不造依据），intersectionClass 缺省诚实落 fact。
func TestContactIntersectionFactsProjectTypedWire(t *testing.T) {
	t.Parallel()
	facts := application.ContactIntersectionFacts([]application.ContactIntersectionSummary{
		{
			IntersectionID:    "i-1",
			SourceRef:         "coExperiencedGathering",
			Dimension:         "relationship",
			PrimaryText:       "你们一起参加过 1 次行动",
			IntersectionClass: "fact",
		},
		{
			IntersectionID: "i-2",
			SourceRef:      "coWishlistedEntity",
			Dimension:      "location",
			PrimaryText:    "你们都想去 2 个相同的地方",
			// intersectionClass 缺省 → fact（云侧事实通道缺标不得伪装成 affinity）。
		},
		{
			IntersectionID: "i-3",
			SourceRef:      "sharedCircle",
			Dimension:      "relationship",
			PrimaryText:    "第三条不得进入",
		},
	})
	if len(facts) != 2 {
		t.Fatalf("contact intersection facts must cap at 2, got %d", len(facts))
	}
	if facts[0]["kind"] != "coExperiencedGathering" ||
		facts[0]["primaryText"] != "你们一起参加过 1 次行动" ||
		facts[0]["intersectionClass"] != "fact" {
		t.Fatalf("first fact wire drifted: %+v", facts[0])
	}
	if facts[1]["intersectionClass"] != "fact" {
		t.Fatalf("missing class must default to fact, got %+v", facts[1])
	}
}

func TestContactIntersectionFactsDropDishonestRows(t *testing.T) {
	t.Parallel()
	facts := application.ContactIntersectionFacts([]application.ContactIntersectionSummary{
		{IntersectionID: "i-1", SourceRef: "sharedCircle", Dimension: "relationship"},
		{IntersectionID: "", SourceRef: "sharedCircle", Dimension: "relationship", PrimaryText: "缺身份"},
		{IntersectionID: "i-3", SourceRef: "", Dimension: "relationship", PrimaryText: "缺 kind"},
		{IntersectionID: "i-4", SourceRef: "sharedCircle", Dimension: "", PrimaryText: "缺维度"},
		{IntersectionID: "i-5", SourceRef: "sharedCircle", Dimension: "relationship", PrimaryText: "重复句"},
		{IntersectionID: "i-6", SourceRef: "sharedCircle", Dimension: "relationship", PrimaryText: "重复句"},
	})
	if len(facts) != 1 || facts[0]["primaryText"] != "重复句" {
		t.Fatalf("dishonest rows must be dropped entirely, got %+v", facts)
	}
}

func TestContactIntersectionResolverCarriesIntersectionClass(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"items": []map[string]any{
				{
					"intersectionId":    "i-1",
					"kind":              "coExperiencedGathering",
					"intersectionClass": "fact",
					"primaryText":       "你们一起参加过 1 次行动",
					"dimension":         "relationship",
				},
			},
		})
	}))
	t.Cleanup(server.Close)
	resolver, err := httpadapter.NewContactIntersectionResolverClient(
		server.URL,
		server.Client(),
		contactIntersectionAuthorization{},
	)
	if err != nil {
		t.Fatalf("new contact intersection resolver: %v", err)
	}
	items, err := resolver.ListContactIntersections(
		context.Background(),
		"viewer-a",
		"contact-b",
		2,
	)
	if err != nil {
		t.Fatalf("list contact intersections: %v", err)
	}
	if len(items) != 1 || items[0].IntersectionClass != "fact" ||
		items[0].SourceRef != "coExperiencedGathering" {
		t.Fatalf("intersectionClass must survive the resolver: %+v", items)
	}
}
