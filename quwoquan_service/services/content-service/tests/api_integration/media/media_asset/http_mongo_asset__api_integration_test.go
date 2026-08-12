// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/media-status-pipeline/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001
// readiness_case: process-media-outbox-api
// readiness_case: record-media-processing-result-api
// readiness_case: update-media-asset-access-policy-api
// readiness_case: get-owned-media-asset-api
// readiness_case: get-media-asset-reference-api
// readiness_case: get-media-asset-delivery-reference-api
// readiness_case: get-media-asset-api
// readiness_case: discard-media-asset-api
// readiness_case: select-auto-video-cover-api
// readiness_case: select-manual-video-cover-api
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
	"quwoquan_service/runtime/commandmeta"
	"quwoquan_service/runtime/operation"
	mediahttp "quwoquan_service/services/content-service/internal/media/media_asset/adapters/inbound/http"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediaprocessing "quwoquan_service/services/content-service/internal/media/media_asset/application/processing"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	mediaassetpersistence "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/persistence"
)

func TestMediaAssetHTTPCommandsAndQueriesPersistThroughCanonicalMongoAdapter(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "media_asset_operations_http")
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
	now := time.Date(2030, time.October, 11, 12, 13, 14, 0, time.UTC)
	sequence := 0
	service := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(store),
		fixedGateway{},
		mediaapp.WithClock(func() time.Time { return now }),
		mediaapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			sequence++
			return fmt.Sprintf("%s-media-http-%d", prefix, sequence), nil
		}),
	)
	handler := mediahttp.NewHandler(mediaapp.BindFacades(service))
	const ownerID = "persona-media-http"
	owner := rtauth.Principal{
		Claims: rtauth.Claims{Subject: "account-media-http", Persona: ownerID},
		Actor:  operation.ActorContext{AccountID: "account-media-http", PersonaID: ownerID},
	}

	fileAsset := seedMongoMediaAsset(
		t, store, now, "media-http-file", ownerID,
		mediamodel.MediaTypeFile, "application/pdf", mediamodel.AccessPolicyPublic, false,
	)
	public := executeMediaAssetHTTP(
		t, handler.GetPublic, http.MethodGet, fileAsset.ID(), "", "", rtauth.Principal{},
	)
	assertMediaHTTPResponse(t, public, http.StatusOK, `"assetId":"media-http-file"`, `"accessPolicy":"public"`)

	owned := executeMediaAssetHTTP(
		t, handler.GetOwned, http.MethodGet, fileAsset.ID(), "", "", owner,
	)
	assertMediaHTTPResponse(t, owned, http.StatusOK, `"assetId":"media-http-file"`)

	reference := executeMediaAssetHTTP(
		t,
		handler.GetReference,
		http.MethodGet,
		fileAsset.ID(),
		"?ownerPersonaId="+ownerID,
		"",
		rtauth.Principal{},
	)
	assertMediaHTTPResponse(t, reference, http.StatusOK, `"assetId":"media-http-file"`, `"ownerPersonaId":"`+ownerID+`"`)

	delivery := executeMediaAssetHTTP(
		t,
		handler.GetDeliveryReference,
		http.MethodGet,
		fileAsset.ID(),
		"?ownerPersonaId="+ownerID,
		"",
		rtauth.Principal{},
	)
	assertMediaHTTPResponse(t, delivery, http.StatusOK, `"assetId":"media-http-file"`, `"publicSliceKey":`, `"cdnUrl":`)

	updated := executeMediaAssetHTTP(
		t,
		handler.UpdateAccessPolicy,
		http.MethodPatch,
		fileAsset.ID(),
		"",
		`{"accessPolicy":"owner_only"}`,
		owner,
		"update-media-http-policy",
	)
	assertMediaHTTPResponse(t, updated, http.StatusOK, `"accessPolicy":"owner_only"`)

	discarded := executeMediaAssetHTTP(
		t, handler.Discard, http.MethodDelete, fileAsset.ID(), "", "", owner, "discard-media-http",
	)
	assertMediaHTTPResponse(t, discarded, http.StatusOK, `"mediaId":"media-http-file"`, `"status":"deleted"`)

	videoAsset := seedMongoMediaAsset(
		t, store, now, "media-http-video", ownerID,
		mediamodel.MediaTypeVideo, "video/mp4", mediamodel.AccessPolicyOwnerOnly, true,
	)
	videoPrefix := "media/video/s/asset/" + videoAsset.ID() + "/v2"
	processed := executeMediaAssetHTTP(
		t,
		handler.RecordProcessingResult,
		http.MethodPost,
		videoAsset.ID(),
		"",
		fmt.Sprintf(`{
            "processingStatus":"ready",
            "processorProfile":"media_canary_progressive_mp4",
            "verifiedDurationMs":125000,
            "videoWidth":540,
            "videoHeight":960,
            "videoCodec":"h264",
            "videoContainer":"mp4",
            "videoAudioCodec":"aac",
            "videoKeyframeIntervalMs":2000,
            "videoFastStart":true,
            "videoPublicSliceKey":%q,
            "coverPublicSliceKey":%q,
            "previewTrackVersion":1,
            "previewTrackManifestSliceKey":%q
        }`, videoPrefix+"/source.mp4", videoPrefix+"/cover.webp", videoPrefix+"/preview/manifest.json"),
		rtauth.Principal{},
		"record-media-http-processing",
	)
	assertMediaHTTPResponse(t, processed, http.StatusOK, `"processingStatus":"ready"`)

	auto := executeMediaAssetHTTP(
		t, handler.SelectAutoCover, http.MethodPost, videoAsset.ID(), "", "", owner, "auto-media-http-cover",
	)
	assertMediaHTTPResponse(t, auto, http.StatusOK, `"coverStrategy":"first_frame"`)

	manual := executeMediaAssetHTTP(
		t,
		handler.SelectManualCover,
		http.MethodPost,
		videoAsset.ID(),
		"",
		`{"coverFrameTimeMs":1250}`,
		owner,
		"manual-media-http-cover",
	)
	assertMediaHTTPResponse(t, manual, http.StatusOK, `"coverStrategy":"manual"`, `"coverFrameTimeMs":1250`)

	persisted, found, err := store.LoadMediaAsset(context.Background(), videoAsset.ID())
	if err != nil || !found || persisted.ProcessingStatus() != mediamodel.ProcessingStatusReady ||
		persisted.CoverStrategy() != string(mediamodel.CoverStrategyManual) {
		t.Fatalf("persisted video state: found=%v asset=%+v err=%v", found, persisted, err)
	}
}

