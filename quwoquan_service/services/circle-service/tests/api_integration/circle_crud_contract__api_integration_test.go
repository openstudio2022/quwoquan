package api_integration

import (
	"context"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// Circle creation writes only the Circle aggregate. The owner
// CircleMembership is a separate aggregate and must never be inserted by the
// Circle store as a hidden cross-aggregate write.

func TestCreateCircleWithOwner(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	rec := executeCircleCommand(t, http.MethodPost, "/circles", map[string]any{
		"name":     "摄影圈",
		"category": "interest",
		"tags":     []string{"photography", "art"},
	}, "circle-create-1", "persona-circle-owner", "CreateCircle", "/circles")

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", rec.Code, rec.Body.String())
	}

	receipt := decodeBody(t, rec)
	circleID, _ := receipt["circleId"].(string)
	if circleID == "" || receipt["version"] != float64(1) ||
		receipt["status"] != "active" || receipt["idempotentReplay"] != false {
		t.Fatalf("Circle command receipt drift: %#v", receipt)
	}

	var doc bson.M
	err := mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&doc)
	if err != nil {
		t.Fatalf("circle not found in MongoDB: %v", err)
	}
	if doc["name"] != "摄影圈" || doc["ownerId"] != "persona-circle-owner" {
		t.Errorf("aggregate state drift: name=%v ownerId=%v", doc["name"], doc["ownerId"])
	}

	// state / receipt / outbox 同一事务提交
	for collection, want := range map[string]int64{
		"circles": 1, "circle_command_receipts": 1, "circle_outbox": 1,
	} {
		count, err := mongoDB.Collection(collection).CountDocuments(context.Background(), bson.M{})
		if err != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, err)
		}
	}

	memberCount, err := mongoDB.Collection("circle_memberships").CountDocuments(context.Background(), bson.M{"circleId": circleID})
	if err != nil || memberCount != 0 {
		t.Fatalf("Circle store performed a hidden membership write: count=%d err=%v", memberCount, err)
	}
	if toInt64(doc["memberCount"]) != 0 {
		t.Errorf("memberCount must be projection-owned, got %v", doc["memberCount"])
	}

	// 相同 Idempotency-Key 重放首个回执
	replay := executeCircleCommand(t, http.MethodPost, "/circles", map[string]any{
		"name":     "摄影圈",
		"category": "interest",
		"tags":     []string{"photography", "art"},
	}, "circle-create-1", "persona-circle-owner", "CreateCircle", "/circles")
	if replay.Code != http.StatusCreated || decodeBody(t, replay)["idempotentReplay"] != true {
		t.Fatalf("Circle create replay drift: status=%d body=%s", replay.Code, replay.Body.String())
	}

	// 同 key 不同命令体 → 幂等冲突
	conflict := executeCircleCommand(t, http.MethodPost, "/circles", map[string]any{
		"name": "另一个圈子",
	}, "circle-create-1", "persona-circle-owner", "CreateCircle", "/circles")
	if conflict.Code != http.StatusConflict || decodeBody(t, conflict)["code"] != "CIRCLE.USER.circle_idempotency_conflict" {
		t.Fatalf("Circle idempotency conflict drift: status=%d body=%s", conflict.Code, conflict.Body.String())
	}

	// CircleCreated 经 outbox relay 投递
	drainCircleEvents(t)
	if events := eventSpy.EventsOfType("CircleCreated"); len(events) == 0 {
		t.Error("expected CircleCreated event through outbox relay")
	}
}

