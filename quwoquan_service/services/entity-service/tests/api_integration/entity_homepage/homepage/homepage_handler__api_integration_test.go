// spec_ref: specs/feature-tree/object-homepage-network/spec.md#dom-002
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-search-and-picker/spec.md#gwt-001
// readiness_case: search-homepages-api
// readiness_case: apply-homepage-lifecycle-events-api
// readiness_case: list-homepage-candidates-api
// readiness_case: intake-homepage-candidate-api
// readiness_case: suggest-homepage-candidate-api
// readiness_case: publish-homepage-candidate-api
// readiness_case: get-homepage-detail-api
// readiness_case: get-homepage-shell-api
// readiness_case: get-homepage-introduction-api
// readiness_case: get-object-page-bundle-api
// readiness_case: get-entity-impact-api
// readiness_case: get-homepage-review-summary-api
// readiness_case: get-homepage-related-groups-api
// readiness_case: update-claimed-homepage-basics-api
package api_integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepageexternal "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/external"
	entityguard "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/operationguard"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/testsupport"
	claimhttp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/adapters/inbound/http"
	claimapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/application"
	claimpersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/infrastructure/persistence"
	statushttp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/adapters/inbound/http"
	statusapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/application"
	statuspersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/infrastructure/persistence"
)

// trustedPersonaHandler 模拟 generated operation guard 验证通过后的可信上下文注入；
// handler 层只信任 operation.Context，不读取任何 identity header。
func trustedPersonaHandler(next http.Handler, personaID string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx := operation.WithContext(r.Context(), operation.Context{
			OperationID:    "api-integration-test",
			RequestID:      "req-test",
			IdempotencyKey: r.Header.Get("Idempotency-Key"),
			Actor: operation.ActorContext{
				AccountID: personaID + "-account",
				PersonaID: personaID,
			},
		})
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

type homepageClaimGate struct{ service *application.HomepageService }

func (gate homepageClaimGate) FindHomepageState(
	ctx context.Context,
	homepageID string,
) (claimapp.HomepageState, bool, error) {
	status, claimStatus, found, err := gate.service.FindHomepageClaimState(ctx, homepageID)
	return claimapp.HomepageState{Status: status, ClaimStatus: claimStatus}, found, err
}

func newMongoGovernanceHomepageService(
	t *testing.T,
) (*application.HomepageService, *claimapp.Facade, *statusapp.Facade, *statuspersistence.MongoStore) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	container, err := tryRunReviewMongoContainer(ctx)
	if err != nil {
		cancel()
		t.Fatalf("mongo testcontainer unavailable: %v", err)
	}
	t.Cleanup(func() {
		_ = container.Terminate(context.Background())
		cancel()
	})
	uri, err := container.ConnectionString(ctx)
	if err != nil {
		t.Fatalf("mongo connection string: %v", err)
	}
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(uri).SetDirect(true))
	if err != nil {
		t.Fatalf("mongo connect: %v", err)
	}
	t.Cleanup(func() { _ = client.Disconnect(context.Background()) })
	database := client.Database("entity_homepage_governance_http_it")
	homepageStore := homepagepersistence.NewMongoHomepageStore(database)
	claimStore := claimpersistence.NewMongoStore(database)
	statusStore := statuspersistence.NewMongoStore(database)
	for name, ensureIndexes := range map[string]func(context.Context) error{
		"homepage":      homepageStore.EnsureIndexes,
		"claim request": claimStore.EnsureIndexes,
		"status report": statusStore.EnsureIndexes,
	} {
		if err := ensureIndexes(ctx); err != nil {
			t.Fatalf("ensure %s indexes: %v", name, err)
		}
	}
	service := application.NewHomepageServiceWithStore(ctx, homepageStore)
	claimFacade, err := claimapp.NewFacade(claimapp.DataPorts{
		Aggregates: claimStore,
		Receipts:   claimStore,
		Homepages:  homepageClaimGate{service: service},
		Queue:      claimStore,
	})
	if err != nil {
		t.Fatalf("new claim facade: %v", err)
	}
	statusFacade, err := statusapp.NewFacade(statusapp.DataPorts{
		Aggregates: statusStore,
		Receipts:   statusStore,
		Homepages:  service,
		Queue:      statusStore,
	})
	if err != nil {
		t.Fatalf("new status report facade: %v", err)
	}
	return service, claimFacade, statusFacade, statusStore
}

// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/spec.md#sit-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-candidate-intake-and-publish/spec.md#gwt-001
func TestHomepageCandidatePublishAndShell(t *testing.T) {
	homepageService, _, _, _ := newMongoGovernanceHomepageService(t)
	tokenConfig := rtauth.TokenConfig{
		Secret:       []byte("0123456789abcdef0123456789abcdef"),
		Issuer:       "quwoquan.entity.homepage.integration",
		Audience:     "quwoquan-app",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          30 * time.Minute,
		ClockSkew:    30 * time.Second,
	}
	signer, err := rtauth.NewHS256Signer(tokenConfig)
	if err != nil {
		t.Fatalf("new access token signer: %v", err)
	}
	verifier, err := rtauth.NewHS256Verifier(tokenConfig)
	if err != nil {
		t.Fatalf("new access token verifier: %v", err)
	}
	operatorToken, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "entity-governance-operator",
		Roles:     []string{"operator"},
		Scopes:    []string{"ops.case.read", "ops.case.write"},
	})
	if err != nil {
		t.Fatalf("sign operator token: %v", err)
	}
	memberToken, err := signer.Sign(rtauth.TokenSubject{AccountID: "ordinary-account"})
	if err != nil {
		t.Fatalf("sign ordinary account token: %v", err)
	}
	viewerToken, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "homepage-reader",
		PersonaID: "homepage-reader-persona",
	})
	if err != nil {
		t.Fatalf("sign homepage reader token: %v", err)
	}
	server := httptest.NewServer(rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: verifier,
	})(entityguard.Handler(httpadapter.NewHandler(homepageService).Routes())))
	defer server.Close()

	ordinaryHeaders := http.Header{"Authorization": []string{"Bearer " + memberToken}}
	requestJSONWithHeaders(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/candidates",
		nil,
		http.StatusForbidden,
		ordinaryHeaders,
	)
	requestJSONWithHeaders(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/candidates",
		map[string]any{"title": "越权候选主页", "homepageType": "sight"},
		http.StatusForbidden,
		ordinaryHeaders,
	)

	operatorHeaders := http.Header{"Authorization": []string{"Bearer " + operatorToken}}
	candidate := requestJSONWithHeaders(t, server.Client(), http.MethodPost, server.URL+"/homepages/candidates", map[string]any{
		"title":        "测试发布主页",
		"subtitle":     "候选发布验证",
		"homepageType": "sight",
		"city":         "杭州",
		"address":      "西湖边",
	}, http.StatusCreated, operatorHeaders)
	homepageID := stringField(t, candidate, "homepageId")
	candidateQueue := requestJSONWithHeaders(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/candidates?query=测试发布主页&limit=20",
		nil,
		http.StatusOK,
		operatorHeaders,
	)
	if items := sliceField(t, candidateQueue, "items"); len(items) != 1 {
		t.Fatalf("expected candidate in governance queue, got %#v", items)
	}

	suggested := requestJSONWithHeaders(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/candidates/suggest",
		map[string]any{
			"title":        "用户建议主页",
			"homepageType": "city",
			"city":         "杭州",
		},
		http.StatusCreated,
		http.Header{"Authorization": []string{"Bearer " + viewerToken}},
	)
	if got := stringField(t, suggested, "status"); got != "candidate" {
		t.Fatalf("expected suggested candidate status, got %q", got)
	}

	published := requestJSONWithHeaders(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/candidates/"+homepageID+":publish",
		nil,
		http.StatusOK,
		operatorHeaders,
	)
	if got := stringField(t, published, "status"); got != "published" {
		t.Fatalf("expected published status, got %q", got)
	}

	search := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/search?query=测试发布主页&status=published",
		nil,
		http.StatusOK,
	)
	items := sliceField(t, search, "items")
	if len(items) == 0 {
		t.Fatalf("expected published homepage in search results")
	}

	shell := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+homepageID+"/shell",
		nil,
		http.StatusOK,
	)
	if _, ok := shell["homepage"].(map[string]any); !ok {
		t.Fatalf("expected shell.homepage object")
	}
	if _, ok := shell["contentPreview"].([]any); !ok {
		t.Fatalf("expected shell.contentPreview array, got %#v", shell)
	}
	detail := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+homepageID,
		nil,
		http.StatusOK,
	)
	if got := stringField(t, detail, "homepageId"); got != homepageID {
		t.Fatalf("expected homepage detail %q, got %q", homepageID, got)
	}
	introduction := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+homepageID+"/introduction",
		nil,
		http.StatusOK,
	)
	if got := stringField(t, introduction, "homepageId"); got != homepageID {
		t.Fatalf("expected homepage introduction %q, got %q", homepageID, got)
	}
	impact := requestJSONWithHeaders(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+homepageID+"/impact",
		nil,
		http.StatusOK,
		http.Header{"Authorization": []string{"Bearer " + viewerToken}},
	)
	if got := stringField(t, impact, "homepageId"); got != homepageID {
		t.Fatalf("expected homepage impact %q, got %q", homepageID, got)
	}
	reviewSummary := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+homepageID+"/review-summary",
		nil,
		http.StatusOK,
	)
	if got := intField(t, reviewSummary, "ratingCount"); got != 0 {
		t.Fatalf("expected empty review summary, got ratingCount=%d", got)
	}
	relatedGroups := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+homepageID+"/related-groups",
		nil,
		http.StatusOK,
	)
	if groups := sliceField(t, relatedGroups, "groups"); len(groups) != 0 {
		t.Fatalf("new homepage must not synthesize related groups: %#v", groups)
	}

	bundle := requestJSONWithHeaders(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+homepageID+"/object-page-bundle?referralSource=test&feedRequestId=feed-1&recommendationTraceId=trace-1&experimentBucket=A&rolloutCohort=cohort-a",
		nil,
		http.StatusOK,
		http.Header{"Authorization": []string{"Bearer " + viewerToken}},
	)
	if got := stringField(t, bundle, "objectType"); got != "homepage" {
		t.Fatalf("expected homepage objectType, got %q", got)
	}
	if got := stringField(t, bundle, "canonicalEntityId"); got == "" {
		t.Fatalf("expected canonicalEntityId in bundle")
	}
	if edges := sliceField(t, bundle, "relationEdges"); len(edges) != 0 {
		t.Fatalf("candidate without relation facts must return empty relationEdges: %#v", edges)
	}
	if _, exists := bundle["assistantContext"]; exists {
		t.Fatalf("candidate without assistant projection must not synthesize assistantContext")
	}
	rolloutContext, ok := bundle["rolloutContext"].(map[string]any)
	if !ok {
		t.Fatalf("expected rolloutContext object")
	}
	if rolloutContext["cohort"] != "cohort-a" {
		t.Fatalf("expected rollout cohort propagated, got %v", rolloutContext["cohort"])
	}
}

