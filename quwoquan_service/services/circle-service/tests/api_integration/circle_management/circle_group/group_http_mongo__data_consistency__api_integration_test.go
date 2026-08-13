// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#sit-001
// readiness_case: create-circle-group-api
// readiness_case: list-circle-groups-api
// readiness_case: search-circle-groups-api
// readiness_case: get-circle-group-api
// readiness_case: update-circle-group-api
// readiness_case: archive-circle-group-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_group/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
	membershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	membershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestCreateCircleGroupHTTPCommitsAggregateReceiptAndOutbox(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_group_object_api")
	ctx := context.Background()
	if _, err := database.Collection("circles").InsertOne(ctx, bson.M{
		"_id": "circle-group-object", "status": "active",
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_memberships").InsertOne(ctx, bson.M{
		"_id": "membership-group-owner", "circleId": "circle-group-object",
		"personaId": "persona-group-owner", "role": "owner", "state": "active",
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoReaders(database)
	handler := httpadapter.NewHandler(app.NewCommandFacade(store, readers), app.NewQueryFacade(readers, readers))
	request := testsupport.Request(t, http.MethodPost, "/circles/circle-group-object/groups", map[string]any{
		"groupType": "self_built", "name": "周末同行", "description": "同行协作",
		"visibility": "public", "joinPolicy": "apply_only",
		"storageEnabled": true, "noticeEnabled": true,
	}, "circle.circle_group.CreateCircleGroup", "persona-group-owner", "group-object-1")
	recorder := httptest.NewRecorder()
	handler.ServeCircleRoute(recorder, request, "circle-group-object", nil)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	created := decodeGroupResponse(t, recorder)
	groupID, _ := created["groupId"].(string)
	if groupID == "" {
		t.Fatalf("created CircleGroup lacks groupId: %#v", created)
	}
	testsupport.AssertCollectionCount(t, database, "circle_groups", 1)
	testsupport.AssertCollectionCount(t, database, "circle_group_command_receipts", 1)
	testsupport.AssertCollectionCount(t, database, "circle_group_outbox", 1)

	// 群主成员行由 CircleGroupCreated 事件经 owner projector 投影（生产链为
	// outbox relay 驱动）；Update/Archive 的 owner/manager 门禁依赖该行。
	membershipAggregateStore := membershippersistence.NewMongoAggregateStore(database)
	if err := membershipAggregateStore.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	membershipReaders := membershippersistence.NewMongoReaders(database)
	ownerProjector := membershipapp.NewCircleGroupOwnerProjector(
		membershipapp.NewCommandFacade(
			membershipAggregateStore, membershipReaders, membershipReaders, membershipReaders,
		),
	)
	outboxEvents, err := store.ReadAfter(ctx, "", 10)
	if err != nil {
		t.Fatal(err)
	}
	for _, event := range outboxEvents {
		if err := ownerProjector.Publish(ctx, event); err != nil {
			t.Fatalf("project CircleGroupCreated owner membership: %v", err)
		}
	}
	testsupport.AssertCollectionCount(t, database, "circle_group_memberships", 1)

	getRequest := testsupport.Request(t, http.MethodGet,
		"/circles/circle-group-object/groups/"+groupID, nil,
		"circle.circle_group.GetCircleGroup", "persona-group-owner", "group-get-1")
	getRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(getRecorder, getRequest, "circle-group-object", []string{groupID})
	if getRecorder.Code != http.StatusOK || decodeGroupResponse(t, getRecorder)["groupId"] != groupID {
		t.Fatalf("get status=%d body=%s", getRecorder.Code, getRecorder.Body.String())
	}

	listRequest := testsupport.Request(t, http.MethodGet,
		"/circles/circle-group-object/groups?limit=20", nil,
		"circle.circle_group.ListCircleGroups", "persona-group-owner", "group-list-1")
	listRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(listRecorder, listRequest, "circle-group-object", nil)
	if listRecorder.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listRecorder.Code, listRecorder.Body.String())
	}
	listItems, _ := decodeGroupResponse(t, listRecorder)["items"].([]any)
	if len(listItems) != 1 {
		t.Fatalf("list CircleGroups items=%#v", listItems)
	}

	searchRequest := testsupport.Request(t, http.MethodGet,
		"/circles/circle-group-object/groups/search?query=周末&limit=20", nil,
		"circle.circle_group.SearchCircleGroups", "persona-group-owner", "group-search-1")
	searchRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(searchRecorder, searchRequest, "circle-group-object", []string{"search"})
	if searchRecorder.Code != http.StatusOK {
		t.Fatalf("search status=%d body=%s", searchRecorder.Code, searchRecorder.Body.String())
	}
	searchItems, _ := decodeGroupResponse(t, searchRecorder)["items"].([]any)
	if len(searchItems) != 1 {
		t.Fatalf("search CircleGroups items=%#v", searchItems)
	}

	updateRequest := testsupport.Request(t, http.MethodPatch,
		"/circles/circle-group-object/groups/"+groupID,
		map[string]any{"name": "周末远足"},
		"circle.circle_group.UpdateCircleGroup", "persona-group-owner", "group-update-1")
	updateRequest.Header.Set("If-Match", "\"1\"")
	updateRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(updateRecorder, updateRequest, "circle-group-object", []string{groupID})
	if updateRecorder.Code != http.StatusOK || decodeGroupResponse(t, updateRecorder)["version"] != float64(2) {
		t.Fatalf("update status=%d body=%s", updateRecorder.Code, updateRecorder.Body.String())
	}

	archiveRequest := testsupport.Request(t, http.MethodDelete,
		"/circles/circle-group-object/groups/"+groupID, nil,
		"circle.circle_group.ArchiveCircleGroup", "persona-group-owner", "group-archive-1")
	archiveRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(archiveRecorder, archiveRequest, "circle-group-object", []string{groupID})
	if archiveRecorder.Code != http.StatusOK || decodeGroupResponse(t, archiveRecorder)["status"] != "archived" {
		t.Fatalf("archive status=%d body=%s", archiveRecorder.Code, archiveRecorder.Body.String())
	}
}

func decodeGroupResponse(t *testing.T, recorder *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var value map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode CircleGroup response: %v body=%s", err, recorder.Body.String())
	}
	return value
}
