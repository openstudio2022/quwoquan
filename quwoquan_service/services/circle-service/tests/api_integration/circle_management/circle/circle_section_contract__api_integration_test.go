// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// readiness_case: update-circle-sections-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

// seedPlacementPolicy 预置 placement 权限读模型（post owner 投影）。
func seedPlacementPolicy(t *testing.T, circleID, postID, ownerPersonaID string) {
	t.Helper()
	if _, err := mongoDB.Collection("circle_post_owner_views").InsertOne(context.Background(), bson.M{
		"_id": postID, "ownerPersonaId": ownerPersonaID, "state": "published",
	}); err != nil {
		t.Fatal(err)
	}
	_ = circleID
}

func executePlacementCommand(t *testing.T, method, path string, body any, idempotencyKey, personaID, operationName, pathTemplate string) *httptest.ResponseRecorder {
	t.Helper()
	var buffer bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buffer).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	request := httptest.NewRequest(method, path, &buffer)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	guard := rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle_post_placement." + operationName,
			ContractGraphSHA256:  "circle-placement-api-integration",
			Method:               method, PathTemplate: pathTemplate,
			OperationKind: "command", MutationTarget: "CirclePostPlacement", InvariantTarget: "CirclePostPlacement",
			AuthMode: "required", ActorRequirement: "persona", Principal: "persona",
			CommercialStatus: "ready", TimeoutMilliseconds: 1500,
		}}, method, pathTemplate,
	)(testHandler)
	guard.ServeHTTP(recorder, request)
	return recorder
}

// --- section_config_update (contract.yaml scenario) ---

func TestSectionConfigUpdate(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	circleID := createTestCircleAs(t, "板块配置圈子", "persona-circle-owner")

	newSections := []map[string]any{
		{"sectionType": "chat", "visible": true, "order": 0},
		{"sectionType": "works", "visible": true, "order": 1},
		{"sectionType": "storage", "visible": false, "order": 2},
		{"sectionType": "members", "visible": true, "order": 3},
	}

	rec := executeCircleCommand(t, http.MethodPatch, "/circles/"+circleID+"/sections", map[string]any{
		"sections": newSections,
	}, "circle-sections-1", "persona-circle-owner", "UpdateCircleSections", "/circles/{circleId}/sections")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	receipt := decodeBody(t, rec)
	if receipt["version"] != float64(2) || receipt["idempotentReplay"] != false {
		t.Fatalf("sections receipt drift: %#v", receipt)
	}

	drainCircleEvents(t)
	if events := eventSpy.EventsOfType("CircleSectionsUpdated"); len(events) == 0 {
		t.Error("expected CircleSectionsUpdated event through outbox relay")
	}

	// sectionType 重复必须 fail closed（owned entity 只经聚合根校验）
	duplicated := executeCircleCommand(t, http.MethodPatch, "/circles/"+circleID+"/sections", map[string]any{
		"sections": []map[string]any{
			{"sectionType": "chat", "visible": true, "order": 0},
			{"sectionType": "chat", "visible": true, "order": 1},
		},
	}, "circle-sections-dup", "persona-circle-owner", "UpdateCircleSections", "/circles/{circleId}/sections")
	if duplicated.Code != http.StatusBadRequest {
		t.Fatalf("duplicate sectionType must fail closed, got %d", duplicated.Code)
	}

	// Verify persisted
	rec = doRequest(t, http.MethodGet, "/circles/"+circleID, nil)
	body := decodeBody(t, rec)
	data := body["data"].(map[string]any)
	sections := data["sectionConfig"].([]any)
	if len(sections) != 4 {
		t.Errorf("expected 4 sections, got %d", len(sections))
	}
	first := sections[0].(map[string]any)
	if first["sectionType"] != "chat" {
		t.Errorf("expected first section=chat, got %v", first["sectionType"])
	}
}

// --- feed_pin_and_feature ---
// 展示位唯一写入口是 CirclePostPlacement 命令；feed 直接联合 placement
// 聚合读模型，禁止把圈子级 pin/feature 污染到本地 Post 展示快照。

