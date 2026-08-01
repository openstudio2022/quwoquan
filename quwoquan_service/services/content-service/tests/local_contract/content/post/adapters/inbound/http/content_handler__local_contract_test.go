package http_test

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	"strconv"
	"strings"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
)

type allowAllFeedViewerBlockReader struct{}

func (allowAllFeedViewerBlockReader) ListBlockedPersonaIDs(
	_ context.Context,
	_ string,
) ([]string, error) {
	return []string{}, nil
}

type readyFeedActiveSupplyReader struct{}

type failingBehaviorSignalProcessor struct {
	err error
}

func (p failingBehaviorSignalProcessor) ProcessSignal(
	_ context.Context,
	_ rtrec.BehaviorSignal,
) error {
	return p.err
}

func (p failingBehaviorSignalProcessor) ProcessSignalBatch(
	_ context.Context,
	_ []rtrec.BehaviorSignal,
) error {
	return p.err
}

type releaseBoundLocalCandidateSource struct {
	inner rtrec.CandidateSource
}

func (s releaseBoundLocalCandidateSource) Recall(
	ctx context.Context,
	req rtrec.RecallRequest,
) ([]rtrec.ContentCandidate, error) {
	items, err := s.inner.Recall(ctx, req)
	if err != nil {
		return nil, err
	}
	for i := range items {
		items[i].SourceOwner = "qwq_data"
		items[i].ReleaseID = req.ActiveReleaseID
		items[i].ManifestDigest = req.ActiveManifestDigest
		items[i].LifecycleStatus = "active"
		if strings.TrimSpace(items[i].SupplySource) == "" {
			items[i].SupplySource = "data_engineering"
		}
	}
	return items, nil
}

func (readyFeedActiveSupplyReader) ActiveSupplySnapshot(
	context.Context,
) (feedapp.ActiveSupplySnapshot, error) {
	return feedapp.ActiveSupplySnapshot{
		Environment:     "local_contract",
		SourceOwner:     "qwq_data",
		Status:          "active",
		ActiveReleaseID: "rel_local_contract",
		ManifestDigest:  "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ReadbackStatus:  "passed",
		Posts:           1,
		DiscoveryPosts:  1,
		PlayableVideos:  1,
	}, nil
}

type acceptingActiveTaxonomyLeafValidationPort struct{}

func (acceptingActiveTaxonomyLeafValidationPort) ValidateActiveTaxonomyLeaves(
	_ context.Context,
	_ string,
	_ []string,
) error {
	return nil
}

type localPostDetailReader struct {
	store *testsupport.PostStore
}

func (r localPostDetailReader) FindPostDetail(
	ctx context.Context,
	postID postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	post, found := r.store.FindByID(ctx, string(postID))
	if !found {
		return postports.PostDetailSlice{}, false, nil
	}
	raw, err := json.Marshal(post)
	if err != nil {
		return postports.PostDetailSlice{}, false, err
	}
	var asMap map[string]any
	if err := json.Unmarshal(raw, &asMap); err != nil {
		return postports.PostDetailSlice{}, false, err
	}
	if _, ok := asMap["postId"]; !ok {
		asMap["postId"] = asMap["id"]
	}
	delete(asMap, "id")
	delete(asMap, "_id")
	normalized, err := json.Marshal(asMap)
	if err != nil {
		return postports.PostDetailSlice{}, false, err
	}
	var detail postports.PostDetailSlice
	if err := json.Unmarshal(normalized, &detail); err != nil {
		return postports.PostDetailSlice{}, false, err
	}
	// moderationStatus 是服务端 gate，json:"-" 禁止出站，因此 test reader
	// 必须像生产 BSON projection 一样显式填充。
	detail.ModerationStatus = post.ModerationStatus
	return detail, true, nil
}

func newTestHandler() http.Handler {
	handler, _ := newTestHandlerWithHotPath()
	return handler
}

