// readiness_case: promote-post-to-work-local
// readiness_case: update-post-settings-local
// readiness_case: delete-post-local
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/spec.md#sit-002
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-008
// readiness_case: submit-post-publication-local
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
// readiness_case: get-feed-local
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-004
// readiness_case: get-app-config-local
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-005
// readiness_case: get-author-impact-local
// readiness_case: list-author-impact-evidence-local
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-015
// readiness_case: get-counters-local
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-001
// readiness_case: get-my-footprint-local
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-005
// readiness_case: get-entity-wishlist-state-local
package http_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	"strconv"
	"strings"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	commenttestsupport "quwoquan_service/services/content-service/internal/content/comment/infrastructure/testsupport"
	behaviorhttp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/adapters/inbound/http"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	behaviormodel "quwoquan_service/services/content-service/internal/content/content_behavior_fact/domain/model"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postappports "quwoquan_service/services/content-service/internal/content/post/application/ports"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	reporthttp "quwoquan_service/services/content-service/internal/trust_safety/report/adapters/inbound/http"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	feedsupport "quwoquan_service/services/content-service/tests/support"
)

type localAuthorImpactReader struct{}

func (localAuthorImpactReader) GetSummary(
	_ context.Context,
	authorID string,
	_ int64,
) (postappports.AuthorImpactSummary, error) {
	return postappports.AuthorImpactSummary{
		AuthorID: authorID,
		Total:    3,
		Items: []postappports.AuthorImpactItem{{
			ImpactID:  "impact-community",
			HelpType:  "community",
			Action:    "join_circle",
			Source:    "behavior_fact",
			Count:     3,
			UpdatedAt: time.Now().UTC(),
		}},
	}, nil
}

func (localAuthorImpactReader) ListPageWithTotal(
	_ context.Context,
	_ string,
	impactID string,
	_ string,
	_ int64,
) ([]postappports.AuthorImpactEvidenceRaw, string, bool, int64, error) {
	return []postappports.AuthorImpactEvidenceRaw{{
		EvidenceID: "evidence-community",
		ImpactID:   impactID,
		ContentID:  "post_photo_001",
		HelpType:   "community",
		Action:     "join_circle",
		OccurredAt: time.Now().UTC(),
	}}, "", false, 1, nil
}

type localFootprintStore struct {
	facts []behaviormodel.Fact
}

func (store *localFootprintStore) InsertBatch(
	_ context.Context,
	facts []behaviormodel.Fact,
) error {
	store.facts = append(store.facts, facts...)
	return nil
}

func (store *localFootprintStore) ListUserFootprint(
	_ context.Context,
	userID string,
	actions []string,
	_ time.Time,
	limit int,
) ([]behaviormodel.Fact, error) {
	actionSet := make(map[string]struct{}, len(actions))
	for _, action := range actions {
		actionSet[action] = struct{}{}
	}
	result := make([]behaviormodel.Fact, 0, len(store.facts))
	for _, fact := range store.facts {
		if fact.UserID != userID {
			continue
		}
		if _, ok := actionSet[fact.Action]; !ok {
			continue
		}
		result = append(result, fact)
		if len(result) >= limit {
			break
		}
	}
	return result, nil
}

type localWishlistStateReader struct {
	wishlisted bool
}

func (reader localWishlistStateReader) IsWishlisted(
	context.Context,
	string,
	string,
	string,
) (bool, error) {
	return reader.wishlisted, nil
}

type allowAllFeedViewerBlockReader struct{}

func (allowAllFeedViewerBlockReader) ListBlockedPersonaIDs(
	_ context.Context,
	_ string,
) ([]string, error) {
	return []string{}, nil
}

type readyFeedActiveSupplyReader struct{}

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
	seedPosts := recinfra.DefaultSeedPosts()
	store := testsupport.NewPostStore(seedPosts)
	candidates := make([]rtrec.ContentCandidate, 0, len(seedPosts))
	for _, post := range seedPosts {
		candidates = append(candidates, rtrec.ContentCandidate{
			ContentID:    post.ID,
			ContentType:  post.ContentType,
			AuthorID:     post.AuthorId,
			Title:        post.Title,
			Tags:         append([]string(nil), post.TagRefs...),
			PublishedAt:  post.PublishedAt,
			ViewCount:    post.ViewCount,
			LikeCount:    post.LikeCount,
			CommentCount: post.CommentCount,
			ShareCount:   post.ShareCount,
		})
	}
	rankedEngine := rtrec.NewEngine(
		hotPath,
		[]rtrec.CandidateSource{handlerCandidateSource{candidates: candidates}},
	)
	feedService := feedapp.NewFeedService(
		testsupport.NewPostFeedReader(store),
		feedsupport.RankedRecommendationOptions(
			rankedEngine,
			feedapp.WithFeedViewerBlockReader(allowAllFeedViewerBlockReader{}),
			feedapp.WithActiveSupplyReader(readyFeedActiveSupplyReader{}),
			feedapp.WithFeedDeliveryPageStore(
				deliveryredis.NewStore(rtredis.NewMemoryClient()),
			),
		)...,
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
		reporthttp.NewHandler(reportapp.BindFacades(reportService)),
		behaviorService,
		WithContentBehaviorHandler(behaviorhttp.NewHandler(behaviorService)),
	).Routes()
	return handler, hotPath
}

