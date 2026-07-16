package api_integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	httpadapter "quwoquan_service/services/entity-service/internal/adapters/http"
	"quwoquan_service/services/entity-service/internal/application"
)

func TestHomepageCandidatePublishAndShell(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	candidate := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/v1/homepages/candidates", map[string]any{
		"title":        "测试发布主页",
		"subtitle":     "候选发布验证",
		"homepageType": "sight",
		"city":         "杭州",
		"address":      "西湖边",
	}, http.StatusCreated)
	homepageID := stringField(t, candidate, "_id")

	published := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/v1/homepages/candidates/"+homepageID+":publish",
		nil,
		http.StatusOK,
	)
	if got := stringField(t, published, "status"); got != "published" {
		t.Fatalf("expected published status, got %q", got)
	}

	search := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/search?query=测试发布主页&status=published",
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
		server.URL+"/v1/homepages/"+homepageID+"/shell",
		nil,
		http.StatusOK,
	)
	if _, ok := shell["homepage"].(map[string]any); !ok {
		t.Fatalf("expected shell.homepage object")
	}
	if _, ok := shell["contentPreview"].([]any); !ok {
		t.Fatalf("expected shell.contentPreview array")
	}

	bundle := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/"+homepageID+"/object-page-bundle?referralSource=test&feedRequestId=feed-1&recommendationTraceId=trace-1&experimentBucket=A&rolloutCohort=cohort-a",
		nil,
		http.StatusOK,
	)
	if got := stringField(t, bundle, "objectType"); got != "homepage" {
		t.Fatalf("expected homepage objectType, got %q", got)
	}
	if got := stringField(t, bundle, "canonicalEntityId"); got == "" {
		t.Fatalf("expected canonicalEntityId in bundle")
	}
	if edges := sliceField(t, bundle, "relationEdges"); len(edges) == 0 {
		t.Fatalf("expected relationEdges in bundle")
	}
	assistantContext, ok := bundle["assistantContext"].(map[string]any)
	if !ok {
		t.Fatalf("expected assistantContext object")
	}
	if assistantContext["referralSource"] != "test" {
		t.Fatalf("expected referralSource propagated, got %v", assistantContext["referralSource"])
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
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
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
			server.URL+"/v1/homepages/"+item.id+"/object-page-bundle",
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
			server.URL+"/v1/homepages/"+item.id,
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
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	const canonicalID = "entity:sight:homepage_sight_west_lake"

	detail := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/"+canonicalID,
		nil,
		http.StatusOK,
	)
	if got := stringField(t, detail, "_id"); got != "homepage_sight_west_lake" {
		t.Fatalf("expected semantic canonical detail to resolve west lake, got %q", got)
	}

	introduction := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/"+canonicalID+"/introduction",
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
		server.URL+"/v1/homepages/"+canonicalID+"/object-page-bundle",
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
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	impact := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/homepage_sight_west_lake/impact",
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
	contentServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotObjectID = r.URL.Query().Get("objectId")
		gotObjectType = r.URL.Query().Get("objectType")
		gotViewerID = r.Header.Get("X-Client-User-Id")
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
	t.Setenv("CONTENT_SERVICE_BASE_URL", contentServer.URL)

	server := httptest.NewServer(
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	req, err := http.NewRequest(
		http.MethodGet,
		server.URL+"/v1/homepages/homepage_sight_west_lake/object-page-bundle",
		nil,
	)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("X-Client-User-Id", "fixture_user_current")
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

func TestHomepageObjectPageBundleFallbackSatisfiesStrictPrimaryContract(t *testing.T) {
	t.Setenv("CONTENT_SERVICE_BASE_URL", "")
	server := httptest.NewServer(
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	bundle := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/homepage_sight_west_lake/object-page-bundle",
		nil,
		http.StatusOK,
	)
	reasons := sliceField(t, bundle, "intersectionReasons")
	if len(reasons) == 0 {
		t.Fatal("fallback intersection reasons must be non-empty")
	}
	for index, raw := range reasons {
		reason, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("reason[%d] type=%T", index, raw)
		}
		primaryText := stringField(t, reason, "primaryText")
		if primaryText == "" {
			t.Fatalf("reason[%d].primaryText empty", index)
		}
		actionTargetID := stringField(t, reason, "actionTargetId")
		spans := sliceField(t, reason, "primarySpans")
		if len(spans) == 0 {
			t.Fatalf("reason[%d].primarySpans empty", index)
		}
		joined := ""
		hasBoundObject := false
		for spanIndex, rawSpan := range spans {
			span, ok := rawSpan.(map[string]any)
			if !ok {
				t.Fatalf("reason[%d].primarySpans[%d] type=%T", index, spanIndex, rawSpan)
			}
			joined += stringField(t, span, "text")
			if stringField(t, span, "role") != "object" {
				continue
			}
			target, ok := span["target"].(map[string]any)
			if !ok {
				t.Fatalf("reason[%d].primarySpans[%d].target missing", index, spanIndex)
			}
			if stringField(t, target, "objectType") == "" {
				t.Fatalf("reason[%d].primarySpans[%d].target.objectType empty", index, spanIndex)
			}
			if stringField(t, target, "objectId") == actionTargetID {
				hasBoundObject = true
			}
		}
		if joined != primaryText {
			t.Fatalf("reason[%d] spans=%q primaryText=%q", index, joined, primaryText)
		}
		if !hasBoundObject {
			t.Fatalf("reason[%d] missing object span bound to actionTargetId", index)
		}
		for _, forbidden := range []string{"sourceRefs", "primaryEvidenceRef"} {
			if _, leaked := reason[forbidden]; leaked {
				t.Fatalf("reason[%d] leaked %s", index, forbidden)
			}
		}
	}
}