func newTestHandlerWithHotPath() (http.Handler, *rtrec.HotPath) {
	redis := testsupport.NewFakeRedis()
	hotPath := rtrec.NewHotPath(redis)
	store := testsupport.NewPostStore(recinfra.DefaultSeedPosts())
	source := releaseBoundLocalCandidateSource{
		inner: recinfra.NewPostProjectionSource(store, store),
	}
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source})
	feedService := feedapp.NewFeedService(
		engine,
		testsupport.NewPostFeedReader(store),
		feedapp.WithFeedViewerBlockReader(allowAllFeedViewerBlockReader{}),
		feedapp.WithActiveSupplyReader(readyFeedActiveSupplyReader{}),
		feedapp.WithFeedDeliveryPageStore(
			deliveryredis.NewStore(rtredis.NewMemoryClient()),
		),
	)
	postService := postapp.NewPostService(
		postapp.BindDataPorts(store),
		postapp.WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	reportStore := testsupport.NewReportStore()
	reportService := reportapp.NewReportService(reportapp.BindDataPorts(reportStore))
	behaviorService := behaviorapp.NewBehaviorService(
		hotPath,
		store,
		behaviorapp.WithOnboardingInterestTaxonomyValidator(
			behaviorapp.CatalogBackedOnboardingInterestTaxonomy{
				DimensionRoots:           map[string]string{"topic": "Topic", "audience": "Audience", "format": "Format", "entity": "Entity"},
				MinSelections:            1,
				MaxSelections:            12,
				DimensionMinSelections:   map[string]int{"topic": 0, "audience": 0, "format": 0, "entity": 0},
				DimensionMaxSelections:   map[string]int{"topic": 4, "audience": 4, "format": 4, "entity": 4},
				ActiveLeafValidationPort: acceptingActiveTaxonomyLeafValidationPort{},
			},
		),
	)
	postQueryService := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail:     localPostDetailReader{store: store},
		Tombstones: store,
	})
	handler := NewContentHandler(
		feedService,
		postapp.BindFacades(postService),
		postQueryService,
		nil,
		nil,
		reportapp.BindFacades(reportService),
		behaviorService,
	).Routes()
	return handler, hotPath
}

func newFeedHandlerWithFeatures(features rtrec.FeatureProvider) http.Handler {
	redis := testsupport.NewFakeRedis()
	hotPath := rtrec.NewHotPath(redis)
	store := testsupport.NewPostStore(recinfra.DefaultSeedPosts())
	source := releaseBoundLocalCandidateSource{
		inner: recinfra.NewPostProjectionSource(store, store),
	}
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source}, rtrec.WithFeatureProvider(features))
	feedService := feedapp.NewFeedService(
		engine,
		testsupport.NewPostFeedReader(store),
		feedapp.WithFeedViewerBlockReader(allowAllFeedViewerBlockReader{}),
		feedapp.WithActiveSupplyReader(readyFeedActiveSupplyReader{}),
		feedapp.WithFeedDeliveryPageStore(
			deliveryredis.NewStore(rtredis.NewMemoryClient()),
		),
	)
	postService := postapp.NewPostService(
		postapp.BindDataPorts(store),
		postapp.WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	reportStore := testsupport.NewReportStore()
	reportService := reportapp.NewReportService(reportapp.BindDataPorts(reportStore))
	behaviorService := behaviorapp.NewBehaviorService(hotPath, store)
	postQueryService := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail:     localPostDetailReader{store: store},
		Tombstones: store,
	})
	return NewContentHandler(
		feedService,
		postapp.BindFacades(postService),
		postQueryService,
		nil,
		nil,
		reportapp.BindFacades(reportService),
		behaviorService,
	).Routes()
}

type stubFeatureProvider struct {
	features *rtrec.UserFeatureVector
}

func (s *stubFeatureProvider) GetFeatures(_ context.Context, _ string) (*rtrec.UserFeatureVector, error) {
	return s.features, nil
}

func setActorHeaders(req *http.Request, ownerID, personaID string) {
	if ownerID != "" {
		req.Header.Set("X-Client-User-Id", ownerID)
	}
	if personaID != "" {
		req.Header.Set("X-Client-Persona-Id", personaID)
	}
	if req.Header.Get("Idempotency-Key") == "" {
		req.Header.Set("Idempotency-Key", "contract-test-"+personaID+"-"+strconv.FormatInt(time.Now().UnixNano(), 10))
	}
}

func TestHealthz(t *testing.T) {
	req := httptest.NewRequest("GET", "/healthz", nil)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("unexpected status: %d", rec.Code)
	}
}

func TestFeedAndPostEndpoints(t *testing.T) {
	feedReq := httptest.NewRequest("GET", "/content/feed?type=photo&limit=1", nil)
	feedRec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(feedRec, feedReq)
	if feedRec.Code != 200 {
		t.Fatalf("unexpected feed status: %d: %s", feedRec.Code, feedRec.Body.String())
	}
	var feedBody struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(feedRec.Body.Bytes(), &feedBody); err != nil {
		t.Fatalf("decode feed response: %v", err)
	}
	if len(feedBody.Items) == 0 {
		t.Fatalf("expected feed items")
	}

	postReq := httptest.NewRequest("GET", "/content/posts/post_photo_001", nil)
	postRec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(postRec, postReq)
	if postRec.Code != 200 {
		t.Fatalf("unexpected post status: %d", postRec.Code)
	}
	var postBody map[string]any
	if err := json.Unmarshal(postRec.Body.Bytes(), &postBody); err != nil {
		t.Fatalf("decode post response: %v", err)
	}
	if postBody["postId"] != "post_photo_001" {
		t.Fatalf("GetPost must expose the generated postId wire field: %+v", postBody)
	}
	if _, legacyID := postBody["_id"]; legacyID {
		t.Fatalf("GetPost must not expose storage _id as a client wire field: %+v", postBody)
	}
}

