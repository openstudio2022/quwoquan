// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-007
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-007.t1
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-007.t2
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-007.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-007.t4
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-007.t5
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-007.t6
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-008
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-008.t1
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-008.t2
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-008.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-008.t4
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-008.t5
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-009
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-009.t1
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-009.t2
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-009.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-009.t4
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-009.t5
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-009.t6
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-010
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-010.t1
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-010.t2
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-010.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-010.t4
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-010.t5
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-010.t6
// readiness_case: place-post-in-circle-api
// readiness_case: remove-post-from-circle-api
// readiness_case: pin-circle-post-api
// readiness_case: feature-circle-post-api
//
// CirclePostPlacement owner 合同证据：Place/Remove/Pin/Feature 四命令各证明
// owner readback 收敛（单次 state/receipt/outbox）、幂等重放、同键冲突输入的
// canonical idempotency failure 与 BOLA/identity 失败原子性。owner readback 经
// 真实 Mongo owner 集合断言（不以 feed/discovery 投影替代）。
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/application"
	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

const (
	placementContractCircleID = "circle-placement-contract"
	placementContractOwner    = "persona-plc-owner"
	placementContractOutsider = "persona-plc-outsider"
)

type placementContractHarness struct {
	database *mongo.Database
	handler  *httpadapter.Handler
}

