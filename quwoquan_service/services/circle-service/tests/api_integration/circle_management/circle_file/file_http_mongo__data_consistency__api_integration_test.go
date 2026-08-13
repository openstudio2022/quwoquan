// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#sit-001
// readiness_case: list-circle-files-api
// readiness_case: create-circle-file-api
// readiness_case: get-circle-file-api
// readiness_case: update-circle-file-api
// readiness_case: delete-circle-file-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_file/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_file/application"
	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/ports"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

type mediaAssetReader struct{}

func (mediaAssetReader) ReadOwnedReadyAsset(context.Context, string, string) (ports.MediaAssetOwnerSlice, bool, error) {
	return ports.MediaAssetOwnerSlice{}, false, nil
}

func TestCreateCircleFileHTTPCommitsAggregateReceiptAndOutbox(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_file_object_api")
	ctx := context.Background()
	if _, err := database.Collection("circles").InsertOne(ctx, bson.M{
		"_id": "circle-file-object", "status": "active", "storageQuotaBytes": int64(1 << 20),
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_memberships").InsertOne(ctx, bson.M{
		"_id": "membership-file-owner", "circleId": "circle-file-object",
		"personaId": "persona-file-owner", "role": "owner", "state": "active",
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoReaders(database)
	handler := httpadapter.NewHandler(
		app.NewCommandFacade(store, readers, mediaAssetReader{}),
		app.NewQueryFacade(readers, readers),
	)
	request := testsupport.Request(t, http.MethodPost, "/circles/circle-file-object/files", map[string]any{
		"name": "行程资料", "fileType": "folder",
	}, "circle.circle_file.CreateCircleFile", "persona-file-owner", "file-object-1")
	recorder := httptest.NewRecorder()
	handler.ServeCircleRoute(recorder, request, "circle-file-object", nil)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var created app.CommandResult
	if err := json.NewDecoder(recorder.Body).Decode(&created); err != nil {
		t.Fatal(err)
	}
	if created.FileID == "" || created.Version != 1 || created.Status != "active" {
		t.Fatalf("create result=%+v", created)
	}

	listRequest := testsupport.Request(
		t, http.MethodGet, "/circles/circle-file-object/files?limit=20", nil,
		"circle.circle_file.ListCircleFiles", "persona-file-owner", "file-object-list",
	)
	listRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(listRecorder, listRequest, "circle-file-object", nil)
	if listRecorder.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listRecorder.Code, listRecorder.Body.String())
	}
	var page app.PageResult
	if err := json.NewDecoder(listRecorder.Body).Decode(&page); err != nil {
		t.Fatal(err)
	}
	if len(page.Items) != 1 || page.Items[0].FileID != created.FileID {
		t.Fatalf("list result=%+v", page)
	}

	getRequest := testsupport.Request(
		t, http.MethodGet, "/circles/circle-file-object/files/"+created.FileID, nil,
		"circle.circle_file.GetCircleFile", "persona-file-owner", "file-object-get",
	)
	getRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(getRecorder, getRequest, "circle-file-object", []string{created.FileID})
	if getRecorder.Code != http.StatusOK {
		t.Fatalf("get status=%d body=%s", getRecorder.Code, getRecorder.Body.String())
	}
	var got app.FileSlice
	if err := json.NewDecoder(getRecorder.Body).Decode(&got); err != nil {
		t.Fatal(err)
	}
	if got.FileID != created.FileID || got.Name != "行程资料" {
		t.Fatalf("get result=%+v", got)
	}

	updateRequest := testsupport.Request(
		t, http.MethodPatch, "/circles/circle-file-object/files/"+created.FileID,
		map[string]any{"name": "行程资料库"},
		"circle.circle_file.UpdateCircleFile", "persona-file-owner", "file-object-update",
	)
	updateRequest.Header.Set("If-Match", `"1"`)
	updateRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(updateRecorder, updateRequest, "circle-file-object", []string{created.FileID})
	if updateRecorder.Code != http.StatusOK {
		t.Fatalf("update status=%d body=%s", updateRecorder.Code, updateRecorder.Body.String())
	}
	var updated app.CommandResult
	if err := json.NewDecoder(updateRecorder.Body).Decode(&updated); err != nil {
		t.Fatal(err)
	}
	if updated.Version != 2 || updated.Status != "active" {
		t.Fatalf("update result=%+v", updated)
	}

	deleteRequest := testsupport.Request(
		t, http.MethodDelete, "/circles/circle-file-object/files/"+created.FileID, nil,
		"circle.circle_file.DeleteCircleFile", "persona-file-owner", "file-object-delete",
	)
	deleteRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(deleteRecorder, deleteRequest, "circle-file-object", []string{created.FileID})
	if deleteRecorder.Code != http.StatusOK {
		t.Fatalf("delete status=%d body=%s", deleteRecorder.Code, deleteRecorder.Body.String())
	}
	var deleted app.CommandResult
	if err := json.NewDecoder(deleteRecorder.Body).Decode(&deleted); err != nil {
		t.Fatal(err)
	}
	if deleted.Version != 3 || deleted.Status != "deleted" {
		t.Fatalf("delete result=%+v", deleted)
	}
	var stored struct {
		Version int64  `bson:"version"`
		Name    string `bson:"name"`
		Status  string `bson:"status"`
	}
	if err := database.Collection("circle_files").FindOne(
		ctx, bson.M{"_id": created.FileID},
	).Decode(&stored); err != nil {
		t.Fatal(err)
	}
	if stored.Version != 3 || stored.Name != "行程资料库" || stored.Status != "deleted" {
		t.Fatalf("stored file=%+v", stored)
	}
	testsupport.AssertCollectionCount(t, database, "circle_files", 1)
	testsupport.AssertCollectionCount(t, database, "circle_files_command_receipts", 3)
	testsupport.AssertCollectionCount(t, database, "circle_files_outbox", 3)
}