func TestHomepageTypeSupportsCampusAndTravelPhoto(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	for _, item := range []struct {
		id               string
		expectedType     string
		expectedTemplate string
	}{
		{
			id:               "fixture_homepage_university_pku",
			expectedType:     "university",
			expectedTemplate: "campus",
		},
		{
			id:               "fixture_homepage_travel_photo_west_lake",
			expectedType:     "travel_photo",
			expectedTemplate: "travel_photo",
		},
	} {
		bundle := requestJSON(
			t,
			server.Client(),
			http.MethodGet,
			server.URL+"/homepages/"+item.id+"/object-page-bundle",
			nil,
			http.StatusOK,
		)
		if got := stringField(t, bundle, "objectPageTemplate"); got != item.expectedTemplate {
			t.Fatalf("expected template %q for %s, got %q", item.expectedTemplate, item.id, got)
		}
		if got := stringField(t, bundle, "canonicalEntityId"); got == "" {
			t.Fatalf("expected canonicalEntityId for %s", item.id)
		}
		detail := requestJSON(
			t,
			server.Client(),
			http.MethodGet,
			server.URL+"/homepages/"+item.id,
			nil,
			http.StatusOK,
		)
		if got := stringField(t, detail, "homepageType"); got != item.expectedType {
			t.Fatalf("expected homepageType %q for %s, got %q", item.expectedType, item.id, got)
		}
	}
}

func TestHomepageDetailSupportsSemanticCanonicalLookup(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	const canonicalID = "entity:sight:west_lake"

	detail := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+canonicalID,
		nil,
		http.StatusOK,
	)
	if got := stringField(t, detail, "homepageId"); got != "homepage_sight_west_lake" {
		t.Fatalf("expected semantic canonical detail to resolve west lake, got %q", got)
	}

	introduction := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+canonicalID+"/introduction",
		nil,
		http.StatusOK,
	)
	if got := stringField(t, introduction, "homepageId"); got != "homepage_sight_west_lake" {
		t.Fatalf("expected semantic canonical introduction to resolve west lake, got %q", got)
	}

	bundle := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+canonicalID+"/object-page-bundle",
		nil,
		http.StatusOK,
	)
	if got := stringField(t, bundle, "objectId"); got != "homepage_sight_west_lake" {
		t.Fatalf("expected semantic canonical bundle to resolve west lake, got %q", got)
	}
	if got := stringField(t, bundle, "canonicalEntityId"); got != "entity:sight:west_lake" {
		t.Fatalf("expected semantic canonical bundle id entity:sight:west_lake, got %q", got)
	}
}