func TestFeedPaginationAdmissionFailsClosedBeforeApplicationDispatch(t *testing.T) {
	for _, target := range []string{
		"/content/feed?limit=0",
		"/content/feed?limit=-1",
		"/content/feed?limit=21",
		"/content/feed?limit=not-an-integer",
	} {
		t.Run(target, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, target, nil)
			rec := httptest.NewRecorder()

			newTestHandler().ServeHTTP(rec, req)

			if rec.Code != http.StatusBadRequest {
				t.Fatalf("%s status = %d, want 400: %s", target, rec.Code, rec.Body.String())
			}
		})
	}

	params, err := BindGeneratedGetFeedParams(
		httptest.NewRequest(http.MethodGet, "/content/feed", nil),
	)
	if err != nil {
		t.Fatalf("default pagination binding failed: %v", err)
	}
	if params.Limit != 20 {
		t.Fatalf("generated default feed limit = %d, want 20", params.Limit)
	}
}

func TestAppConfigEndpointIsImplemented(t *testing.T) {
	req := httptest.NewRequest("GET", "/config/app", nil)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected app config status 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode app config response: %v", err)
	}
	content, _ := body["content"].(map[string]any)
	if content == nil {
		t.Fatalf("missing content config: %+v", body)
	}
	if _, exists := body["packageVersion"]; exists {
		t.Fatalf("app config exposes retired packageVersion: %+v", body)
	}
	etag := rec.Header().Get("ETag")
	if !strings.HasPrefix(etag, `"sha256:`) || !strings.HasSuffix(etag, `"`) {
		t.Fatalf("app config ETag must be the quoted canonical configHash: %q", etag)
	}

	conditional := httptest.NewRequest(http.MethodGet, "/config/app", nil)
	conditional.Header.Set("If-None-Match", etag)
	conditionalRec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(conditionalRec, conditional)
	if conditionalRec.Code != http.StatusNotModified {
		t.Fatalf("matching canonical ETag status=%d want 304", conditionalRec.Code)
	}
	if conditionalRec.Body.Len() != 0 {
		t.Fatalf("304 response must not include an app config body: %q", conditionalRec.Body.String())
	}
}

func TestAuthorImpactEndpointFailsWhenStoreIsNotConfigured(t *testing.T) {
	req := httptest.NewRequest("GET", "/content/personas/test_author/author-impact", nil)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected author impact status 503, got %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "CONTENT.SYSTEM.required_dependency_unavailable") {
		t.Fatalf("expected structured dependency failure, got: %s", rec.Body.String())
	}
}

func TestAuthorImpactEvidenceEndpointFailsWhenStoreIsNotConfigured(t *testing.T) {
	req := httptest.NewRequest(
		"GET",
		"/content/personas/test_author/author-impact/evidence?impactId=impact_1",
		nil,
	)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected author impact evidence status 503, got %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "CONTENT.SYSTEM.required_dependency_unavailable") {
		t.Fatalf("expected structured dependency failure, got: %s", rec.Body.String())
	}
}

func TestSubmitPostPublicationBodyBindingRejectsUnknownField(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"unknownField":"x"}`),
	)
	setActorHeaders(req, "owner_test_unknown", "sub_test_unknown")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("unexpected create status for invalid field: %d", rec.Code)
	}
}

func TestSubmitPostPublicationRequiresTransportIdempotencyHeader(t *testing.T) {
	handler := newTestHandler()
	req := httptest.NewRequest(
		http.MethodPost,
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-missing-key","localDraftId":"draft-missing-key","contentType":"micro","body":"缺少幂等键"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-Persona-Id", "persona-idempotency")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected 400 without Idempotency-Key, got %d: %s",
			rec.Code,
			rec.Body.String(),
		)
	}
}

func TestSubmitPostPublicationHonorsNonProductionMediaNotReadyInjection(t *testing.T) {
	t.Setenv("APP_ENV", "gamma")
	req := httptest.NewRequest(
		http.MethodPost,
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-media-not-ready","localDraftId":"draft-media-not-ready","contentType":"text","body":"test injection"}`),
	)
	req.Header.Set("X-Test-Error-Inject", "CONTENT.USER.media_not_ready")
	rec := httptest.NewRecorder()

	newTestHandler().ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected injected media_not_ready status 400, got %d: %s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode injected media_not_ready response: %v", err)
	}
	if body["code"] != "CONTENT.USER.media_not_ready" {
		t.Fatalf("unexpected injected media_not_ready code: %+v", body)
	}
	recovery, _ := body["recovery"].(map[string]any)
	if recovery["action"] != "retry" || recovery["afterSeconds"] != float64(3) {
		t.Fatalf("unexpected injected media_not_ready recovery: %+v", recovery)
	}
}