func newPlacementContractHarness(t *testing.T, databaseName string) placementContractHarness {
	t.Helper()
	database := testsupport.StartRealMongo(t, databaseName)
	ctx := context.Background()
	if _, err := database.Collection("circles").InsertOne(ctx, bson.M{
		"_id": placementContractCircleID, "ownerId": placementContractOwner, "status": "active",
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_post_owner_views").InsertMany(ctx, []any{
		bson.M{
			"_id": "post-plc-a", "ownerPersonaId": placementContractOwner, "state": "published",
		},
		bson.M{
			"_id": "post-plc-b", "ownerPersonaId": placementContractOwner, "state": "published",
		},
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoPolicyReaders(database)
	if err := readers.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	return placementContractHarness{
		database: database,
		handler: httpadapter.NewHandler(app.NewCommandFacade(store, ports.PolicyReaders{
			Circles: readers, Groups: readers, Posts: readers, Memberships: readers,
		})),
	}
}

func (h placementContractHarness) serve(
	t *testing.T,
	method, path string,
	body map[string]any,
	operationID, personaID, idempotencyKey string,
	tail []string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := testsupport.Request(t, method, path, body, operationID, personaID, idempotencyKey)
	recorder := httptest.NewRecorder()
	h.handler.ServeCircleRoute(recorder, request, placementContractCircleID, tail)
	return recorder
}

func (h placementContractHarness) count(t *testing.T, collection string) int64 {
	t.Helper()
	count, err := h.database.Collection(collection).CountDocuments(context.Background(), bson.M{})
	if err != nil {
		t.Fatal(err)
	}
	return count
}

// ownerReadback 经真实 owner 集合读回 placement 事实（不以 feed 投影替代）。
func (h placementContractHarness) ownerReadback(t *testing.T, placementID string) bson.M {
	t.Helper()
	var document bson.M
	if err := h.database.Collection("circle_post_placements").
		FindOne(context.Background(), bson.M{"_id": placementID}).
		Decode(&document); err != nil {
		t.Fatalf("owner readback for placement %s: %v", placementID, err)
	}
	return document
}

func (h placementContractHarness) place(t *testing.T, personaID, postID, key string) *httptest.ResponseRecorder {
	t.Helper()
	return h.serve(t, http.MethodPost,
		"/circles/"+placementContractCircleID+"/post-placements",
		map[string]any{"postId": postID},
		"circle.circle_post_placement.PlacePostInCircle", personaID, key, nil)
}

func (h placementContractHarness) toggle(
	t *testing.T, personaID, placementID, action string, enabled bool, key string,
) *httptest.ResponseRecorder {
	t.Helper()
	return h.serve(t, http.MethodPatch,
		"/circles/"+placementContractCircleID+"/post-placements/"+placementID+"/"+action,
		map[string]any{"enabled": enabled},
		"circle.circle_post_placement."+action, personaID, key,
		[]string{placementID, action})
}

func (h placementContractHarness) remove(t *testing.T, personaID, placementID, key string) *httptest.ResponseRecorder {
	t.Helper()
	return h.serve(t, http.MethodDelete,
		"/circles/"+placementContractCircleID+"/post-placements/"+placementID, nil,
		"circle.circle_post_placement.RemovePostFromCircle", personaID, key,
		[]string{placementID})
}

func decodePlacementResponse(t *testing.T, recorder *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var value map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode CirclePostPlacement response: %v body=%s", err, recorder.Body.String())
	}
	return value
}

func TestPlaceCirclePostPlacementOwnerContract(t *testing.T) {
	h := newPlacementContractHarness(t, "circle_post_placement_owner_place")
	receiptsBefore := h.count(t, "circle_post_placement_command_receipts")
	outboxBefore := h.count(t, "circle_post_placement_outbox")

	// t5+t6：BOLA——非 Post owner 放置返回 typed failure，无部分成功。
	denied := h.place(t, placementContractOutsider, "post-plc-a", "plc-place-denied")
	deniedBody := decodePlacementResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] == nil {
		t.Fatalf("non-owner place must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	if h.count(t, "circle_post_placements") != 0 ||
		h.count(t, "circle_post_placement_command_receipts") != receiptsBefore ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore {
		t.Fatal("failed place must not partially commit state, receipt or outbox")
	}

	// t1+t2：一次放置成功，owner readback 收敛 active，且只提交一次。
	placed := h.place(t, placementContractOwner, "post-plc-a", "plc-place-1")
	placedBody := decodePlacementResponse(t, placed)
	placementID, _ := placedBody["placementId"].(string)
	if placed.Code != http.StatusCreated || placementID == "" || placedBody["state"] != "active" {
		t.Fatalf("place status=%d body=%#v", placed.Code, placedBody)
	}
	readback := h.ownerReadback(t, placementID)
	if readback["state"] != "active" || readback["circleId"] != placementContractCircleID ||
		readback["postId"] != "post-plc-a" {
		t.Fatalf("owner readback must converge with receipt: %#v", readback)
	}
	if h.count(t, "circle_post_placements") != 1 ||
		h.count(t, "circle_post_placement_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore+1 {
		t.Fatal("place must commit exactly one state, receipt and outbox event")
	}

	// t3：相同幂等键重放返回同一 placement，不推进。
	replay := h.place(t, placementContractOwner, "post-plc-a", "plc-place-1")
	replayBody := decodePlacementResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["placementId"] != placementID ||
		replayBody["version"] != placedBody["version"] {
		t.Fatalf("place replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_post_placements") != 1 ||
		h.count(t, "circle_post_placement_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore+1 {
		t.Fatal("place replay must not create a second placement, receipt or outbox event")
	}

	// t4：同键冲突输入返回 canonical idempotency failure。
	conflict := h.place(t, placementContractOwner, "post-plc-b", "plc-place-1")
	conflictBody := decodePlacementResponse(t, conflict)
	if conflict.Code < http.StatusBadRequest ||
		conflictBody["code"] != "CIRCLE.USER.placement_idempotency_conflict" {
		t.Fatalf(
			"conflicting reuse of the idempotency key must fail typed: status=%d body=%#v",
			conflict.Code, conflictBody,
		)
	}
}

func TestPinCirclePostPlacementOwnerContract(t *testing.T) {
	h := newPlacementContractHarness(t, "circle_post_placement_owner_pin")
	placed := decodePlacementResponse(
		t, h.place(t, placementContractOwner, "post-plc-a", "plc-pin-seed"),
	)
	placementID, _ := placed["placementId"].(string)
	if placementID == "" {
		t.Fatalf("seed place body=%#v", placed)
	}
	receiptsBefore := h.count(t, "circle_post_placement_command_receipts")
	outboxBefore := h.count(t, "circle_post_placement_outbox")

	// t5+t6：BOLA——非 owner 置顶返回 typed failure，无部分成功。
	denied := h.toggle(t, placementContractOutsider, placementID, "pin", true, "plc-pin-denied")
	deniedBody := decodePlacementResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] == nil {
		t.Fatalf("non-owner pin must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	if h.count(t, "circle_post_placement_command_receipts") != receiptsBefore ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore {
		t.Fatal("failed pin must not commit receipt or outbox")
	}

	// t1+t2：owner 置顶一次成功，owner readback 收敛 pinned 与新 version。
	pinned := decodePlacementResponse(
		t, h.toggle(t, placementContractOwner, placementID, "pin", true, "plc-pin-1"),
	)
	readback := h.ownerReadback(t, placementID)
	if pinned["version"] == placed["version"] || readback["pinned"] != true {
		t.Fatalf("pin must converge on owner readback: body=%#v readback=%#v", pinned, readback)
	}
	if h.count(t, "circle_post_placement_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore+1 {
		t.Fatal("pin must commit exactly one receipt and one outbox event")
	}

	// t3：相同幂等键重放不重复推进。
	replay := decodePlacementResponse(
		t, h.toggle(t, placementContractOwner, placementID, "pin", true, "plc-pin-1"),
	)
	if replay["version"] != pinned["version"] {
		t.Fatalf("pin replay must be idempotent: %#v vs %#v", replay, pinned)
	}
	if h.count(t, "circle_post_placement_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore+1 {
		t.Fatal("pin replay must not append receipts or outbox events")
	}

	// t4：同键不同 enabled 语义返回 canonical idempotency failure。
	conflict := h.toggle(t, placementContractOwner, placementID, "pin", false, "plc-pin-1")
	conflictBody := decodePlacementResponse(t, conflict)
	if conflict.Code < http.StatusBadRequest ||
		conflictBody["code"] != "CIRCLE.USER.placement_idempotency_conflict" {
		t.Fatalf(
			"conflicting pin semantics on the same key must fail typed: status=%d body=%#v",
			conflict.Code, conflictBody,
		)
	}
}

func TestFeatureCirclePostPlacementOwnerContract(t *testing.T) {
	h := newPlacementContractHarness(t, "circle_post_placement_owner_feature")
	placed := decodePlacementResponse(
		t, h.place(t, placementContractOwner, "post-plc-a", "plc-feature-seed"),
	)
	placementID, _ := placed["placementId"].(string)
	if placementID == "" {
		t.Fatalf("seed place body=%#v", placed)
	}
	receiptsBefore := h.count(t, "circle_post_placement_command_receipts")
	outboxBefore := h.count(t, "circle_post_placement_outbox")

	// t5+t6：BOLA 失败原子性。
	denied := h.toggle(t, placementContractOutsider, placementID, "feature", true, "plc-feature-denied")
	deniedBody := decodePlacementResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] == nil {
		t.Fatalf("non-owner feature must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	if h.count(t, "circle_post_placement_command_receipts") != receiptsBefore ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore {
		t.Fatal("failed feature must not commit receipt or outbox")
	}

	// t1+t2：owner 精选一次成功，owner readback 收敛 featured 与新 version。
	featured := decodePlacementResponse(
		t, h.toggle(t, placementContractOwner, placementID, "feature", true, "plc-feature-1"),
	)
	readback := h.ownerReadback(t, placementID)
	if featured["version"] == placed["version"] || readback["featured"] != true {
		t.Fatalf("feature must converge on owner readback: body=%#v readback=%#v", featured, readback)
	}
	if h.count(t, "circle_post_placement_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore+1 {
		t.Fatal("feature must commit exactly one receipt and one outbox event")
	}

	// t3：幂等重放不重复推进。
	replay := decodePlacementResponse(
		t, h.toggle(t, placementContractOwner, placementID, "feature", true, "plc-feature-1"),
	)
	if replay["version"] != featured["version"] {
		t.Fatalf("feature replay must be idempotent: %#v vs %#v", replay, featured)
	}

	// t4：同键不同 enabled 语义返回 canonical idempotency failure。
	conflict := h.toggle(t, placementContractOwner, placementID, "feature", false, "plc-feature-1")
	conflictBody := decodePlacementResponse(t, conflict)
	if conflict.Code < http.StatusBadRequest ||
		conflictBody["code"] != "CIRCLE.USER.placement_idempotency_conflict" {
		t.Fatalf(
			"conflicting feature semantics on the same key must fail typed: status=%d body=%#v",
			conflict.Code, conflictBody,
		)
	}
}

func TestRemoveCirclePostPlacementOwnerContract(t *testing.T) {
	h := newPlacementContractHarness(t, "circle_post_placement_owner_remove")
	placed := decodePlacementResponse(
		t, h.place(t, placementContractOwner, "post-plc-a", "plc-remove-seed"),
	)
	placementID, _ := placed["placementId"].(string)
	if placementID == "" {
		t.Fatalf("seed place body=%#v", placed)
	}
	receiptsBefore := h.count(t, "circle_post_placement_command_receipts")
	outboxBefore := h.count(t, "circle_post_placement_outbox")

	// t5+t6：BOLA 与 placement 不存在均返回 typed failure，无部分变化。
	denied := h.remove(t, placementContractOutsider, placementID, "plc-remove-denied")
	deniedBody := decodePlacementResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] == nil {
		t.Fatalf("non-owner removal must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	missing := h.remove(t, placementContractOwner, "placement-plc-missing", "plc-remove-missing")
	missingBody := decodePlacementResponse(t, missing)
	if missing.Code < http.StatusBadRequest ||
		missingBody["code"] != "CIRCLE.USER.placement_not_found" {
		t.Fatalf("missing placement removal must fail typed: status=%d body=%#v", missing.Code, missingBody)
	}
	if h.count(t, "circle_post_placement_command_receipts") != receiptsBefore ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore {
		t.Fatal("failed removals must not commit receipt or outbox")
	}

	// t1+t2：owner 移除一次成功，owner readback 收敛 removed 与推进后的 version。
	removed := decodePlacementResponse(
		t, h.remove(t, placementContractOwner, placementID, "plc-remove-1"),
	)
	readback := h.ownerReadback(t, placementID)
	if removed["state"] != "removed" || readback["state"] != "removed" {
		t.Fatalf("remove must converge on owner readback: body=%#v readback=%#v", removed, readback)
	}
	if h.count(t, "circle_post_placement_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore+1 {
		t.Fatal("remove must commit exactly one receipt and one outbox event")
	}

	// t3：幂等重放返回同一 receipt 身份，不重复移除。
	replay := decodePlacementResponse(
		t, h.remove(t, placementContractOwner, placementID, "plc-remove-1"),
	)
	if replay["placementId"] != placementID || replay["version"] != removed["version"] {
		t.Fatalf("remove replay must be idempotent: %#v vs %#v", replay, removed)
	}
	if h.count(t, "circle_post_placement_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_post_placement_outbox") != outboxBefore+1 {
		t.Fatal("remove replay must not append receipts or outbox events")
	}
}