func TestHomepageImpactReturnsStructuredSummary(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	impact := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/homepage_sight_west_lake/impact",
		nil,
		http.StatusOK,
	)
	if got := stringField(t, impact, "homepageId"); got != "homepage_sight_west_lake" {
		t.Fatalf("expected homepageId homepage_sight_west_lake, got %q", got)
	}
	if got := intField(t, impact, "total"); got <= 0 {
		t.Fatalf("expected positive total, got %d", got)
	}
	items := sliceField(t, impact, "items")
	if len(items) == 0 {
		t.Fatalf("expected impact items")
	}
	first, ok := items[0].(map[string]any)
	if !ok {
		t.Fatalf("expected first impact item map, got %T", items[0])
	}
	primaryText := stringField(t, first, "primaryText")
	if primaryText == "" {
		t.Fatalf("expected non-empty primaryText")
	}
	spans := sliceField(t, first, "primarySpans")
	joined := ""
	hasCircleObjectSpan := false
	for _, raw := range spans {
		span, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("expected primary span map, got %T", raw)
		}
		joined += stringField(t, span, "text")
		if stringField(t, span, "role") == "object" {
			target, _ := span["target"].(map[string]any)
			hasCircleObjectSpan = target != nil && stringField(t, target, "objectType") == "circle" && stringField(t, target, "objectId") == "fixture_circle_photo"
		}
	}
	if joined != primaryText || !hasCircleObjectSpan {
		t.Fatalf("invalid primarySpans: joined=%q primary=%q spans=%+v", joined, primaryText, spans)
	}
	representative, ok := first["representativeActor"].(map[string]any)
	if !ok || stringField(t, representative, "displayName") != "契约摄影社主理人" || stringField(t, representative, "relationLabel") != "圈子主理人" {
		t.Fatalf("expected relationship-qualified representative actor, got %+v", first["representativeActor"])
	}
	actorTarget, _ := representative["target"].(map[string]any)
	if actorTarget == nil || stringField(t, actorTarget, "objectType") != "user" || stringField(t, actorTarget, "objectId") != "fixture_user_owner" {
		t.Fatalf("expected routable user actor target, got %+v", representative["target"])
	}
	actionHints := sliceField(t, first, "actionHints")
	if len(actionHints) == 0 {
		t.Fatalf("expected actionHints")
	}
	actionHint, ok := actionHints[0].(map[string]any)
	if !ok {
		t.Fatalf("expected action hint map, got %T", actionHints[0])
	}
	target, ok := actionHint["target"].(map[string]any)
	if !ok {
		t.Fatalf("expected action hint target map, got %T", actionHint["target"])
	}
	if got := stringField(t, target, "objectId"); got != "fixture_circle_photo" {
		t.Fatalf("expected action target fixture_circle_photo, got %q", got)
	}
}

func TestHomepageObjectPageBundleRequestsCanonicalEntityScopedIntersections(t *testing.T) {
	var gotObjectID string
	var gotObjectType string
	var gotViewerID string
	tokenConfig := entityDelegatedTokenConfig()
	verifier, err := rtauth.NewHS256Verifier(tokenConfig)
	if err != nil {
		t.Fatalf("new delegated verifier: %v", err)
	}
	contentServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotObjectID = r.URL.Query().Get("objectId")
		gotObjectType = r.URL.Query().Get("objectType")
		token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		claims, verifyErr := verifier.Verify(token)
		if verifyErr != nil {
			t.Errorf("verify delegated token: %v", verifyErr)
		} else {
			gotViewerID = claims.Persona
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"items": []map[string]any{
				{
					"intersectionId":            "remote_homepage_reason",
					"actionTargetId":            "homepage_sight_west_lake",
					"primaryText":               "顾南等2位你关注的人来过西湖景区",
					"sourceRefs":                []string{"internal/source"},
					"primaryEvidenceRef":        "internal/evidence",
					"actorEvidenceTotalCount":   2,
					"actorEvidenceCompleteness": "complete",
					"representativeActor": map[string]any{
						"actorId":       "user_gu_nan",
						"displayName":   "顾南",
						"relationLabel": "你关注的人",
						"target": map[string]any{
							"objectType": "user",
							"objectId":   "user_gu_nan",
							"objectKind": "person",
							"routeId":    "userProfile",
						},
					},
					"primarySpans": []map[string]any{
						{
							"text": "顾南", "role": "object",
							"target": map[string]any{
								"objectType": "user",
								"objectId":   "user_gu_nan",
								"objectKind": "person",
								"routeId":    "userProfile",
							},
						},
						{"text": "等2位你关注的人来过", "role": "plain"},
						{
							"text": "西湖景区", "role": "object",
							"target": map[string]any{
								"objectType": "homepage",
								"objectId":   "homepage_sight_west_lake",
								"objectKind": "place",
								"routeId":    "homepageDetail",
							},
						},
					},
					"actionHints": []map[string]any{
						{
							"actionKey": "view_object",
							"label":     "查看对象",
							"target": map[string]any{
								"objectType": "homepage",
								"objectId":   "homepage_sight_west_lake",
								"objectKind": "place",
								"routeId":    "homepageDetail",
							},
						},
					},
				},
			},
		})
	}))
	defer contentServer.Close()
	credentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		tokenConfig,
		"entity-service",
		[]string{"content.object_intersections.read"},
	)
	if err != nil {
		t.Fatalf("new delegated credentials: %v", err)
	}
	intersectionReader, err := homepageexternal.NewContentIntersectionReader(
		homepageexternal.ContentIntersectionConfig{
			BaseURL:                 contentServer.URL,
			ObjectIntersectionsPath: "/content/intersections/object",
			Authorization:           credentials,
		},
	)
	if err != nil {
		t.Fatalf("new content intersection reader: %v", err)
	}

	server := httptest.NewServer(trustedPersonaHandler(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageServiceWithOptions(
			application.WithIntersectionReader(intersectionReader),
		)).Routes(),
		"fixture_user_current",
	))
	defer server.Close()

	req, err := http.NewRequest(
		http.MethodGet,
		server.URL+"/homepages/homepage_sight_west_lake/object-page-bundle",
		nil,
	)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	resp, err := server.Client().Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}
	var bundle map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&bundle); err != nil {
		t.Fatalf("decode bundle: %v", err)
	}
	if gotObjectID != "entity:sight:west_lake" {
		t.Fatalf("expected canonical entity objectId request, got %q", gotObjectID)
	}
	if gotObjectType != "sight" {
		t.Fatalf("expected homepage type objectType request, got %q", gotObjectType)
	}
	if gotViewerID != "fixture_user_current" {
		t.Fatalf("expected viewer header to propagate, got %q", gotViewerID)
	}
	reasons := sliceField(t, bundle, "intersectionReasons")
	if len(reasons) == 0 {
		t.Fatalf("expected remote intersection reasons in bundle")
	}
	first, ok := reasons[0].(map[string]any)
	if !ok {
		t.Fatalf("expected first reason map, got %T", reasons[0])
	}
	if got := stringField(t, first, "intersectionId"); got != "remote_homepage_reason" {
		t.Fatalf("expected remote reason passthrough, got %q", got)
	}
	for _, forbidden := range []string{"sourceRefs", "primaryEvidenceRef"} {
		if _, leaked := first[forbidden]; leaked {
			t.Fatalf("remote reason leaked %s", forbidden)
		}
	}
}

func entityDelegatedTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("entity-api-integration-secret-at-least-32-bytes"),
		Issuer:       "quwoquan-test",
		Audience:     "quwoquan-test",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
		ClockSkew:    time.Second,
	}
}

func TestHomepageObjectPageBundleWithoutIntersectionDataIsHonestlyEmpty(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	bundle := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/homepage_sight_west_lake/object-page-bundle",
		nil,
		http.StatusOK,
	)
	reasons := sliceField(t, bundle, "intersectionReasons")
	if len(reasons) != 0 {
		t.Fatalf("missing dependency data must not synthesize reasons: %#v", reasons)
	}
}

func TestHomepageIntroductionReturnsStructuredLongFormContent(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	introduction := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/homepage_sight_west_lake/introduction",
		nil,
		http.StatusOK,
	)
	if got := stringField(t, introduction, "homepageId"); got != "homepage_sight_west_lake" {
		t.Fatalf("expected west lake introduction, got %q", got)
	}
	if got := stringField(t, introduction, "displayName"); got != "西湖景区" {
		t.Fatalf("expected displayName 西湖景区, got %q", got)
	}
	if got := stringField(t, introduction, "summary"); got == "" {
		t.Fatalf("expected introduction summary")
	}
	if _, ok := introduction["sourceRefs"]; ok {
		t.Fatalf("internal sourceRefs must not be exposed by introduction API")
	}
	sections := sliceField(t, introduction, "sections")
	if len(sections) == 0 || len(sections) > 2 {
		t.Fatalf("expected only field-derived overview/keyFacts sections, got %d", len(sections))
	}
	kinds := map[string]bool{}
	for _, raw := range sections {
		section, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("expected section object, got %T", raw)
		}
		kind := stringField(t, section, "kind")
		if !isAllowedIntroductionKind(kind) {
			t.Fatalf("unexpected section kind %q", kind)
		}
		kinds[kind] = true
	}
	for _, kind := range []string{"overview", "keyFacts"} {
		if !kinds[kind] {
			t.Fatalf("expected section kind %s in %#v", kind, kinds)
		}
	}
	for _, forbidden := range []string{"timeline", "history"} {
		if kinds[forbidden] {
			t.Fatalf("introduction must not synthesize %s", forbidden)
		}
	}
	related := sliceField(t, introduction, "relatedObjects")
	if len(related) == 0 {
		t.Fatalf("expected relatedObjects")
	}
}