func TestFeedPinAndFeature(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	circleID := createTestCircleAs(t, "Feed管理圈子", "persona-circle-owner")
	secondCircleID := createTestCircleAs(t, "第二个Feed管理圈子", "persona-circle-owner")
	insertCircleFeedItem(t, bson.M{
		"_id":   "post_001",
		"title": "待管理帖子",
	})
	seedPlacementPolicy(t, circleID, "post_001", "persona-post-owner")

	place := executePlacementCommand(t, http.MethodPost, "/circles/"+circleID+"/post-placements",
		map[string]any{"postId": "post_001"},
		"placement-place-1", "persona-post-owner", "PlacePostInCircle",
		"/circles/{circleId}/post-placements")
	if place.Code != http.StatusCreated {
		t.Fatalf("place post failed: %d %s", place.Code, place.Body.String())
	}
	placementID, _ := decodeBody(t, place)["placementId"].(string)
	if placementID == "" {
		t.Fatal("placement receipt missing placementId")
	}
	secondPlace := executePlacementCommand(t, http.MethodPost, "/circles/"+secondCircleID+"/post-placements",
		map[string]any{"postId": "post_001"},
		"placement-place-2", "persona-post-owner", "PlacePostInCircle",
		"/circles/{circleId}/post-placements")
	if secondPlace.Code != http.StatusCreated {
		t.Fatalf("place post in second circle failed: %d %s", secondPlace.Code, secondPlace.Body.String())
	}
	secondPlacementID, _ := decodeBody(t, secondPlace)["placementId"].(string)

	pin := executePlacementCommand(t, http.MethodPatch,
		"/circles/"+circleID+"/post-placements/"+placementID+"/pin",
		map[string]any{"enabled": true},
		"placement-pin-1", "persona-circle-owner", "PinCirclePost",
		"/circles/{circleId}/post-placements/{placementId}/pin")
	if pin.Code != http.StatusOK {
		t.Fatalf("pin: expected 200, got %d %s", pin.Code, pin.Body.String())
	}

	feature := executePlacementCommand(t, http.MethodPatch,
		"/circles/"+circleID+"/post-placements/"+placementID+"/feature",
		map[string]any{"enabled": true},
		"placement-feature-1", "persona-circle-owner", "FeatureCirclePost",
		"/circles/{circleId}/post-placements/{placementId}/feature")
	if feature.Code != http.StatusOK {
		t.Fatalf("feature: expected 200, got %d %s", feature.Code, feature.Body.String())
	}

	var doc bson.M
	if err := mongoDB.Collection("circle_feed_items").FindOne(context.Background(), bson.M{"_id": "post_001"}).Decode(&doc); err != nil {
		t.Fatalf("find post_001 failed: %v", err)
	}
	if _, polluted := doc["pinned"]; polluted {
		t.Fatalf("shared post must not carry circle placement pinned state: %#v", doc)
	}
	if _, polluted := doc["featured"]; polluted {
		t.Fatalf("shared post must not carry circle placement featured state: %#v", doc)
	}

	firstFeed := doRequest(t, http.MethodGet, "/circles/"+circleID+"/feed?sort=featured", nil)
	if firstFeed.Code != http.StatusOK {
		t.Fatalf("first circle feed failed: %d %s", firstFeed.Code, firstFeed.Body.String())
	}
	firstItems := decodeBody(t, firstFeed)["items"].([]any)
	if len(firstItems) != 1 {
		t.Fatalf("expected one first-circle item, got %#v", firstItems)
	}
	firstItem := firstItems[0].(map[string]any)
	if firstItem["placementId"] != placementID ||
		firstItem["pinned"] != true ||
		firstItem["featured"] != true {
		t.Fatalf("first-circle placement projection drift: %#v", firstItem)
	}

	secondFeed := doRequest(t, http.MethodGet, "/circles/"+secondCircleID+"/feed?sort=featured", nil)
	if secondFeed.Code != http.StatusOK {
		t.Fatalf("second circle feed failed: %d %s", secondFeed.Code, secondFeed.Body.String())
	}
	secondItems := decodeBody(t, secondFeed)["items"].([]any)
	if len(secondItems) != 1 {
		t.Fatalf("expected one second-circle item, got %#v", secondItems)
	}
	secondItem := secondItems[0].(map[string]any)
	if secondItem["placementId"] != secondPlacementID ||
		secondItem["pinned"] != false ||
		secondItem["featured"] != false {
		t.Fatalf("second-circle placement must remain independent: %#v", secondItem)
	}

	// pin no-op：目标状态已满足的首个 key 也持久化 receipt 并标记重放
	noop := executePlacementCommand(t, http.MethodPatch,
		"/circles/"+circleID+"/post-placements/"+placementID+"/pin",
		map[string]any{"enabled": true},
		"placement-pin-noop", "persona-circle-owner", "PinCirclePost",
		"/circles/{circleId}/post-placements/{placementId}/pin")
	if noop.Code != http.StatusOK || decodeBody(t, noop)["idempotentReplay"] != true {
		t.Fatalf("pin no-op must persist receipt and replay: %d %s", noop.Code, noop.Body.String())
	}
	replay := executePlacementCommand(t, http.MethodPatch,
		"/circles/"+circleID+"/post-placements/"+placementID+"/pin",
		map[string]any{"enabled": true},
		"placement-pin-noop", "persona-circle-owner", "PinCirclePost",
		"/circles/{circleId}/post-placements/{placementId}/pin")
	if replay.Code != http.StatusOK || decodeBody(t, replay)["idempotentReplay"] != true {
		t.Fatalf("pin no-op replay drift: %d %s", replay.Code, replay.Body.String())
	}
}
