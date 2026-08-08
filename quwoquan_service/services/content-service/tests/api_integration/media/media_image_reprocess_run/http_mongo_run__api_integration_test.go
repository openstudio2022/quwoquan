// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-004
// readiness_case: start-media-image-reprocess-run-api
// readiness_case: pause-media-image-reprocess-run-api
// readiness_case: resume-media-image-reprocess-run-api
// readiness_case: rollback-media-image-reprocess-run-api
// readiness_case: get-media-image-reprocess-run-api
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
	"quwoquan_service/runtime/commandmeta"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	reprocesshttp "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/adapters/inbound/http"
	reprocessapp "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/application"
	reprocesspersistence "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/infrastructure/persistence"
)

func TestHTTPStartAndGetUseObjectOwnedMongoTransaction(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "media_image_reprocess_run_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	store := reprocesspersistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure indexes: %v", err)
	}
	asset := readyImageAsset(t)
	handler := reprocesshttp.NewHandler(reprocessapp.NewService(store, fixedImageReader{asset: asset}))

	startRequest := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/media-image-reprocess-runs",
		strings.NewReader(`{"runId":"image-reprocess-run","assetIds":["media-image"]}`),
	)
	startRequest = startRequest.WithContext(commandmeta.WithIdempotencyKey(startRequest.Context(), "start-image-reprocess-once"))
	startRecorder := httptest.NewRecorder()
	handler.Start(startRecorder, startRequest)
	if startRecorder.Code != http.StatusAccepted {
		t.Fatalf("start status=%d body=%s", startRecorder.Code, startRecorder.Body.String())
	}
	conflictingStartRequest := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/media-image-reprocess-runs",
		strings.NewReader(`{"runId":"different-image-reprocess-run","assetIds":["media-image"]}`),
	)
	conflictingStartRequest = conflictingStartRequest.WithContext(commandmeta.WithIdempotencyKey(
		conflictingStartRequest.Context(),
		"start-image-reprocess-once",
	))
	conflictingStartRecorder := httptest.NewRecorder()
	handler.Start(conflictingStartRecorder, conflictingStartRequest)
	if conflictingStartRecorder.Code != http.StatusConflict ||
		!strings.Contains(
			conflictingStartRecorder.Body.String(),
			`"code":"CONTENT.USER.media_image_reprocess_version_conflict"`,
		) {
		t.Fatalf(
			"conflicting start status=%d body=%s",
			conflictingStartRecorder.Code,
			conflictingStartRecorder.Body.String(),
		)
	}

	getRequest := httptest.NewRequest(http.MethodGet, "/internal/content/media-image-reprocess-runs/image-reprocess-run", nil)
	getRequest.SetPathValue("runId", "image-reprocess-run")
	getRecorder := httptest.NewRecorder()
	handler.Get(getRecorder, getRequest)
	if getRecorder.Code != http.StatusOK || !strings.Contains(getRecorder.Body.String(), `"status":"running"`) {
		t.Fatalf("get status=%d body=%s", getRecorder.Code, getRecorder.Body.String())
	}

	transition := func(
		name string,
		key string,
		invoke func(http.ResponseWriter, *http.Request),
		wantStatus string,
	) {
		t.Helper()
		request := httptest.NewRequest(
			http.MethodPost,
			"/internal/content/media-image-reprocess-runs/image-reprocess-run:"+name,
			nil,
		)
		request.SetPathValue("runId", "image-reprocess-run")
		request = request.WithContext(commandmeta.WithIdempotencyKey(request.Context(), key))
		recorder := httptest.NewRecorder()
		invoke(recorder, request)
		if recorder.Code != http.StatusAccepted ||
			!strings.Contains(recorder.Body.String(), `"status":"`+wantStatus+`"`) {
			t.Fatalf("%s status=%d body=%s", name, recorder.Code, recorder.Body.String())
		}
	}
	transition("pause", "pause-image-reprocess-once", handler.Pause, "paused")
	transition("resume", "resume-image-reprocess-once", handler.Resume, "running")
	transition("pause", "pause-image-reprocess-for-rollback", handler.Pause, "paused")
	transition("rollback", "rollback-image-reprocess-once", handler.Rollback, "rolling_back")

	finalGetRequest := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/media-image-reprocess-runs/image-reprocess-run",
		nil,
	)
	finalGetRequest.SetPathValue("runId", "image-reprocess-run")
	finalGetRecorder := httptest.NewRecorder()
	handler.Get(finalGetRecorder, finalGetRequest)
	if finalGetRecorder.Code != http.StatusOK ||
		!strings.Contains(finalGetRecorder.Body.String(), `"status":"rolling_back"`) ||
		!strings.Contains(finalGetRecorder.Body.String(), `"version":5`) {
		t.Fatalf("final get status=%d body=%s", finalGetRecorder.Code, finalGetRecorder.Body.String())
	}

	runs, err := runtime.Database.Collection("media_image_reprocess_runs").CountDocuments(context.Background(), bson.D{})
	if err != nil || runs != 1 {
		t.Fatalf("run count=%d err=%v", runs, err)
	}
	receipts, err := runtime.Database.Collection("media_image_reprocess_run_receipts").CountDocuments(context.Background(), bson.D{})
	if err != nil || receipts != 5 {
		t.Fatalf("receipt count=%d err=%v", receipts, err)
	}
}

type fixedImageReader struct{ asset *mediamodel.MediaAsset }

func (reader fixedImageReader) LoadMediaAsset(context.Context, string) (*mediamodel.MediaAsset, bool, error) {
	asset, err := mediamodel.RestoreMediaAsset(reader.asset.Snapshot())
	return asset, err == nil, err
}

func readyImageAsset(t *testing.T) *mediamodel.MediaAsset {
	t.Helper()
	now := time.Date(2030, time.April, 5, 6, 7, 8, 0, time.UTC)
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID: "media-image", OwnerID: "persona-owner", SourceSessionID: "upload-image",
		ObjectKey: "media/original/image.jpg",
		SHA256:    "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
		MediaType: "image", MimeType: "image/jpeg", FileSize: 512,
		AccessPolicy: mediamodel.AccessPolicyOwnerOnly, ProcessingRequired: true, Now: now,
	})
	if err != nil {
		t.Fatalf("create image asset: %v", err)
	}
	publicPrefix := fmt.Sprintf("media/image/s/asset/%s/v%d", asset.ID(), asset.Version()+1)
	err = asset.RecordProcessingResult(mediamodel.ProcessingStatusReady, "", mediamodel.MediaProcessingDescriptor{
		Image: mediamodel.ImageProcessingDescriptor{
			ProcessorProfile: "content_processing_image_baseline", ImageWidth: 1080, ImageHeight: 1440,
			ImageDeliveryMimeType: "image/jpeg", ImageNormalizedObjectKey: "media/processed/image/source.jpg",
			ImagePublicSliceKey: publicPrefix + "/source.jpg", ImageDominantColor: "#1A2B3C",
			ImageLQIP: "data:image/jpeg;base64,/9j/2Q==", ImageContentProfile: "photographic",
			DerivativePolicyVersion: 1,
		},
	}, now.Add(time.Second))
	if err != nil {
		t.Fatalf("mark image ready: %v", err)
	}
	return asset
}