func TestSubmitPostPublicationBodyBindingAcceptsRequestEntityFields(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-create","localDraftId":"draft-create","contentType":"article","articleMarkdown":"# 测试文章\n\nb","markdownDialect":"qwq-rich-md","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(req, "owner_test_create", "sub_test_create")
	req.Header.Set("Idempotency-Key", "intent-create")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("unexpected create status for valid payload: %d", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	postID, _ := body["postId"].(string)
	if strings.TrimSpace(postID) == "" {
		t.Fatalf("missing postId in create response: %+v", body)
	}
	if body["publishIntentId"] != "intent-create" ||
		body["localDraftId"] != "draft-create" ||
		body["state"] != "published" {
		t.Fatalf("publication receipt is incomplete: %+v", body)
	}
}

func TestPostCommandBodiesBindOnlyCanonicalRequestEntityFields(t *testing.T) {
	testCases := []struct {
		name      string
		operation string
		body      string
		wantKey   string
	}{
		{
			name:      "submit publication",
			operation: "SubmitPostPublication",
			body:      `{"publishIntentId":"intent-canonical","localDraftId":"draft-canonical","contentType":"micro","body":"canonical"}`,
			wantKey:   "publishIntentId",
		},
		{
			name:      "update settings",
			operation: "UpdatePostSettings",
			body:      `{"visibility":"private","assistantUsePolicy":"exclude"}`,
			wantKey:   "visibility",
		},
		{
			name:      "promote to work",
			operation: "PromotePostToWork",
			body:      `{"contentType":"article","title":"canonical work"}`,
			wantKey:   "contentType",
		},
		{
			name:      "generate article summary",
			operation: "GenerateArticleSummary",
			body:      `{"title":"canonical title","body":"canonical body"}`,
			wantKey:   "title",
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodPost,
				"/",
				bytes.NewBufferString(testCase.body),
			)
			payload, err := BindGeneratedRequestBodyFromRequest(
				request,
				testCase.operation,
			)
			if err != nil {
				t.Fatalf("BindGeneratedRequestBodyFromRequest() error = %v", err)
			}
			if _, exists := payload[testCase.wantKey]; !exists {
				t.Fatalf(
					"%s canonical body is missing %s: %v",
					testCase.operation,
					testCase.wantKey,
					payload,
				)
			}
		})
	}

	pathLeak := httptest.NewRequest(
		http.MethodPatch,
		"/",
		bytes.NewBufferString(`{"postId":"post-must-stay-in-path","visibility":"private"}`),
	)
	if _, err := BindGeneratedRequestBodyFromRequest(
		pathLeak,
		"UpdatePostSettings",
	); err == nil {
		t.Fatal("path-bound postId must not be accepted in the request body")
	}
}

func TestReportBehaviorsEndpoint(t *testing.T) {
	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	req := httptest.NewRequest(
		"POST",
		"/content/behaviors",
		bytes.NewBufferString(fmt.Sprintf(
			`{"userId":"u1","events":[{"clientEventId":"evt-handler-001","occurredAt":%q,"contentId":"post_photo_001","action":"click"}]}`,
			occurredAt,
		)),
	)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("unexpected behaviors status: %d", rec.Code)
	}
}

func TestReportBehaviorsMapsOperationalFailuresToDeclaredHTTPCodes(t *testing.T) {
	testCases := []struct {
		name         string
		failure      error
		status       int
		expectedCode string
	}{
		{
			name:         "storage write failure",
			failure:      fmt.Errorf("controlled behavior write failure"),
			status:       http.StatusInternalServerError,
			expectedCode: "CONTENT.SYSTEM.storage_write_failed",
		},
		{
			name:         "dependency timeout",
			failure:      context.DeadlineExceeded,
			status:       http.StatusGatewayTimeout,
			expectedCode: "CONTENT.MIDDLEWARE.upstream_timeout",
		},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			store := testsupport.NewPostStore(recinfra.DefaultSeedPosts())
			behaviorService := behaviorapp.NewBehaviorService(
				failingBehaviorSignalProcessor{err: testCase.failure},
				store,
			)
			handler := NewContentHandler(
				nil,
				nil,
				nil,
				nil,
				nil,
				nil,
				behaviorService,
			).Routes()
			occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
			req := httptest.NewRequest(
				http.MethodPost,
				"/content/behaviors",
				bytes.NewBufferString(fmt.Sprintf(
					`{"userId":"u-failure","events":[{"clientEventId":"evt-failure-001","occurredAt":%q,"contentId":"post_photo_001","action":"click"}]}`,
					occurredAt,
				)),
			)
			rec := httptest.NewRecorder()

			handler.ServeHTTP(rec, req)

			if rec.Code != testCase.status {
				t.Fatalf(
					"status=%d want=%d: %s",
					rec.Code,
					testCase.status,
					rec.Body.String(),
				)
			}
			if !strings.Contains(rec.Body.String(), testCase.expectedCode) {
				t.Fatalf(
					"expected canonical error %s: %s",
					testCase.expectedCode,
					rec.Body.String(),
				)
			}
		})
	}
}

// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/interest-onboarding-prior/spec.md#gwt-001
func TestReportBehaviorsOnboardingInterestCreatesCanonicalTagPrior(t *testing.T) {
	handler, hotPath := newTestHandlerWithHotPath()
	const (
		userID    = "onboarding-user"
		sessionID = "onboarding-session"
		eventID   = "evt-onboarding-interest-001"
	)
	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	payload := fmt.Sprintf(
		`{"userId":%q,"events":[{"clientEventId":%q,"occurredAt":%q,"sessionId":%q,"action":"onboarding_interest","taxonomyReleaseId":"tag-taxonomy-test-001","tagRefs":[" Topic/兴趣/旅行 ","Audience/用户/兴趣偏好/摄影","Topic/兴趣/旅行",""]}]}`,
		userID,
		eventID,
		occurredAt,
		sessionID,
	)

	for attempt := 0; attempt < 2; attempt++ {
		req := httptest.NewRequest(
			http.MethodPost,
			"/content/behaviors",
			bytes.NewBufferString(payload),
		)
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != http.StatusNoContent {
			t.Fatalf(
				"onboarding behavior attempt %d returned %d: %s",
				attempt+1,
				rec.Code,
				rec.Body.String(),
			)
		}
	}

	state, err := hotPath.GetSessionState(context.Background(), userID, sessionID)
	if err != nil {
		t.Fatalf("read onboarding hotpath state: %v", err)
	}
	if len(state.TagWeights) != 2 {
		t.Fatalf("expected exactly two canonical tag priors, got %+v", state.TagWeights)
	}
	for _, tagRef := range []string{
		"Topic/兴趣/旅行",
		"Audience/用户/兴趣偏好/摄影",
	} {
		if state.TagWeights[tagRef] != rtrec.SignalWeights["onboarding_interest"] {
			t.Fatalf(
				"expected one onboarding weight for %q, got %+v",
				tagRef,
				state.TagWeights,
			)
		}
	}

	invalidReq := httptest.NewRequest(
		http.MethodPost,
		"/content/behaviors",
		bytes.NewBufferString(fmt.Sprintf(
			`{"userId":"onboarding-invalid","events":[{"clientEventId":"evt-onboarding-interest-empty","occurredAt":%q,"sessionId":"onboarding-invalid-session","action":"onboarding_interest","taxonomyReleaseId":"tag-taxonomy-test-001","tagRefs":[""," "]}]}`,
			occurredAt,
		)),
	)
	invalidRec := httptest.NewRecorder()
	handler.ServeHTTP(invalidRec, invalidReq)
	if invalidRec.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected canonical invalid-argument failure for empty onboarding tags, got %d: %s",
			invalidRec.Code,
			invalidRec.Body.String(),
		)
	}
	if !strings.Contains(
		invalidRec.Body.String(),
		"CONTENT.USER.invalid_argument",
	) {
		t.Fatalf(
			"expected structured invalid-argument failure, got: %s",
			invalidRec.Body.String(),
		)
	}
	invalidState, err := hotPath.GetSessionState(
		context.Background(),
		"onboarding-invalid",
		"onboarding-invalid-session",
	)
	if err != nil {
		t.Fatalf("read rejected onboarding hotpath state: %v", err)
	}
	if len(invalidState.TagWeights) != 0 {
		t.Fatalf(
			"rejected onboarding request must not create recommendation priors: %+v",
			invalidState.TagWeights,
		)
	}
}

// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/interest-onboarding-prior/spec.md#gwt-001
func TestReportBehaviorsRejectsRetiredCatalogVersionBeforeWrites(t *testing.T) {
	handler, hotPath := newTestHandlerWithHotPath()
	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	// Retired catalogVersion input must be rejected by the strict decoder; it
	// cannot be ignored or translated into the canonical taxonomy release.
	payload := fmt.Sprintf(
		`{"userId":"onboarding-retired-field","events":[{"clientEventId":"evt-onboarding-retired-field","occurredAt":%q,"sessionId":"onboarding-retired-session","action":"onboarding_interest","catalogVersion":"retired","taxonomyReleaseId":"tag-taxonomy-test-001","tagRefs":["Topic/兴趣/旅行"]}]}`,
		occurredAt,
	)
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("retired catalogVersion status=%d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "CONTENT.USER.invalid_argument") {
		t.Fatalf("expected canonical invalid-argument failure, got: %s", rec.Body.String())
	}
	state, err := hotPath.GetSessionState(
		context.Background(),
		"onboarding-retired-field",
		"onboarding-retired-session",
	)
	if err != nil {
		t.Fatalf("read rejected onboarding state: %v", err)
	}
	if len(state.TagWeights) != 0 {
		t.Fatalf("retired catalogVersion input wrote recommendation priors: %+v", state.TagWeights)
	}
}

