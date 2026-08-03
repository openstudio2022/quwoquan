package api_integration_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	"quwoquan_service/runtime/commandmeta"
	mediaassetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	originalaccesshttp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/adapters/inbound/http"
	originalaccessapp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/application"
	originalaccesspersistence "quwoquan_service/services/content-service/internal/media/media_original_access_fact/infrastructure/persistence"
)

func TestHTTPAppendsOneMongoFactAndReplaysAbsoluteGrant(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "content_media_original_access_fact")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	database := runtime.Database
	store := originalaccesspersistence.NewMongoStore(database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure indexes: %v", err)
	}
	now := time.Date(2030, time.March, 4, 5, 6, 7, 0, time.UTC)
	service := originalaccessapp.NewService(
		store,
		fixedAssetReader{},
		visiblePostReader{},
		fixedURLSigner{},
		originalaccessapp.WithClock(func() time.Time { return now }),
	)
	handler := originalaccesshttp.NewHandler(service)

	first := executeRequest(t, handler)
	replayed := executeRequest(t, handler)
	if first.Code != http.StatusOK || replayed.Code != http.StatusOK {
		t.Fatalf("grant status first=%d replay=%d bodies=%s / %s", first.Code, replayed.Code, first.Body.String(), replayed.Body.String())
	}
	if first.Body.String() != replayed.Body.String() {
		t.Fatalf("idempotent replay changed response: %s / %s", first.Body.String(), replayed.Body.String())
	}
	count, err := database.Collection("media_original_access_facts").CountDocuments(context.Background(), bson.D{})
	if err != nil {
		t.Fatalf("count facts: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected one immutable fact after replay, got %d", count)
	}
	if !strings.Contains(first.Body.String(), fmt.Sprintf("\"expiresAt\":\"%s\"", now.Add(5*time.Minute).Format(time.RFC3339))) {
		t.Fatalf("response does not preserve canonical absolute expiry: %s", first.Body.String())
	}
}

func executeRequest(t *testing.T, handler *originalaccesshttp.Handler) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, "/content/media/media_image/original:access", strings.NewReader(`{"purpose":"save"}`))
	request.SetPathValue("mediaId", "media_image")
	ctx := commandmeta.WithIdempotencyKey(request.Context(), "original-access-once")
	ctx = rtauth.WithPrincipal(ctx, rtauth.Principal{
		Claims: rtauth.Claims{Subject: "account_1", Persona: "persona_owner"},
		Actor:  rtoperation.ActorContext{AccountID: "account_1", PersonaID: "persona_owner"},
	})
	request = request.WithContext(ctx)
	recorder := httptest.NewRecorder()
	handler.Request(recorder, request)
	return recorder
}

type fixedAssetReader struct{}

func (fixedAssetReader) FindOriginalAccessAsset(context.Context, string) (mediaassetports.OriginalAccessSlice, bool, error) {
	return mediaassetports.OriginalAccessSlice{
		AssetID: "media_image", OwnerID: "persona_owner", ObjectKey: "media/original/image.jpg",
		MediaType: "image", MimeType: "image/jpeg", FileSize: 512,
		ProcessingStatus: "ready", AccessPolicy: "owner_only",
	}, true, nil
}

type visiblePostReader struct{}

func (visiblePostReader) CanViewerAccessPublishedMedia(context.Context, string, string) (bool, error) {
	return true, nil
}

type fixedURLSigner struct{}

func (fixedURLSigner) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	return fmt.Sprintf("https://cdn.example.test/%s?expires=%d", objectKey, expiresAt.Unix()), nil
}