type handlerCandidateSource struct {
	candidates []rtrec.ContentCandidate
}

func (source handlerCandidateSource) Recall(
	_ context.Context,
	request rtrec.RecallRequest,
) ([]rtrec.ContentCandidate, error) {
	limit := request.Limit
	if limit <= 0 || limit > len(source.candidates) {
		limit = len(source.candidates)
	}
	return append([]rtrec.ContentCandidate(nil), source.candidates[:limit]...), nil
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
	if _, privateStorageID := postBody["_id"]; privateStorageID {
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
	var typed postapp.AppConfigSlice
	if err := json.Unmarshal(rec.Body.Bytes(), &typed); err != nil {
		t.Fatalf("decode typed app config response: %v", err)
	}
	if typed.Schema != "app_remote_config" || typed.ConfigHash == "" {
		t.Fatalf("invalid typed app config identity: %+v", typed)
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

func TestAuthorImpactOperationsUseTheBoundProjectionReader(t *testing.T) {
	handler := NewContentHandler(
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		WithAuthorImpactProjectionReader(localAuthorImpactReader{}),
	).Routes()

	summaryRequest := httptest.NewRequest(
		http.MethodGet,
		"/content/personas/author-impact-local/author-impact?limit=5",
		nil,
	)
	summaryRequest.Header.Set("X-Client-User-Id", "author-impact-local")
	summaryRecorder := httptest.NewRecorder()
	handler.ServeHTTP(summaryRecorder, summaryRequest)
	if summaryRecorder.Code != http.StatusOK {
		t.Fatalf(
			"GetAuthorImpact status=%d body=%s",
			summaryRecorder.Code,
			summaryRecorder.Body.String(),
		)
	}
	var summary postappports.AuthorImpactSummary
	if err := json.Unmarshal(summaryRecorder.Body.Bytes(), &summary); err != nil {
		t.Fatal(err)
	}
	if summary.AuthorID != "author-impact-local" ||
		summary.Total != 3 ||
		len(summary.Items) != 1 {
		t.Fatalf("GetAuthorImpact summary=%+v", summary)
	}

	evidenceRequest := httptest.NewRequest(
		http.MethodGet,
		"/content/personas/author-impact-local/author-impact/evidence?impactId=impact-community&limit=5",
		nil,
	)
	evidenceRequest.Header.Set("X-Client-User-Id", "author-impact-local")
	evidenceRecorder := httptest.NewRecorder()
	handler.ServeHTTP(evidenceRecorder, evidenceRequest)
	if evidenceRecorder.Code != http.StatusOK {
		t.Fatalf(
			"ListAuthorImpactEvidence status=%d body=%s",
			evidenceRecorder.Code,
			evidenceRecorder.Body.String(),
		)
	}
	var evidence struct {
		ImpactID string `json:"impactId"`
		Total    int64  `json:"totalCount"`
		Items    []any  `json:"items"`
		HasMore  bool   `json:"hasMore"`
		Snapshot string `json:"evidenceSnapshotId"`
	}
	if err := json.Unmarshal(evidenceRecorder.Body.Bytes(), &evidence); err != nil {
		t.Fatal(err)
	}
	if evidence.ImpactID != "impact-community" ||
		evidence.Snapshot != "impact-community" ||
		evidence.Total != 1 ||
		len(evidence.Items) != 1 ||
		evidence.HasMore {
		t.Fatalf("ListAuthorImpactEvidence page=%+v", evidence)
	}
}

func TestGetCountersUsesCommentOwnedAuthoritativeCount(t *testing.T) {
	postStore := testsupport.NewPostStore(recinfra.DefaultSeedPosts())
	commentStore := commenttestsupport.NewStore()
	postService := postapp.NewPostService(
		postapp.BindDataPorts(postStore),
		postapp.WithCommentReaders(commentStore),
	)
	handler := NewContentHandler(
		nil,
		postapp.BindFacades(postService),
		nil,
		nil,
		nil,
		nil,
		nil,
	).Routes()
	request := httptest.NewRequest(
		http.MethodGet,
		"/content/posts/post_photo_001/counters",
		nil,
	)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("GetCounters status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var counters postapp.PostCounterSlice
	if err := json.Unmarshal(recorder.Body.Bytes(), &counters); err != nil {
		t.Fatal(err)
	}
	if counters.CommentCount != 0 || counters.LikeCount < 0 || counters.ShareCount < 0 {
		t.Fatalf("GetCounters result=%+v", counters)
	}
}

func TestGetMyFootprintHydratesBehaviorFactsThroughThePostRoute(t *testing.T) {
	postStore := testsupport.NewPostStore(recinfra.DefaultSeedPosts())
	now := time.Now().UTC()
	facts := &localFootprintStore{facts: []behaviormodel.Fact{{
		ClientEventID: "footprint-local-event",
		UserID:        "footprint-local-user",
		SessionID:     "footprint-local-session",
		ContentID:     "post_photo_001",
		Action:        "click",
		OccurredAt:    now.Format(time.RFC3339Nano),
		CreatedAt:     now,
	}}}
	behaviorService := behaviorapp.NewBehaviorService(
		nil,
		postStore,
		behaviorapp.WithBehaviorEventStore(facts),
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
	request := httptest.NewRequest(
		http.MethodGet,
		"/content/footprint?type=viewed&limit=10",
		nil,
	)
	request.Header.Set("X-Client-User-Id", "footprint-local-user")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("GetMyFootprint status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var page struct {
		Items []struct {
			PostID string         `json:"postId"`
			Action string         `json:"action"`
			Post   map[string]any `json:"post"`
		} `json:"items"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Items) != 1 ||
		page.Items[0].PostID != "post_photo_001" ||
		page.Items[0].Action != "click" ||
		page.Items[0].Post["postId"] != "post_photo_001" {
		t.Fatalf("GetMyFootprint page=%+v", page)
	}
}

func TestGetEntityWishlistStateUsesTheBehaviorFactReader(t *testing.T) {
	behaviorService := behaviorapp.NewBehaviorService(
		nil,
		nil,
		behaviorapp.WithWishlistStateReader(
			localWishlistStateReader{wishlisted: true},
		),
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
	request := httptest.NewRequest(
		http.MethodGet,
		"/content/entity-wishlist-state?objectId=homepage-local&objectKind=homepage",
		nil,
	)
	request.Header.Set("X-Client-User-Id", "wishlist-local-user")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"GetEntityWishlistState status=%d body=%s",
			recorder.Code,
			recorder.Body.String(),
		)
	}
	var state behaviorapp.EntityWishlistState
	if err := json.Unmarshal(recorder.Body.Bytes(), &state); err != nil {
		t.Fatal(err)
	}
	if state.ObjectID != "homepage-local" ||
		state.ObjectKind != "homepage" ||
		!state.Wishlisted {
		t.Fatalf("GetEntityWishlistState result=%+v", state)
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

	forbiddenReq := httptest.NewRequest("DELETE", "/content/posts/"+postID, nil)
	setActorHeaders(forbiddenReq, "u_delete_intruder", "u_delete_intruder")
	forbiddenReq.Header.Set("Idempotency-Key", "delete-post-forbidden")
	forbiddenRec := httptest.NewRecorder()
	handler.ServeHTTP(forbiddenRec, forbiddenReq)
	if forbiddenRec.Code != http.StatusForbidden ||
		!strings.Contains(forbiddenRec.Body.String(), "CONTENT.USER.forbidden_delete") {
		t.Fatalf("non-owner delete status=%d body=%s", forbiddenRec.Code, forbiddenRec.Body.String())
	}

	delReq := httptest.NewRequest("DELETE", "/content/posts/"+postID, nil)
	setActorHeaders(delReq, "u_delete", "u_delete")
	delReq.Header.Set("Idempotency-Key", "delete-post-stable")
	delRec := httptest.NewRecorder()
	handler.ServeHTTP(delRec, delReq)
	if delRec.Code != http.StatusOK {
		t.Fatalf("delete failed: %d", delRec.Code)
	}
	var deletionReceipt struct {
		PostID   string `json:"postId"`
		Status   string `json:"status"`
		Replayed bool   `json:"replayed"`
	}
	if err := json.Unmarshal(delRec.Body.Bytes(), &deletionReceipt); err != nil || deletionReceipt.PostID != postID || deletionReceipt.Status != "deleted" || deletionReceipt.Replayed {
		t.Fatalf("unexpected deletion receipt: %+v err=%v", deletionReceipt, err)
	}
	replayReq := httptest.NewRequest("DELETE", "/content/posts/"+postID, nil)
	setActorHeaders(replayReq, "u_delete", "u_delete")
	replayReq.Header.Set("Idempotency-Key", "delete-post-stable")
	replayRec := httptest.NewRecorder()
	handler.ServeHTTP(replayRec, replayReq)
	if err := json.Unmarshal(replayRec.Body.Bytes(), &deletionReceipt); replayRec.Code != http.StatusOK || err != nil || !deletionReceipt.Replayed {
		t.Fatalf("delete replay did not return typed replay receipt: code=%d body=%s err=%v", replayRec.Code, replayRec.Body.String(), err)
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
	feedService := feedapp.NewFeedService(
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
		WithContentBehaviorHandler(behaviorhttp.NewHandler(behaviorService)),
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
