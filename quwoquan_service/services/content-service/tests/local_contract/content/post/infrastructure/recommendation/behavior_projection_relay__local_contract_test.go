package recommendation_test

// N0-2 契约：BehaviorProjectionRelay 从 rm_behavior_events 重建的
// BehaviorBatchReported 事件必须与在线 ProcessBatch 的 payload 同构——
// RecommendFeatureProjector.onBehaviorBatch 消费的每个字段都能取到值。
// 防止 relay 与 projector 之间出现第二套字段名（R24 单真相源）。

import (
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/content/post/application/ports"
)

func relayRow(id bson.ObjectID, ev ports.RawBehaviorEvent) RelayBehaviorEvent {
	return RelayBehaviorEvent{ID: id, RawBehaviorEvent: ev}
}

func TestBuildBehaviorBatchEvents_EmitsOneAtomicEventPerFact(t *testing.T) {
	now := time.Now().UTC()
	rows := []RelayBehaviorEvent{
		relayRow(bson.NewObjectID(), ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", Action: "click", ContentID: "c1", CreatedAt: now}),
		relayRow(bson.NewObjectID(), ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", Action: "dwell", ContentID: "c2", CreatedAt: now.Add(time.Second)}),
		relayRow(bson.NewObjectID(), ports.RawBehaviorEvent{UserID: "u2", SessionID: "s9", Action: "like", ContentID: "c3", CreatedAt: now}),
	}

	events := BuildBehaviorBatchEvents(rows)
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
// helper（StrVal/IntVal/AnySlice）兼容。
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

	payload := BehaviorEventPayload(ev)

	if got := StrVal(payload, "action"); got != "impression" {
		t.Fatalf("action: want impression, got %q", got)
	}
	if got := StrVal(payload, "contentType"); got != "image" {
		t.Fatalf("contentType: want image (projector typeImpressions 依赖), got %q", got)
	}
	if got := StrVal(payload, "state"); got != "impressed" {
		t.Fatalf("state: want impressed (七态语义), got %q", got)
	}
	if got := StrVal(payload, "authorId"); got != "author_9" {
		t.Fatalf("authorId: want author_9, got %q", got)
	}
	if got := StrVal(payload, "referralSource"); got != "home_feed" {
		t.Fatalf("referralSource: want home_feed, got %q", got)
	}
	if got := IntVal(payload, "engagementDepth"); got != 2 {
		t.Fatalf("engagementDepth: want 2, got %d", got)
	}
	if got := AnySlice(payload, "tagRefs"); len(got) != 1 || got[0] != "Topic/旅行" {
		t.Fatalf("tagRefs: want [Topic/旅行], got %v", got)
	}
	if got := AnySlice(payload, "entityRefs"); len(got) != 1 || got[0] != "entity_west_lake" {
		t.Fatalf("entityRefs: want [entity_west_lake], got %v", got)
	}
	if got := StrVal(payload, "intersectionSourceRef"); got != "sharedCircle" {
		t.Fatalf("intersectionSourceRef: want sharedCircle (交集 kindCounts 依赖), got %q", got)
	}
	if got := StrVal(payload, "contentId"); got != "c1" {
		t.Fatalf("contentId: want c1 (discovery viewCount 依赖), got %q", got)
	}
}

// 每条事实必须保持 _id（写入）全序；projector 用该原子水位去重。
func TestBuildBehaviorBatchEvents_PreservesOrderAndLastID(t *testing.T) {
	first := bson.NewObjectID()
	second := bson.NewObjectID()
	rows := []RelayBehaviorEvent{
		relayRow(first, ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "click", CreatedAt: time.Now().UTC()}),
		relayRow(second, ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", ContentID: "c2", Action: "like", CreatedAt: time.Now().UTC()}),
	}

	events := BuildBehaviorBatchEvents(rows)
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
	if StrVal(firstPayload[0], "contentId") != "c1" || StrVal(secondPayload[0], "contentId") != "c2" {
		t.Fatal("payload events must preserve insertion order")
	}
}

// projector 直连契约：relay 构造的事件被 RecommendFeatureProjector 分派到
// onBehaviorBatch（不因 payload 类型不匹配静默 no-op）。使用 nil coll 会
// panic，故这里只验证 BehaviorPayloadEvents 与 relay events 载荷的类型兼容。
func TestRelayPayloadEventsAreConsumableByProjectorHelpers(t *testing.T) {
	rows := []RelayBehaviorEvent{
		relayRow(bson.NewObjectID(), ports.RawBehaviorEvent{UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "click", CreatedAt: time.Now().UTC()}),
	}
	events := BuildBehaviorBatchEvents(rows)
	parsed := BehaviorPayloadEvents(events[0].Payload["events"])
	if len(parsed) != 1 {
		t.Fatalf("BehaviorPayloadEvents must parse relay payload, got %d entries", len(parsed))
	}
	if StrVal(parsed[0], "contentId") != "c1" {
		t.Fatalf("parsed payload lost contentId: %v", parsed[0])
	}
}

func TestBehaviorProjectionScanFilter_ZeroLagIncludesCurrentSecond(t *testing.T) {
	now := time.Date(2026, time.July, 21, 4, 0, 0, 999_000_000, time.UTC)
	lastID := bson.NewObjectIDFromTimestamp(now.Add(-time.Second))
	relay := &BehaviorProjectionRelay{WatermarkLag: 0}

	filter := relay.ScanFilter(lastID, now)
	bounds, ok := filter["_id"].(bson.M)
	if !ok {
		t.Fatalf("zero-lag scan must preserve resume cursor, filter=%#v", filter)
	}
	if got := bounds["$gt"]; got != lastID {
		t.Fatalf("zero-lag scan cursor=%v, want %v", got, lastID)
	}
	if _, exists := bounds["$lt"]; exists {
		t.Fatalf(
			"zero-lag scan must not use second-granularity upper bound; current-second events would be skipped: %#v",
			bounds,
		)
	}
}

func TestBehaviorProjectionScanFilter_PositiveLagKeepsWatermark(t *testing.T) {
	now := time.Date(2026, time.July, 21, 4, 0, 10, 0, time.UTC)
	relay := &BehaviorProjectionRelay{WatermarkLag: 2 * time.Second}

	filter := relay.ScanFilter(bson.ObjectID{}, now)
	bounds, ok := filter["_id"].(bson.M)
	if !ok {
		t.Fatalf("positive-lag scan must retain watermark, filter=%#v", filter)
	}
	got, ok := bounds["$lt"].(bson.ObjectID)
	if !ok {
		t.Fatalf("watermark must be ObjectID, got %T", bounds["$lt"])
	}
	wantAt := now.Add(-2 * time.Second)
	if !got.Timestamp().Equal(wantAt) {
		t.Fatalf("watermark timestamp=%s, want %s", got.Timestamp(), wantAt)
	}
}
