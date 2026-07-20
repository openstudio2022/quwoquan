package recommendation

// N0-2 契约：BehaviorProjectionRelay 从 rm_behavior_events 重建的
// BehaviorBatchReported 事件必须与在线 ProcessBatch 的 payload 同构——
// RecommendFeatureProjector.onBehaviorBatch 消费的每个字段都能取到值。
// 防止 relay 与 projector 之间出现第二套字段名（R24 单真相源）。

import (
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/application/ports"
)

func relayRow(id bson.ObjectID, ev ports.RawBehaviorEvent) relayBehaviorEvent {
	return relayBehaviorEvent{ID: id, RawBehaviorEvent: ev}
}

func TestBuildBehaviorBatchEvents_EmitsOneAtomicEventPerFact(t *testing.T) {
	now := time.Now().UTC()
	rows := []relayBehaviorEvent{
		relayRow(bson.NewObjectID(), ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", Action: "click", ContentID: "c1", CreatedAt: now}),
		relayRow(bson.NewObjectID(), ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", Action: "dwell", ContentID: "c2", CreatedAt: now.Add(time.Second)}),
		relayRow(bson.NewObjectID(), ports.RawBehaviorEvent{UserID: "u2", SessionID: "s9", Action: "like", ContentID: "c3", CreatedAt: now}),
	}

	events := buildBehaviorBatchEvents(rows)
	if len(events) != len(rows) {
		t.Fatalf("expected one atomic projection event per fact, got %d", len(events))
	}
	first := events[0]
	if first.Type != "BehaviorBatchReported" {
		t.Fatalf("event type must be BehaviorBatchReported, got %s", first.Type)
	}
	if got := first.Payload["userId"]; got != "u1" {
		t.Fatalf("first batch userId want u1, got %v", got)
	}
	if got := first.Payload["count"]; got != 1 {
		t.Fatalf("atomic projection event count want 1, got %v", got)
	}
	if events[2].AggregateID != "s9" {
		t.Fatalf("aggregateID should prefer sessionId, got %s", events[2].AggregateID)
	}
}

// relay payload 必须携带 onBehaviorBatch 消费的全部字段，且类型与解析
// helper（strVal/intVal/anySlice）兼容。
func TestBehaviorEventPayload_FieldContractForProjector(t *testing.T) {
	ev := ports.RawBehaviorEvent{
		ClientEventID:         "evt-1",
		State:                 "impressed",
		UserID:                "u1",
		SessionID:             "s1",
		ContentID:             "c1",
		Action:                "impression",
		ContentType:           "image",
		Tags:                  []string{"Topic/旅行"},
		AuthorID:              "author_9",
		ReferralSource:        "home_feed",
		EngagementDepth:       2,
		EntityRefs:            []string{"entity_west_lake"},
		IntersectionSourceRef: "sharedCircle",
		OccurredAt:            time.Now().UTC().Format(time.RFC3339),
		CreatedAt:             time.Now().UTC(),
	}

	payload := behaviorEventPayload(ev)

	if got := strVal(payload, "action"); got != "impression" {
		t.Fatalf("action: want impression, got %q", got)
	}
	if got := strVal(payload, "contentType"); got != "image" {
		t.Fatalf("contentType: want image (projector typeImpressions 依赖), got %q", got)
	}
	if got := strVal(payload, "state"); got != "impressed" {
		t.Fatalf("state: want impressed (七态语义), got %q", got)
	}
	if got := strVal(payload, "authorId"); got != "author_9" {
		t.Fatalf("authorId: want author_9, got %q", got)
	}
	if got := strVal(payload, "referralSource"); got != "home_feed" {
		t.Fatalf("referralSource: want home_feed, got %q", got)
	}
	if got := intVal(payload, "engagementDepth"); got != 2 {
		t.Fatalf("engagementDepth: want 2, got %d", got)
	}
	if got := anySlice(payload, "tagRefs"); len(got) != 1 || got[0] != "Topic/旅行" {
		t.Fatalf("tagRefs: want [Topic/旅行], got %v", got)
	}
	if got := anySlice(payload, "entityRefs"); len(got) != 1 || got[0] != "entity_west_lake" {
		t.Fatalf("entityRefs: want [entity_west_lake], got %v", got)
	}
	if got := strVal(payload, "intersectionSourceRef"); got != "sharedCircle" {
		t.Fatalf("intersectionSourceRef: want sharedCircle (交集 kindCounts 依赖), got %q", got)
	}
	if got := strVal(payload, "contentId"); got != "c1" {
		t.Fatalf("contentId: want c1 (discovery viewCount 依赖), got %q", got)
	}
}

// 每条事实必须保持 _id（写入）全序；projector 用该原子水位去重。
func TestBuildBehaviorBatchEvents_PreservesOrderAndLastID(t *testing.T) {
	first := bson.NewObjectID()
	second := bson.NewObjectID()
	rows := []relayBehaviorEvent{
		relayRow(first, ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "click", CreatedAt: time.Now().UTC()}),
		relayRow(second, ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", ContentID: "c2", Action: "like", CreatedAt: time.Now().UTC()}),
	}

	events := buildBehaviorBatchEvents(rows)
	if len(events) != 2 {
		t.Fatalf("expected two atomic projection events, got %d", len(events))
	}
	if events[0].ID != first.Hex() || events[1].ID != second.Hex() {
		t.Fatalf("projection event IDs must preserve row order: got %s, %s", events[0].ID, events[1].ID)
	}
	firstPayload, _ := events[0].Payload["events"].([]map[string]any)
	secondPayload, _ := events[1].Payload["events"].([]map[string]any)
	if len(firstPayload) != 1 || len(secondPayload) != 1 {
		t.Fatalf("each projection event must contain one fact, got %d and %d", len(firstPayload), len(secondPayload))
	}
	if strVal(firstPayload[0], "contentId") != "c1" || strVal(secondPayload[0], "contentId") != "c2" {
		t.Fatal("payload events must preserve insertion order")
	}
}

// projector 直连契约：relay 构造的事件被 RecommendFeatureProjector 分派到
// onBehaviorBatch（不因 payload 类型不匹配静默 no-op）。使用 nil coll 会
// panic，故这里只验证 behaviorPayloadEvents 与 relay events 载荷的类型兼容。
func TestRelayPayloadEventsAreConsumableByProjectorHelpers(t *testing.T) {
	rows := []relayBehaviorEvent{
		relayRow(bson.NewObjectID(), ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "click", CreatedAt: time.Now().UTC()}),
	}
	events := buildBehaviorBatchEvents(rows)
	parsed := behaviorPayloadEvents(events[0].Payload["events"])
	if len(parsed) != 1 {
		t.Fatalf("behaviorPayloadEvents must parse relay payload, got %d entries", len(parsed))
	}
	if strVal(parsed[0], "contentId") != "c1" {
		t.Fatalf("parsed payload lost contentId: %v", parsed[0])
	}
}