func TestReportBehaviorsAcceptsGzipAndOccurredAt(t *testing.T) {
	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	payload := fmt.Sprintf(
		`{"userId":"u-gzip","events":[{"clientEventId":"evt-gzip-001","occurredAt":%q,"contentId":"post_photo_001","action":"click"}]}`,
		occurredAt,
	)
	var compressed bytes.Buffer
	writer := gzip.NewWriter(&compressed)
	if _, err := writer.Write([]byte(payload)); err != nil {
		t.Fatalf("compress behavior payload: %v", err)
	}
	if err := writer.Close(); err != nil {
		t.Fatalf("close gzip writer: %v", err)
	}

	req := httptest.NewRequest(
		"POST",
		"/content/behaviors",
		bytes.NewReader(compressed.Bytes()),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Content-Encoding", "gzip")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("gzip behavior payload rejected: %d: %s", rec.Code, rec.Body.String())
	}
}

// TestFeedIssuesServerFeedRequestID 断言首页推荐主链路服务端权威下发 feedRequestId（frq_ 前缀）
// 与 policyDigest，并在客户端回显时保持同一归因 id（feedRequestId echo）。
func TestFeedIssuesServerFeedRequestID(t *testing.T) {
	handler := newTestHandler()

	firstReq := httptest.NewRequest("GET", "/content/feed?sort=recommend&limit=2", nil)
	firstReq.Header.Set("X-Client-Session-Id", "feed-request-id-session")
	firstRec := httptest.NewRecorder()
	handler.ServeHTTP(firstRec, firstReq)
	if firstRec.Code != http.StatusOK {
		t.Fatalf("unexpected feed status: %d", firstRec.Code)
	}
	var firstBody struct {
		FeedRequestID string `json:"feedRequestId"`
		PolicyDigest  string `json:"policyDigest"`
	}
	if err := json.Unmarshal(firstRec.Body.Bytes(), &firstBody); err != nil {
		t.Fatalf("decode feed response: %v", err)
	}
	if !strings.HasPrefix(firstBody.FeedRequestID, "frq_") {
		t.Fatalf("expected server-issued feedRequestId with frq_ prefix, got %q", firstBody.FeedRequestID)
	}
	if !strings.HasPrefix(firstBody.PolicyDigest, "sha256:") {
		t.Fatalf("expected canonical policyDigest, got %q", firstBody.PolicyDigest)
	}

	echoReq := httptest.NewRequest(
		"GET",
		"/content/feed?sort=recommend&limit=2&feedRequestId="+firstBody.FeedRequestID,
		nil,
	)
	echoReq.Header.Set("X-Client-Session-Id", "feed-request-id-session")
	echoRec := httptest.NewRecorder()
	handler.ServeHTTP(echoRec, echoReq)
	if echoRec.Code != http.StatusOK {
		t.Fatalf("unexpected feed echo status: %d", echoRec.Code)
	}
	var echoBody struct {
		FeedRequestID string `json:"feedRequestId"`
	}
	if err := json.Unmarshal(echoRec.Body.Bytes(), &echoBody); err != nil {
		t.Fatalf("decode feed echo response: %v", err)
	}
	if echoBody.FeedRequestID != firstBody.FeedRequestID {
		t.Fatalf("expected feedRequestId echo %q, got %q", firstBody.FeedRequestID, echoBody.FeedRequestID)
	}
}

func TestFeedRecommendUsesLongTermTagFeatures(t *testing.T) {
	handler := newFeedHandlerWithFeatures(&stubFeatureProvider{features: &rtrec.UserFeatureVector{
		TagAffinities: map[string]float64{"art": 10},
	}})
	req := httptest.NewRequest("GET", "/content/feed?sort=recommend&limit=1", nil)
	req.Header.Set("X-Client-User-Id", "u1")
	req.Header.Set("X-Client-Session-Id", "long-term-tag-feature-session")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("unexpected feed status: %d", rec.Code)
	}
	var body struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode feed response: %v", err)
	}
	if len(body.Items) == 0 {
		t.Fatalf("expected feed items")
	}
	postID, _ := body.Items[0]["postId"].(string)
	if postID == "" {
		t.Fatalf("missing postId in first item: %+v", body.Items[0])
	}
	if _, legacyID := body.Items[0]["_id"]; legacyID {
		t.Fatalf("feed item must not expose storage _id: %+v", body.Items[0])
	}
}

func TestFeedWithSessionIdFromHeader(t *testing.T) {
	req := httptest.NewRequest("GET", "/content/feed?type=photo&limit=1", nil)
	req.Header.Set("X-Client-Session-Id", "dart_session_abc")
	req.Header.Set("X-Client-User-Id", "user_123")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf(
			"unexpected feed status with headers: %d: %s",
			rec.Code,
			rec.Body.String(),
		)
	}
}