func TestHomepageIntroductionReturnsStructuredLongFormContent(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	introduction := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/homepage_sight_west_lake/introduction",
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
	if len(sections) < 4 {
		t.Fatalf("expected structured sections, got %d", len(sections))
	}
	kinds := map[string]bool{}
	totalBodyLen := 0
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
		if body, ok := section["bodyMarkdown"].(string); ok {
			totalBodyLen += len([]rune(body))
		}
	}
	for _, kind := range []string{"overview", "keyFacts", "timeline", "history"} {
		if !kinds[kind] {
			t.Fatalf("expected section kind %s in %#v", kind, kinds)
		}
	}
	if totalBodyLen < 800 {
		t.Fatalf("expected 800+ rune introduction body, got %d", totalBodyLen)
	}
	related := sliceField(t, introduction, "relatedObjects")
	if len(related) == 0 {
		t.Fatalf("expected relatedObjects")
	}
}

func TestHomepageIntroductionProjectsIntakenPageMarkdown(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	pageMarkdown := "---\ntitle: 都江堰\ncoverImage: asset://cover_asset\n---\n" +
		"# 都江堰\n\n都江堰是战国时期修建的大型水利工程。\n\n" +
		"## 历史沿革\n\n李冰父子主持修建。\n\n" +
		":::figure id=\"fig_01\" layout=\"fullWidth\" caption=\"鱼嘴分水堤\"\nasset://inline_asset_1\n:::\n\n" +
		"## 相关图片\n\n:::gallery layout=\"grid\"\nasset://related_asset_1\n:::\n"
	candidate := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/v1/homepages/candidates", map[string]any{
		"title":                "都江堰",
		"homepageType":         "sight",
		"introductionMarkdown": pageMarkdown,
		"introductionAssets": []map[string]any{
			{"assetId": "cover_asset", "url": "https://cdn.example.com/cover.jpg", "caption": "都江堰全景", "role": "cover"},
			{"assetId": "inline_asset_1", "url": "https://cdn.example.com/inline1.jpg", "caption": "鱼嘴分水堤"},
			{"assetId": "related_asset_1", "url": "https://cdn.example.com/rel1.jpg"},
		},
	}, http.StatusCreated)
	homepageID := stringField(t, candidate, "_id")
	if got := stringField(t, candidate, "coverUrl"); got != "https://cdn.example.com/cover.jpg" {
		t.Fatalf("expected cover derived from role=cover asset, got %q", got)
	}

	introduction := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/"+homepageID+"/introduction",
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
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	resp, err := server.Client().Get(server.URL + "/v1/homepages/missing-homepage/introduction")
	if err != nil {
		t.Fatalf("get introduction: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 for missing homepage, got %d", resp.StatusCode)
	}
}

func TestHomepageGovernanceLifecycle(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	candidate := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/v1/homepages/candidates", map[string]any{
		"title":        "测试治理主页",
		"subtitle":     "认领与下线验证",
		"homepageType": "hotel",
		"city":         "杭州",
		"address":      "龙井路 18 号",
	}, http.StatusCreated)
	homepageID := stringField(t, candidate, "_id")
	requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/v1/homepages/candidates/"+homepageID+":publish",
		nil,
		http.StatusOK,
	)

	claim := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/v1/homepages/"+homepageID+"/claim-requests",
		map[string]any{
			"claimTier":    "verified",
			"contactPhone": "13800000000",
			"note":         "governance test",
		},
		http.StatusCreated,
	)
	claimID := stringField(t, claim, "_id")
	if got := stringField(t, claim, "status"); got != "pending_review" {
		t.Fatalf("expected pending_review claim, got %q", got)
	}

	claimReview := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/v1/homepages/"+homepageID+"/claim-requests/"+claimID+":review",
		map[string]any{
			"status":     "approved",
			"reviewNote": "ok",
		},
		http.StatusOK,
	)
	if got := stringField(t, claimReview, "status"); got != "approved" {
		t.Fatalf("expected approved claim review, got %q", got)
	}

	updated := requestJSON(
		t,
		server.Client(),
		http.MethodPatch,
		server.URL+"/v1/homepages/"+homepageID+"/claimed-basics",
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
		server.URL+"/v1/homepages/"+homepageID+"/status-reports",
		map[string]any{
			"reason":      "offline",
			"description": "confirm soft offline",
		},
		http.StatusCreated,
	)
	reportID := stringField(t, report, "_id")
	if got := stringField(t, report, "status"); got != "pending_review" {
		t.Fatalf("expected pending_review status report, got %q", got)
	}

	reportReview := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/v1/homepages/"+homepageID+"/status-reports/"+reportID+":review",
		map[string]any{
			"status":     "confirmed_offline",
			"reviewNote": "offline confirmed",
		},
		http.StatusOK,
	)
	if got := stringField(t, reportReview, "status"); got != "confirmed_offline" {
		t.Fatalf("expected confirmed_offline review, got %q", got)
	}

	offlineDetail := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/"+homepageID,
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
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	req, err := http.NewRequest(
		http.MethodPost,
		server.URL+"/v1/homepages/candidates",
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
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	req, err := http.NewRequest(
		http.MethodGet,
		server.URL+"/v1/homepages/unknown/not-a-route",
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
	if out["code"] != "ENTITY.USER.not_found" {
		t.Fatalf("expected runtime code ENTITY.USER.not_found, got %v", out["code"])
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
	var body *bytes.Reader
	if payload == nil {
		body = bytes.NewReader(nil)
	} else {
		raw, err := json.Marshal(payload)
		if err != nil {
			t.Fatalf("marshal payload: %v", err)
		}
		body = bytes.NewReader(raw)
	}
	req, err := http.NewRequest(method, url, body)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
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