func seedMongoMediaAsset(
	t *testing.T,
	store *mediaassetpersistence.MongoMediaStore,
	now time.Time,
	assetID string,
	ownerID string,
	mediaType mediamodel.MediaType,
	mimeType string,
	accessPolicy mediamodel.AccessPolicy,
	processingRequired bool,
) *mediamodel.MediaAsset {
	t.Helper()
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID: assetID, OwnerID: ownerID, SourceSessionID: "upload-" + assetID,
		ObjectKey: "media/original/" + assetID,
		SHA256:    "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
		MediaType: mediaType, MimeType: mimeType, FileSize: 2048,
		AccessPolicy: accessPolicy, ProcessingRequired: processingRequired, Now: now,
	})
	if err != nil {
		t.Fatalf("create MediaAsset %s: %v", assetID, err)
	}
	if _, err := store.CommitMediaAsset(context.Background(), mediaports.MediaAssetCommit{
		Aggregate: asset, ExpectedVersion: 0,
		IdempotencyKey: "seed-" + assetID,
		CommandName:    "CompleteMediaUpload", CommandDigest: "digest-" + assetID,
		ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []mediaports.OutboxEvent{{
			EventID: "event-" + assetID, EventType: "content.media_asset.created",
			AggregateType: "MediaAsset", AggregateID: assetID, AggregateVersion: asset.Version(),
			Payload: []byte(`{}`), OccurredAt: now,
		}},
	}); err != nil {
		t.Fatalf("commit MediaAsset %s: %v", assetID, err)
	}
	return asset
}

func executeMediaAssetHTTP(
	t *testing.T,
	handler func(http.ResponseWriter, *http.Request),
	method string,
	mediaID string,
	query string,
	body string,
	principal rtauth.Principal,
	idempotencyKey ...string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, "/content/media/"+mediaID+query, strings.NewReader(body))
	request.SetPathValue("mediaId", mediaID)
	request.Header.Set("Content-Type", "application/json")
	ctx := request.Context()
	if len(idempotencyKey) != 0 && strings.TrimSpace(idempotencyKey[0]) != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey[0])
		ctx = commandmeta.WithIdempotencyKey(ctx, idempotencyKey[0])
	}
	if strings.TrimSpace(principal.Claims.Subject) != "" {
		ctx = rtauth.WithPrincipal(ctx, principal)
	}
	request = request.WithContext(ctx)
	recorder := httptest.NewRecorder()
	handler(recorder, request)
	return recorder
}