func TestBehaviorsWithSessionIdFromHeader(t *testing.T) {
	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	req := httptest.NewRequest(
		"POST",
		"/content/behaviors",
		bytes.NewBufferString(fmt.Sprintf(
			`{"events":[{"clientEventId":"evt-handler-header-001","occurredAt":%q,"contentId":"post_photo_001","action":"click"}]}`,
			occurredAt,
		)),
	)
	req.Header.Set("X-Client-Session-Id", "dart_session_abc")
	req.Header.Set("X-Client-User-Id", "user_123")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("unexpected behaviors status with header auth: %d", rec.Code)
	}
}

func TestSubmitPostPublicationWithLocationField(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-location","localDraftId":"draft-location","contentType":"article","location":{"latitude":39.9,"longitude":116.4},"locationName":"Beijing","articleMarkdown":"# loc test\n\nb","markdownDialect":"qwq-rich-md","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(req, "owner_test_location", "sub_test_location")
	req.Header.Set("Idempotency-Key", "intent-location")
	rec := httptest.NewRecorder()
	handler := newTestHandler()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("unexpected create status: %d, body: %s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	json.Unmarshal(rec.Body.Bytes(), &body)
	postID, _ := body["postId"].(string)
	getReq := httptest.NewRequest("GET", "/content/posts/"+postID, nil)
	getRec := httptest.NewRecorder()
	handler.ServeHTTP(getRec, getReq)
	var detail map[string]any
	json.Unmarshal(getRec.Body.Bytes(), &detail)
	loc, ok := detail["location"].(map[string]any)
	if !ok {
		t.Fatalf("location should be a map, got %T", detail["location"])
	}
	if loc["latitude"].(float64) != 39.9 {
		t.Errorf("expected latitude 39.9, got %v", loc["latitude"])
	}
}

func TestMomentRequiresBodyOrMedia(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-empty","localDraftId":"draft-empty","contentType":"micro","body":""}`),
	)
	setActorHeaders(req, "owner_test_moment", "sub_test_moment")
	req.Header.Set("Idempotency-Key", "intent-empty")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for empty moment payload, got %d", rec.Code)
	}
}

func TestRetiredPostDraftMutationRoutesAreAbsent(t *testing.T) {
	handler := newTestHandler()
	createReq := httptest.NewRequest(
		"POST",
		"/content/posts",
		bytes.NewBufferString(`{"contentType":"micro","body":"retired"}`),
	)
	setActorHeaders(createReq, "u1", "u1")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusNotFound {
		t.Fatalf("retired CreatePost route must be absent, got %d", createRec.Code)
	}
	publishReq := httptest.NewRequest(
		"POST",
		"/content/posts/post-retired/publish",
		bytes.NewBufferString(`{}`),
	)
	setActorHeaders(publishReq, "u1", "u1")
	publishRec := httptest.NewRecorder()
	handler.ServeHTTP(publishRec, publishReq)
	if publishRec.Code != http.StatusNotFound {
		t.Fatalf("retired PublishPost route must be absent, got %d", publishRec.Code)
	}
	updateReq := httptest.NewRequest(
		"PATCH",
		"/content/posts/post-retired",
		bytes.NewBufferString(`{"title":"new title"}`),
	)
	setActorHeaders(updateReq, "u1", "u1")
	updateRec := httptest.NewRecorder()
	handler.ServeHTTP(updateRec, updateReq)
	if updateRec.Code != http.StatusNotFound {
		t.Fatalf("retired UpdatePost route must be absent, got %d", updateRec.Code)
	}
}

func TestDeletePostAndTombstoneLookup(t *testing.T) {
	handler := newTestHandler()
	createReq := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-delete","localDraftId":"draft-delete","contentType":"article","articleMarkdown":"# to delete\n\nb","markdownDialect":"qwq-rich-md","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(createReq, "u_delete", "u_delete")
	createReq.Header.Set("Idempotency-Key", "intent-delete")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusAccepted {
		t.Fatalf("create failed: %d", createRec.Code)
	}
	var created map[string]any
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)
	postID, _ := created["postId"].(string)

	delReq := httptest.NewRequest("DELETE", "/content/posts/"+postID, nil)
	setActorHeaders(delReq, "u_delete", "u_delete")
	delRec := httptest.NewRecorder()
	handler.ServeHTTP(delRec, delReq)
	if delRec.Code != http.StatusOK {
		t.Fatalf("delete failed: %d", delRec.Code)
	}

	getReq := httptest.NewRequest("GET", "/content/posts/"+postID, nil)
	getRec := httptest.NewRecorder()
	handler.ServeHTTP(getRec, getReq)
	if getRec.Code != http.StatusGone {
		t.Fatalf("expected 410 for deleted tombstone, got %d", getRec.Code)
	}
	var deletedFailure map[string]any
	if err := json.Unmarshal(getRec.Body.Bytes(), &deletedFailure); err != nil {
		t.Fatalf("decode tombstone failure: %v", err)
	}
	if deletedFailure["code"] != "CONTENT.USER.content_deleted" {
		t.Fatalf("tombstone read must map content_deleted, got %v", deletedFailure)
	}
}

