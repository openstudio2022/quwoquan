package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	filtercataloghttp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/adapters/inbound/http"
	filtercatalogapp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/application"
	filtercatalogmodel "quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/model"
	filtercatalogpersistence "quwoquan_service/services/content-service/internal/media/filter_catalog_release/infrastructure/persistence"
)

func newFilterCatalogAPI(
	t *testing.T,
) (http.Handler, *filtercatalogpersistence.MongoStore) {
	t.Helper()
	cleanFilterCatalogCollections(t)
	t.Cleanup(func() { cleanFilterCatalogCollections(t) })
	store := filtercatalogpersistence.NewMongoStore(requireFilterCatalogMongoDB(t))
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure FilterCatalogRelease indexes: %v", err)
	}
	service, err := filtercatalogapp.NewService(store, store)
	if err != nil {
		t.Fatal(err)
	}
	base := filtercataloghttp.NewHandler(
		filtercatalogapp.BindFacades(service),
	).Route(http.NotFoundHandler())
	return rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("content"),
	)(base), store
}

func validFilterCatalogStageFixture(
	t *testing.T,
	releaseID string,
	contrast float64,
) filterCatalogStageFixture {
	t.Helper()
	categories := []filtercatalogmodel.FilterCategoryDefinition{
		{
			CategoryID:        "basic",
			DisplayNameZhHans: "基础",
			Sort:              1,
			Enabled:           true,
		},
		{
			CategoryID:        "portrait",
			DisplayNameZhHans: "人像",
			Sort:              2,
			Enabled:           true,
		},
	}
	presets := []filtercatalogmodel.FilterPresetDefinition{
		{
			PresetID:          "original",
			CategoryID:        "basic",
			DisplayNameZhHans: "原图",
			Sort:              1,
			Enabled:           true,
		},
		{
			PresetID:          "portrait-soft",
			CategoryID:        "portrait",
			DisplayNameZhHans: "柔光人像",
			Sort:              1,
			Enabled:           true,
			DefaultStrength:   80,
			Adjustments: filtercatalogmodel.FilterAdjustmentValues{
				LightSense: 12,
				Contrast:   contrast,
			},
		},
	}
	fallbacks := []string{"original", "portrait-soft"}
	digest, err := filtercatalogmodel.ComputeCanonicalDigest(categories, presets, fallbacks)
	if err != nil {
		t.Fatalf("compute filter catalog fixture digest: %v", err)
	}
	return filterCatalogStageFixture{
		ReleaseID:                    releaseID,
		SourceOwner:                  "qwq-data",
		CanonicalDigest:              digest,
		Categories:                   categories,
		Presets:                      presets,
		RecommendedFallbackPresetIDs: fallbacks,
	}
}

func stageFilterCatalog(
	t *testing.T,
	handler http.Handler,
	releaseID string,
	contrast float64,
	idempotencyKey string,
) {
	t.Helper()
	stageFilterCatalogFixture(
		t,
		handler,
		validFilterCatalogStageFixture(t, releaseID, contrast),
		idempotencyKey,
	)
}

func stageFilterCatalogFixture(
	t *testing.T,
	handler http.Handler,
	fixture filterCatalogStageFixture,
	idempotencyKey string,
) {
	t.Helper()
	performFilterCatalogCommand(
		t,
		handler,
		"/internal/content/filter-catalog-releases",
		fixture,
		idempotencyKey,
	)
}

func performFilterCatalogCommand(
	t *testing.T,
	handler http.Handler,
	path string,
	body any,
	idempotencyKey string,
) map[string]any {
	t.Helper()
	response := performFilterCatalogRequest(
		t,
		handler,
		http.MethodPost,
		path,
		body,
		idempotencyKey,
	)
	if response.Code != http.StatusOK {
		t.Fatalf(
			"filter catalog command %s status=%d body=%s",
			path,
			response.Code,
			response.Body.String(),
		)
	}
	var payload map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	return payload
}

func performFilterCatalogRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body any,
	idempotencyKey string,
) *httptest.ResponseRecorder {
	t.Helper()
	var encoded []byte
	var err error
	if body != nil {
		encoded, err = json.Marshal(body)
		if err != nil {
			t.Fatal(err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(encoded))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Request-Id", "filter-catalog-api-integration")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	if method != http.MethodGet && method != http.MethodHead {
		request = request.WithContext(rtauth.WithPrincipal(
			request.Context(),
			rtauth.Principal{
				Claims: rtauth.Claims{
					Subject: "service:qwq-data",
					Scope:   "content.filter_catalog.manage",
					Roles:   []string{"service"},
				},
				Actor: rtoperation.ActorContext{AccountID: "service:qwq-data"},
			},
		))
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func assertFilterCatalogRuntimeError(
	t *testing.T,
	response *httptest.ResponseRecorder,
	status int,
	code string,
) {
	t.Helper()
	if response.Code != status {
		t.Fatalf(
			"runtime error status=%d want=%d body=%s",
			response.Code,
			status,
			response.Body.String(),
		)
	}
	var payload map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["code"] != code {
		t.Fatalf("runtime error code=%v want=%s payload=%+v", payload["code"], code, payload)
	}
	if payload["requestId"] == "" || payload["traceId"] == "" {
		t.Fatalf("runtime error lost request/trace identity: %+v", payload)
	}
}

func loadFilterCatalogRelease(
	t *testing.T,
	store *filtercatalogpersistence.MongoStore,
	releaseID string,
) *filtercatalogmodel.FilterCatalogRelease {
	t.Helper()
	release, found, err := store.Load(context.Background(), releaseID)
	if err != nil || !found {
		t.Fatalf("load FilterCatalogRelease %s: found=%v err=%v", releaseID, found, err)
	}
	return release
}

func countFilterCatalogDocuments(t *testing.T, filter any) int64 {
	t.Helper()
	count, err := requireFilterCatalogMongoDB(t).
		Collection("filter_catalog_releases").
		CountDocuments(context.Background(), filter)
	if err != nil {
		t.Fatal(err)
	}
	return count
}

func countFilterCatalogReceipts(t *testing.T) int64 {
	t.Helper()
	count, err := requireFilterCatalogMongoDB(t).
		Collection("filter_catalog_command_receipts").
		CountDocuments(context.Background(), bson.M{})
	if err != nil {
		t.Fatal(err)
	}
	return count
}

func cleanFilterCatalogCollections(t *testing.T) {
	t.Helper()
	for _, collection := range []string{
		"filter_catalog_command_receipts",
		"filter_catalog_releases",
	} {
		if _, err := requireFilterCatalogMongoDB(t).
			Collection(collection).
			DeleteMany(context.Background(), bson.M{}); err != nil {
			t.Fatalf("clean %s: %v", collection, err)
		}
	}
}