func assertMediaHTTPResponse(t *testing.T, response *httptest.ResponseRecorder, status int, fragments ...string) {
	t.Helper()
	if response.Code != status {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	for _, fragment := range fragments {
		if !strings.Contains(response.Body.String(), fragment) {
			t.Fatalf("response missing %q: %s", fragment, response.Body.String())
		}
	}
}

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

func TestMediaLifecycleConsumerPersistsReadyStateAndCheckpointInRealMongo(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "media_asset_lifecycle_consumer")
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
		ID: "media-consumer-video", OwnerID: "persona-media-consumer", SourceSessionID: "upload-media-consumer",
		ObjectKey: "media/cas/media-consumer-video", SHA256: "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
		MediaType: mediamodel.MediaTypeVideo, MimeType: "video/mp4", FileSize: 4096,
		AccessPolicy: mediamodel.AccessPolicyOwnerOnly, ProcessingRequired: true, Now: now,
	})
	if err != nil {
		t.Fatalf("create processing MediaAsset: %v", err)
	}
	const eventID = "media-consumer-video:1"
	if _, err := store.CommitMediaAsset(context.Background(), mediaports.MediaAssetCommit{
		Aggregate: asset, ExpectedVersion: 0, IdempotencyKey: "create-media-consumer-video",
		CommandName: "CompleteMediaUpload", CommandDigest: "digest-create-media-consumer-video",
		ReceiptExpiresAt: now.Add(24 * time.Hour), Events: []mediaports.OutboxEvent{{
			EventID: eventID, EventType: "content.media_asset.created",
			AggregateType: "MediaAsset", AggregateID: asset.ID(), AggregateVersion: asset.Version(),
			Payload: []byte(`{}`), OccurredAt: now,
		}},
	}); err != nil {
		t.Fatalf("commit processing MediaAsset: %v", err)
	}
	processor := &mongoProcessingProcessor{}
	service := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(store),
		fixedGateway{},
		mediaapp.WithClock(func() time.Time { return now.Add(time.Minute) }),
	)
	const consumer = "media-lifecycle-api"
	handler := mediaprocessing.NewMediaProcessingHandler(
		store,
		store,
		store,
		processor,
		service,
		store,
		mediaprocessing.WithConsumer(consumer),
		mediaprocessing.WithLeaseOwner("media-lifecycle-api-runner"),
		mediaprocessing.WithClock(func() time.Time { return now.Add(time.Minute) }),
	)
	processed, err := handler.Process(context.Background(), 10)
	if err != nil || processed != 1 {
		t.Fatalf("drain real Mongo media event: processed=%d err=%v", processed, err)
	}
	projected, found, err := store.LoadMediaAsset(context.Background(), asset.ID())
	if err != nil || !found {
		t.Fatalf("load projected MediaAsset: found=%v err=%v", found, err)
	}
	if projected.ProcessingStatus() != mediamodel.ProcessingStatusReady || processor.calls != 1 {
		t.Fatalf("projected status=%s processor calls=%d", projected.ProcessingStatus(), processor.calls)
	}
	checkpoint, err := store.LoadCheckpoint(context.Background(), consumer)
	if err != nil || checkpoint == "" {
		t.Fatalf("load media processing checkpoint=%q err=%v", checkpoint, err)
	}
	if count, err := runtime.Database.Collection("media_asset_command_receipts").CountDocuments(
		context.Background(),
		bson.M{"_id": "media-processing-result:" + eventID},
	); err != nil || count != 1 {
		t.Fatalf("media processing receipt count=%d err=%v", count, err)
	}
}

type mongoProcessingProcessor struct {
	calls int
}

func (processor *mongoProcessingProcessor) Process(
	_ context.Context,
	request mediaprocessing.ProcessRequest,
) (mediaprocessing.ProcessOutcome, error) {
	processor.calls++
	prefix := fmt.Sprintf("media/video/s/asset/%s/v%d", request.AssetID, request.AssetVersion)
	return mediaprocessing.ProcessOutcome{Descriptor: mediamodel.MediaProcessingDescriptor{
		Video: mediamodel.VideoProcessingDescriptor{
			ProcessorProfile: "content_processing_progressive_mp4", VerifiedDurationMs: 30_000,
			VideoWidth: 720, VideoHeight: 1280, VideoCodec: "h264", VideoContainer: "mp4",
			VideoAudioCodec: "aac", VideoKeyframeIntervalMs: 2_000, VideoFastStart: true,
			VideoPublicSliceKey: prefix + "/source.mp4", CoverPublicSliceKey: prefix + "/cover.jpg",
			PreviewTrackVersion: 1, PreviewTrackManifestSliceKey: prefix + "/preview/manifest.json",
		},
	}}, nil
}

type fixedGateway struct{}

func (fixedGateway) PublishPublicSlice(context.Context, string, string) error { return nil }

func (fixedGateway) DeliveryURL(_ context.Context, objectKey string) (string, error) {
	return "https://cdn.example.test/" + objectKey, nil
}

func (fixedGateway) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	return "https://cdn.example.test/" + objectKey, nil
}