func TestGetCircleSuccess(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	circleID := createTestCircle(t, "测试圈子")

	rec := doRequest(t, http.MethodGet, "/circles/"+circleID, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	body := decodeBody(t, rec)
	data := body["data"].(map[string]any)
	if data["name"] != "测试圈子" {
		t.Errorf("expected name=测试圈子, got %v", data["name"])
	}
	if data["version"] != float64(1) {
		t.Errorf("detail read must expose aggregate version, got %v", data["version"])
	}
}

func TestListCirclesSuccess(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	createTestCircle(t, "圈子A")
	createTestCircle(t, "圈子B")

	rec := doRequest(t, http.MethodGet, "/circles?limit=10", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) < 2 {
		t.Errorf("expected at least 2 circles, got %d", len(items))
	}
}

func TestUpdateCircleSuccess(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	circleID := createTestCircleAs(t, "原名", "persona-circle-owner")

	rec := executeCircleCommand(t, http.MethodPatch, "/circles/"+circleID, map[string]any{
		"name":           "新名",
		"rulesText":      "尊重原创，禁止人身攻击。",
		"welcomeMessage": "欢迎先阅读圈规，再发布第一条作品。",
	}, "circle-update-1", "persona-circle-owner", "UpdateCircle", "/circles/{circleId}")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	receipt := decodeBody(t, rec)
	if receipt["circleId"] != circleID || receipt["version"] != float64(2) || receipt["idempotentReplay"] != false {
		t.Fatalf("Circle update receipt drift: %#v", receipt)
	}

	var doc bson.M
	if err := mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&doc); err != nil {
		t.Fatalf("circle not found: %v", err)
	}
	if doc["name"] != "新名" ||
		doc["rulesText"] != "尊重原创，禁止人身攻击。" ||
		doc["welcomeMessage"] != "欢迎先阅读圈规，再发布第一条作品。" ||
		toInt64(doc["version"]) != 2 {
		t.Errorf("update state drift: %#v", doc)
	}

	// 未知字段 fail closed（typed 请求体）
	unknown := executeCircleCommand(t, http.MethodPatch, "/circles/"+circleID, map[string]any{
		"name": "白名单外", "hackField": true,
	}, "circle-update-unknown", "persona-circle-owner", "UpdateCircle", "/circles/{circleId}")
	if unknown.Code != http.StatusBadRequest {
		t.Fatalf("unknown field must fail closed, got %d: %s", unknown.Code, unknown.Body.String())
	}

	// 非管理成员 BOLA fail closed
	denied := executeCircleCommand(t, http.MethodPatch, "/circles/"+circleID, map[string]any{
		"name": "越权改名",
	}, "circle-update-bola", "persona-outsider", "UpdateCircle", "/circles/{circleId}")
	if denied.Code != http.StatusForbidden || decodeBody(t, denied)["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("Circle update BOLA must fail closed: status=%d body=%s", denied.Code, denied.Body.String())
	}

	drainCircleEvents(t)
	if events := eventSpy.EventsOfType("CircleUpdated"); len(events) == 0 {
		t.Error("expected CircleUpdated event through outbox relay")
	} else if events[0].Payload["rulesText"] != "尊重原创，禁止人身攻击。" ||
		events[0].Payload["welcomeMessage"] != "欢迎先阅读圈规，再发布第一条作品。" {
		t.Fatalf("CircleUpdated governance payload drift: %#v", events[0].Payload)
	}
}

func TestArchiveCircleSuccess(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	circleID := createTestCircleAs(t, "待归档圈子", "persona-circle-owner")

	// 非圈主归档 fail closed
	denied := executeCircleCommand(t, http.MethodDelete, "/circles/"+circleID, nil,
		"circle-archive-bola", "persona-outsider", "ArchiveCircle", "/circles/{circleId}")
	if denied.Code != http.StatusForbidden {
		t.Fatalf("Circle archive BOLA must fail closed: status=%d body=%s", denied.Code, denied.Body.String())
	}

	rec := executeCircleCommand(t, http.MethodDelete, "/circles/"+circleID, nil,
		"circle-archive-1", "persona-circle-owner", "ArchiveCircle", "/circles/{circleId}")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	receipt := decodeBody(t, rec)
	if receipt["status"] != "archived" || receipt["version"] != float64(2) {
		t.Fatalf("Circle archive receipt drift: %#v", receipt)
	}

	var doc bson.M
	mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&doc)
	if doc["status"] != "archived" {
		t.Errorf("expected status=archived, got %v", doc["status"])
	}

	// 已归档后的新 key：no-op receipt（不递增版本），相同 key 重放
	noop := executeCircleCommand(t, http.MethodDelete, "/circles/"+circleID, nil,
		"circle-archive-noop", "persona-circle-owner", "ArchiveCircle", "/circles/{circleId}")
	if noop.Code != http.StatusOK {
		t.Fatalf("archive no-op failed: %d %s", noop.Code, noop.Body.String())
	}
	noopReceipt := decodeBody(t, noop)
	if noopReceipt["version"] != float64(2) || noopReceipt["idempotentReplay"] != true {
		t.Fatalf("archive no-op must keep version and replay: %#v", noopReceipt)
	}
	replay := executeCircleCommand(t, http.MethodDelete, "/circles/"+circleID, nil,
		"circle-archive-noop", "persona-circle-owner", "ArchiveCircle", "/circles/{circleId}")
	if replay.Code != http.StatusOK || decodeBody(t, replay)["idempotentReplay"] != true {
		t.Fatalf("archive no-op replay drift: %d %s", replay.Code, replay.Body.String())
	}

	drainCircleEvents(t)
	if events := eventSpy.EventsOfType("CircleArchived"); len(events) != 1 {
		t.Errorf("expected exactly one CircleArchived event, got %d", len(eventSpy.EventsOfType("CircleArchived")))
	}
}
