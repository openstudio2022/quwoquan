// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
package api_integration

import (
	"context"
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
	testsupport.AssertCollectionCount(t, database, "circle_files", 1)
	testsupport.AssertCollectionCount(t, database, "circle_files_command_receipts", 1)
	testsupport.AssertCollectionCount(t, database, "circle_files_outbox", 1)
}