// TestGetPostTombstoneReturnsGone 锁定墓碑 410 契约：聚合文档消失后（保留期内）
// 读取仍按持久墓碑返回 content_deleted，而不是 404。
func TestGetPostTombstoneReturnsGone(t *testing.T) {
	redis := testsupport.NewFakeRedis()
	hotPath := rtrec.NewHotPath(redis)
	store := testsupport.NewPostStore(recinfra.DefaultSeedPosts())
	source := recinfra.NewPostProjectionSource(store, store)
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source})
	feedService := feedapp.NewFeedService(
		engine,
		testsupport.NewPostFeedReader(store),
		feedapp.WithFeedViewerBlockReader(allowAllFeedViewerBlockReader{}),
	)
	postService := postapp.NewPostService(
		postapp.BindDataPorts(store),
		postapp.WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	behaviorService := behaviorapp.NewBehaviorService(hotPath, store)
	postQueryService := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail:     localPostDetailReader{store: store},
		Tombstones: store,
	})
	handler := NewContentHandler(
		feedService,
		postapp.BindFacades(postService),
		postQueryService,
		nil,
		nil,
		nil,
		behaviorService,
	).Routes()

	createReq := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-gone","localDraftId":"draft-gone","contentType":"micro","body":"tombstone body","visibility":"public"}`),
	)
	setActorHeaders(createReq, "u_gone", "u_gone")
	createReq.Header.Set("Idempotency-Key", "intent-gone")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusAccepted {
		t.Fatalf("create failed: %d", createRec.Code)
	}
	var created map[string]any
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)
	postID, _ := created["postId"].(string)

	delReq := httptest.NewRequest("DELETE", "/content/posts/"+postID, nil)
	setActorHeaders(delReq, "u_gone", "u_gone")
	delRec := httptest.NewRecorder()
	handler.ServeHTTP(delRec, delReq)
	if delRec.Code != http.StatusOK {
		t.Fatalf("delete failed: %d", delRec.Code)
	}

	// 模拟保留期内聚合文档已被清理（隐私硬删/TTL 前置）：墓碑仍是持久事实。
	store.RemovePostDocumentForTest(postID)

	getReq := httptest.NewRequest("GET", "/content/posts/"+postID, nil)
	getRec := httptest.NewRecorder()
	handler.ServeHTTP(getRec, getReq)
	if getRec.Code != http.StatusGone {
		t.Fatalf("tombstone-only read must return 410, got %d", getRec.Code)
	}

	// 不存在也无墓碑的 postId 仍回 404。
	missReq := httptest.NewRequest("GET", "/content/posts/never-existed", nil)
	missRec := httptest.NewRecorder()
	handler.ServeHTTP(missRec, missReq)
	if missRec.Code != http.StatusNotFound {
		t.Fatalf("missing post without tombstone must return 404, got %d", missRec.Code)
	}
}

func TestRetiredPostCircleMutationRouteIsAbsent(t *testing.T) {
	handler := newTestHandler()
	circleReq := httptest.NewRequest(
		"PATCH",
		"/content/posts/post-retired-route/circles",
		bytes.NewBufferString(`{"add":["circle_a"]}`),
	)
	setActorHeaders(circleReq, "author1", "author1")
	circleRec := httptest.NewRecorder()
	handler.ServeHTTP(circleRec, circleReq)
	if circleRec.Code != http.StatusNotFound {
		t.Fatalf("retired Post circle mutation route must be absent, got %d", circleRec.Code)
	}
}

func TestPostDetailProjectionUsesCanonicalMediaURLsWire(t *testing.T) {
	wire := ProjectPostDetailForClient(postports.PostDetailSlice{
		PostID:      postports.NewPostID("post_media_wire"),
		ContentType: postports.ContentType("image"),
		MediaURLs:   []string{"media/image/s/asset/example/v1/source.jpg"},
	})
	payload, err := json.Marshal(wire)
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatal(err)
	}
	if _, found := decoded["imageUrls"]; found {
		t.Fatalf("post detail must not expose non-canonical imageUrls: %s", payload)
	}
	mediaURLs, found := decoded["mediaUrls"].([]any)
	if !found || len(mediaURLs) != 1 || mediaURLs[0] != "media/image/s/asset/example/v1/source.jpg" {
		t.Fatalf("post detail mediaUrls mismatch: %s", payload)
	}
}