func TestHomepageIntroductionProjectsIntakenPageMarkdown(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	pageMarkdown := "---\ntitle: 都江堰\ncoverImage: asset://cover_asset\n---\n" +
		"# 都江堰\n\n都江堰是战国时期修建的大型水利工程。\n\n" +
		"## 历史沿革\n\n李冰父子主持修建。\n\n" +
		":::figure id=\"fig_01\" layout=\"fullWidth\" caption=\"鱼嘴分水堤\"\nasset://inline_asset_1\n:::\n\n" +
		"## 相关图片\n\n:::gallery layout=\"grid\"\nasset://related_asset_1\n:::\n"
	candidate := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/homepages/candidates", map[string]any{
		"title":                "都江堰",
		"homepageType":         "sight",
		"introductionMarkdown": pageMarkdown,
		"introductionAssets": []map[string]any{
			{"assetId": "cover_asset", "url": "https://cdn.example.com/cover.jpg", "caption": "都江堰全景", "role": "cover"},
			{"assetId": "inline_asset_1", "url": "https://cdn.example.com/inline1.jpg", "caption": "鱼嘴分水堤"},
			{"assetId": "related_asset_1", "url": "https://cdn.example.com/rel1.jpg"},
		},
	}, http.StatusCreated)
	homepageID := stringField(t, candidate, "homepageId")
	if got := stringField(t, candidate, "coverUrl"); got != "https://cdn.example.com/cover.jpg" {
		t.Fatalf("expected cover derived from role=cover asset, got %q", got)
	}

	introduction := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+homepageID+"/introduction",
		nil,
		http.StatusOK,
	)
	if got := stringField(t, introduction, "coverUrl"); got != "https://cdn.example.com/cover.jpg" {
		t.Fatalf("expected frontmatter cover url, got %q", got)
	}
	sections := sliceField(t, introduction, "sections")
	var bodySection, relatedSection map[string]any
	for _, raw := range sections {
		section, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("expected section object, got %T", raw)
		}
		kind := stringField(t, section, "kind")
		if !isAllowedIntroductionKind(kind) {
			t.Fatalf("unexpected section kind %q", kind)
		}
		switch kind {
		case "body":
			bodySection = section
		case "relatedImages":
			relatedSection = section
		}
	}
	if bodySection == nil {
		t.Fatalf("expected body section projected from page.md, got %#v", sections)
	}
	body, _ := bodySection["bodyMarkdown"].(string)
	if !strings.Contains(body, `:::figure id="fig_01"`) {
		t.Fatalf("body markdown must preserve figure directive, got %q", body)
	}
	bodyAssets := sliceField(t, bodySection, "assets")
	if len(bodyAssets) != 1 {
		t.Fatalf("expected one inline asset binding, got %#v", bodyAssets)
	}
	if inline, ok := bodyAssets[0].(map[string]any); !ok || inline["role"] != "inline" {
		t.Fatalf("expected inline role binding, got %#v", bodyAssets[0])
	}
	if relatedSection == nil {
		t.Fatalf("expected relatedImages section, got %#v", sections)
	}
	relatedAssets := sliceField(t, relatedSection, "assets")
	if len(relatedAssets) != 1 {
		t.Fatalf("expected related gallery asset, got %#v", relatedAssets)
	}
	if related, ok := relatedAssets[0].(map[string]any); !ok || related["role"] != "related" {
		t.Fatalf("expected related role binding, got %#v", relatedAssets[0])
	}
}

func TestHomepageIntroductionReturnsNotFoundForUnknownHomepage(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	resp, err := server.Client().Get(server.URL + "/homepages/missing-homepage/introduction")
	if err != nil {
		t.Fatalf("get introduction: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 for missing homepage, got %d", resp.StatusCode)
	}
}

// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-claim-request-and-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-offline-report-and-history-retention/spec.md#gwt-001
func TestHomepageGovernanceLifecycle(t *testing.T) {
	homepageService, claimFacade, statusFacade, statusStore := newMongoGovernanceHomepageService(t)
	handler := httpadapter.NewHandler(homepageService).
		WithClaimRequestHandler(claimhttp.NewHandler(claimFacade)).
		WithStatusReportHandler(statushttp.NewHandler(statusFacade))
	server := httptest.NewServer(trustedPersonaHandler(
		handler.Routes(),
		"fixture_operator",
	))
	defer server.Close()

	candidate := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/homepages/candidates", map[string]any{
		"title":        "测试治理主页",
		"subtitle":     "认领与下线验证",
		"homepageType": "hotel",
		"city":         "杭州",
		"address":      "龙井路 18 号",
	}, http.StatusCreated)
	homepageID := stringField(t, candidate, "homepageId")
	candidateQueue := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/candidates?limit=20",
		nil,
		http.StatusOK,
	)
	if items := sliceField(t, candidateQueue, "items"); len(items) != 1 {
		t.Fatalf("expected candidate governance queue item, got %#v", items)
	}
	requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/candidates/"+homepageID+":publish",
		nil,
		http.StatusOK,
	)

	unsafeClaim := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/"+homepageID+"/claim-requests",
		map[string]any{
			"claimTier":          "basic",
			"contactPhone":       "13800000000",
			"businessLicenseUrl": "javascript:alert(document.domain)",
		},
		http.StatusBadRequest,
	)
	if got := stringField(t, unsafeClaim, "code"); got != "ENTITY.USER.invalid_claim_material_url" {
		t.Fatalf("unsafe claim material URL must return canonical 400 code, got %q", got)
	}

	unsafeReport := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/"+homepageID+"/status-reports",
		map[string]any{
			"reason":       "offline",
			"evidenceUrls": []string{"http://assets.test/offline-proof"},
		},
		http.StatusBadRequest,
	)
	if got := stringField(t, unsafeReport, "code"); got != "ENTITY.USER.invalid_status_report_evidence_url" {
		t.Fatalf("unsafe status-report evidence URL must return canonical 400 code, got %q", got)
	}

	claim := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/"+homepageID+"/claim-requests",
		map[string]any{
			"claimTier":          "basic",
			"contactPhone":       "13800000000",
			"businessLicenseUrl": "https://assets.test/license",
			"note":               "governance test",
		},
		http.StatusCreated,
	)
	claimID := stringField(t, claim, "claimRequestId")
	if got := stringField(t, claim, "status"); got != "pending_review" {
		t.Fatalf("expected pending_review claim, got %q", got)
	}
	claimQueue := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepage-claim-requests?status=pending_review&limit=20",
		nil,
		http.StatusOK,
	)
	claimItems := sliceField(t, claimQueue, "items")
	if len(claimItems) != 1 ||
		stringField(t, claimItems[0].(map[string]any), "claimRequestId") != claimID {
		t.Fatalf("expected pending claim in governance queue, got %#v", claimItems)
	}
	lifecycleHandler := application.NewHomepageLifecycleHandler(homepageService)
	if err := lifecycleHandler.ApplyClaimRequestedProjection(
		context.Background(),
		"test-claim-requested",
		homepageID,
	); err != nil {
		t.Fatalf("project claim requested: %v", err)
	}

	claimReview := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/"+homepageID+"/claim-requests/"+claimID+":review",
		map[string]any{
			"status":     "approved",
			"reviewNote": "ok",
		},
		http.StatusOK,
	)
	if got := stringField(t, claimReview, "status"); got != "approved" {
		t.Fatalf("expected approved claim review, got %q", got)
	}
	if err := lifecycleHandler.ApplyClaimReviewedProjection(
		context.Background(),
		"test-claim-reviewed",
		homepageID,
		"fixture_operator",
		true,
	); err != nil {
		t.Fatalf("project claim reviewed: %v", err)
	}
	averageRating := 4.9
	if err := lifecycleHandler.ApplyReviewSummary(
		context.Background(),
		homepageID,
		&averageRating,
		18,
		[]string{"位置优越", "服务稳定"},
	); err != nil {
		t.Fatalf("project review summary: %v", err)
	}
	reviewSummary, err := homepageService.GetHomepageReviewSummary(
		context.Background(),
		homepageID,
	)
	if err != nil || reviewSummary.RatingCount != 18 ||
		reviewSummary.AverageRating == nil || *reviewSummary.AverageRating != averageRating {
		t.Fatalf("review summary projection mismatch: summary=%+v err=%v", reviewSummary, err)
	}

	intruderServer := httptest.NewServer(trustedPersonaHandler(
		httpadapter.NewHandler(homepageService).Routes(),
		"fixture_intruder",
	))
	defer intruderServer.Close()
	requestJSON(
		t,
		intruderServer.Client(),
		http.MethodPatch,
		intruderServer.URL+"/homepages/"+homepageID+"/claimed-basics",
		map[string]any{"subtitle": "越权修改"},
		http.StatusForbidden,
	)

	updated := requestJSON(
		t,
		server.Client(),
		http.MethodPatch,
		server.URL+"/homepages/"+homepageID+"/claimed-basics",
		map[string]any{
			"subtitle":     "已认领并更新",
			"categoryTags": []string{"酒店", "已认领"},
		},
		http.StatusOK,
	)
	if got := stringField(t, updated, "subtitle"); got != "已认领并更新" {
		t.Fatalf("expected updated subtitle, got %q", got)
	}

	report := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/"+homepageID+"/status-reports",
		map[string]any{
			"reason":      "offline",
			"description": "confirm soft offline",
		},
		http.StatusCreated,
	)
	reportID := stringField(t, report, "reportId")
	if got := stringField(t, report, "status"); got != "pending_review" {
		t.Fatalf("expected pending_review status report, got %q", got)
	}
	reportQueue := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepage-status-reports?status=pending_review&limit=20",
		nil,
		http.StatusOK,
	)
	reportItems := sliceField(t, reportQueue, "items")
	if len(reportItems) != 1 ||
		stringField(t, reportItems[0].(map[string]any), "reportId") != reportID {
		t.Fatalf("expected pending status report in governance queue, got %#v", reportItems)
	}

	reportReview := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/"+homepageID+"/status-reports/"+reportID+":review",
		map[string]any{
			"status":     "confirmed_offline",
			"reviewNote": "offline confirmed",
		},
		http.StatusOK,
	)
	if got := stringField(t, reportReview, "status"); got != "confirmed_offline" {
		t.Fatalf("expected confirmed_offline review, got %q", got)
	}
	statusProjector, err := application.NewStatusHomepageProjector(
		statusStore,
		homepageService,
	)
	if err != nil {
		t.Fatalf("construct status lifecycle projector: %v", err)
	}
	processed, err := statusProjector.RunOnce(context.Background(), 10)
	if err != nil || processed != 2 {
		t.Fatalf("project status lifecycle: processed=%d err=%v", processed, err)
	}
	checkpoint, err := statusStore.LoadCheckpoint(
		context.Background(),
		"entity.homepage-status-lifecycle",
	)
	if err != nil || strings.TrimSpace(checkpoint) == "" {
		t.Fatalf("status lifecycle ACK checkpoint=%q err=%v", checkpoint, err)
	}
	if replayed, err := statusProjector.RunOnce(context.Background(), 10); err != nil || replayed != 0 {
		t.Fatalf("status lifecycle replay: processed=%d err=%v", replayed, err)
	}

	offlineDetail := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/"+homepageID,
		nil,
		http.StatusGone,
	)
	if got := stringField(t, offlineDetail, "code"); got != "ENTITY.USER.homepage_offline" {
		t.Fatalf("expected offline runtime error, got %q", got)
	}
}

