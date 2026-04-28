package tests

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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

	detail := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/v1/homepages/"+homepageID,
		nil,
		http.StatusOK,
	)
	if got := stringField(t, detail, "claimStatus"); got != "claimed" {
		t.Fatalf("expected claimed homepage, got %q", got)
	}
	if got := stringField(t, detail, "status"); got != "offline" {
		t.Fatalf("expected offline homepage, got %q", got)
	}
	if _, ok := detail["offlineAt"].(string); !ok {
		t.Fatalf("expected offlineAt timestamp in detail response")
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
