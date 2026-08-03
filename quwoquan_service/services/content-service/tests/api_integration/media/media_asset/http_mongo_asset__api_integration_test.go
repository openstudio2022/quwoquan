package api_integration_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	mediahttp "quwoquan_service/services/content-service/internal/media/media_asset/adapters/inbound/http"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	mediaassetpersistence "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/persistence"
)

func TestPublicHTTPReadsObjectOwnedMongoAggregate(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "media_asset_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	store := mediaassetpersistence.NewMongoMediaStore(runtime.Database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure MediaAsset indexes: %v", err)
	}
	now := time.Date(2030, time.May, 6, 7, 8, 9, 0, time.UTC)
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID: "media-public-file", OwnerID: "persona-owner", SourceSessionID: "upload-public-file",
		ObjectKey: "media/original/public.pdf",
		SHA256:    "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
		MediaType: mediamodel.MediaTypeFile, MimeType: "application/pdf", FileSize: 2048,
		AccessPolicy: mediamodel.AccessPolicyPublic, ProcessingRequired: false, Now: now,
	})
	if err != nil {
		t.Fatalf("create MediaAsset: %v", err)
	}
	if _, err := store.CommitMediaAsset(context.Background(), mediaports.MediaAssetCommit{
		Aggregate: asset, ExpectedVersion: 0, IdempotencyKey: "create-media-public-file",
		CommandName: "CompleteMediaUpload", CommandDigest: "digest-create-media-public-file",
		ReceiptExpiresAt: now.Add(24 * time.Hour), Events: []mediaports.OutboxEvent{{
			EventID: "event-media-public-file", EventType: "content.media_asset.created",
			AggregateType: "MediaAsset", AggregateID: asset.ID(), AggregateVersion: asset.Version(),
			Payload: []byte(`{}`), OccurredAt: now,
		}},
	}); err != nil {
		t.Fatalf("commit MediaAsset: %v", err)
	}
	handler := mediahttp.NewHandler(mediaapp.BindFacades(mediaapp.NewMediaService(
		mediaapp.BindDataPorts(store), fixedGateway{},
	)))
	request := httptest.NewRequest(http.MethodGet, "/content/media/media-public-file", nil)
	request.SetPathValue("mediaId", "media-public-file")
	recorder := httptest.NewRecorder()
	handler.GetPublic(recorder, request)
	if recorder.Code != http.StatusOK ||
		!strings.Contains(recorder.Body.String(), `"assetId":"media-public-file"`) ||
		!strings.Contains(recorder.Body.String(), `"accessPolicy":"public"`) {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	count, err := runtime.Database.Collection("media_assets").CountDocuments(context.Background(), bson.D{})
	if err != nil || count != 1 {
		t.Fatalf("media_assets count=%d err=%v", count, err)
	}
}

type fixedGateway struct{}

func (fixedGateway) PublishPublicSlice(context.Context, string, string) error { return nil }

func (fixedGateway) DeliveryURL(_ context.Context, objectKey string) (string, error) {
	return "https://cdn.example.test/" + objectKey, nil
}

func (fixedGateway) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	return "https://cdn.example.test/" + objectKey, nil
}