func isAllowedIntroductionKind(kind string) bool {
	// 与 projections/homepage_introduction_section.yaml 的 kind 闭集同源。
	switch kind {
	case "overview", "keyFacts", "timeline", "history", "relatedPeople",
		"relatedObjects", "map", "gallery", "body", "relatedImages":
		return true
	default:
		return false
	}
}

func TestHomepageInvalidJSONUsesRuntimeErrorResponse(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	req, err := http.NewRequest(
		http.MethodPost,
		server.URL+"/homepages/candidates",
		bytes.NewReader([]byte("{")),
	)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Request-Id", "entity-req-1")
	req.Header.Set("X-Trace-Id", "entity-trace-1")
	resp, err := server.Client().Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", resp.StatusCode)
	}
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if out["code"] != "ENTITY.USER.invalid_argument" {
		t.Fatalf("expected runtime code ENTITY.USER.invalid_argument, got %v", out["code"])
	}
	if out["requestId"] != "entity-req-1" || out["traceId"] != "entity-trace-1" {
		t.Fatalf("expected request/trace propagation, got request=%v trace=%v", out["requestId"], out["traceId"])
	}
	if _, ok := out["origin"].(string); !ok {
		t.Fatalf("expected runtime origin in error response: %#v", out)
	}
	if _, ok := out["location"].(map[string]any); !ok {
		t.Fatalf("expected runtime location in error response: %#v", out)
	}
	if _, ok := out["context"].(map[string]any); !ok {
		t.Fatalf("expected runtime context in error response: %#v", out)
	}
}

func TestHomepageRouteNotFoundUsesRuntimeNotFound(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	req, err := http.NewRequest(
		http.MethodGet,
		server.URL+"/homepages/unknown/not-a-route",
		nil,
	)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	resp, err := server.Client().Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", resp.StatusCode)
	}
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if out["code"] != "GATEWAY.USER.route_not_found" {
		t.Fatalf("expected runtime code GATEWAY.USER.route_not_found, got %v", out["code"])
	}
	if out["kind"] != "notFound" {
		t.Fatalf("expected runtime kind notFound, got %v", out["kind"])
	}
}

func requestJSON(
	t *testing.T,
	client *http.Client,
	method string,
	url string,
	payload any,
	expectedStatus int,
) map[string]any {
	t.Helper()
	return requestJSONWithHeaders(
		t,
		client,
		method,
		url,
		payload,
		expectedStatus,
		nil,
	)
}

func requestJSONWithHeaders(
	t *testing.T,
	client *http.Client,
	method string,
	url string,
	payload any,
	expectedStatus int,
	headers http.Header,
) map[string]any {
	t.Helper()
	var bodyBytes []byte
	var body *bytes.Reader
	if payload == nil {
		body = bytes.NewReader(nil)
	} else {
		raw, err := json.Marshal(payload)
		if err != nil {
			t.Fatalf("marshal payload: %v", err)
		}
		bodyBytes = raw
		body = bytes.NewReader(raw)
	}
	req, err := http.NewRequest(method, url, body)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if method != http.MethodGet {
		digest := sha256.Sum256(
			append([]byte(method+"\x00"+url+"\x00"), bodyBytes...),
		)
		req.Header.Set("Idempotency-Key", hex.EncodeToString(digest[:]))
	}
	for key, values := range headers {
		req.Header.Del(key)
		for _, value := range values {
			req.Header.Add(key, value)
		}
	}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != expectedStatus {
		t.Fatalf("expected status %d, got %d", expectedStatus, resp.StatusCode)
	}
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	return out
}

func stringField(t *testing.T, data map[string]any, key string) string {
	t.Helper()
	value, ok := data[key]
	if !ok {
		t.Fatalf("missing field %q", key)
	}
	str, ok := value.(string)
	if !ok {
		t.Fatalf("field %q is not a string", key)
	}
	return str
}

func sliceField(t *testing.T, data map[string]any, key string) []any {
	t.Helper()
	value, ok := data[key]
	if !ok {
		t.Fatalf("missing field %q", key)
	}
	items, ok := value.([]any)
	if !ok {
		t.Fatalf("field %q is not a slice", key)
	}
	return items
}

func intField(t *testing.T, data map[string]any, key string) int {
	t.Helper()
	value, ok := data[key]
	if !ok {
		t.Fatalf("missing field %q", key)
	}
	switch v := value.(type) {
	case float64:
		return int(v)
	case int:
		return v
	default:
		t.Fatalf("field %q is not a number", key)
		return 0
	}
}
