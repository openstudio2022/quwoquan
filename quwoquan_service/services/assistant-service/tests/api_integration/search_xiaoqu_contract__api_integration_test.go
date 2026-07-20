package api_integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	assistanthttp "quwoquan_service/services/assistant-service/internal/adapters/http"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/infrastructure/searchclient"
)

func TestSearchXiaoquContractApiIntegration(t *testing.T) {
	resetIntegrationState(t)
	var searchRequest map[string]any
	searchServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("search-service method=%s, want POST", r.Method)
		}
		if err := json.NewDecoder(r.Body).Decode(&searchRequest); err != nil {
			t.Fatalf("decode search-service request: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"hits": [],
			"citations": [
				{
					"citationId": "citation-article",
					"objectType": "article",
					"objectId": "post-1",
					"title": "四川露营路线",
					"snippet": "露营攻略",
					"sourceDomain": "content",
					"score": 0.95
				},
				{
					"citationId": "citation-entity",
					"objectType": "entity",
					"objectId": "homepage-1",
					"title": "四川露营地",
					"snippet": "地点主页",
					"sourceDomain": "entity",
					"score": 0.92
				},
				{
					"citationId": "citation-web",
					"objectType": "web",
					"objectId": "web-1",
					"title": "公开露营信息",
					"url": "https://example.test/camping",
					"sourceDomain": "web",
					"score": 0.88
				}
			],
			"provenance": {
				"provider": "search-service",
				"indexVersion": "integration",
				"generatedAt": "2026-07-20T10:00:00Z"
			}
		}`))
	}))
	defer searchServer.Close()
	searchReader, err := searchclient.New(
		searchServer.URL,
		&http.Client{Timeout: time.Second},
	)
	if err != nil {
		t.Fatalf("new canonical search reader: %v", err)
	}
	service := newIntegrationAssistantService(
		application.WithXiaoquSearchReader(searchReader),
	)
	handler := assistanthttp.NewHandler(service).Routes()

	payload, err := json.Marshal(map[string]any{
		"userQuery":        "四川露营攻略",
		"searchIntensity":  "balanced",
		"sourceSurfaceId":  "assistant_dialog",
		"fromGlobalSearch": true,
	})
	if err != nil {
		t.Fatalf("marshal request: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, "/assistant/search/xiaoqu", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_xiaoqu_api_1")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if got := stringField(searchRequest, "query"); got != "四川露营攻略" {
		t.Fatalf("search-service query=%q, want 四川露营攻略", got)
	}
	if got := stringField(searchRequest, "mode"); got != "result" {
		t.Fatalf("search-service mode=%q, want result", got)
	}

	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if got := stringField(result, "queryEcho"); got != "四川露营攻略" {
		t.Fatalf("queryEcho=%q, want 四川露营攻略", got)
	}
	if got := stringField(result, "searchIntensity"); got != "balanced" {
		t.Fatalf("searchIntensity=%q, want balanced", got)
	}

	rawCitations, ok := result["citations"].([]any)
	if !ok {
		t.Fatalf("citations missing: %#v", result)
	}
	if len(rawCitations) < 2 {
		t.Fatalf("expected canonical citations, got %#v", result)
	}

	seenTargets := map[string]bool{}
	for _, raw := range rawCitations {
		citation, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("unexpected citation payload: %#v", raw)
		}
		objectType := stringField(citation, "objectType")
		if objectType == "spec" || objectType == "knowledge" {
			t.Fatalf("placeholder citation must not be returned: %#v", citation)
		}
		for _, forbidden := range []string{"content.post", "entity.homepage", "circle.group", "user.profile", "web.document"} {
			if objectType == forbidden {
				t.Fatalf("internal object type leaked to API citation: %q", objectType)
			}
		}
		seenTargets[objectType] = true
		if stringField(citation, "citationId") == "" {
			t.Fatalf("citationId missing: %#v", citation)
		}
		if stringField(citation, "objectId") == "" {
			t.Fatalf("objectId missing: %#v", citation)
		}
		if stringField(citation, "title") == "" {
			t.Fatalf("title missing: %#v", citation)
		}
		if stringField(citation, "sourceDomain") == "" {
			t.Fatalf("sourceDomain missing: %#v", citation)
		}
		if stringField(citation, "objectTypeRef") != objectType {
			t.Fatalf("objectTypeRef must mirror objectType: %#v", citation)
		}
		score, ok := citation["score"].(float64)
		if !ok || score <= 0 {
			t.Fatalf("score must be positive: %#v", citation)
		}
		if objectType == "web" {
			if stringField(citation, "url") == "" {
				t.Fatalf("web citation missing url: %#v", citation)
			}
			if stringField(citation, "recallSource") != "search-service" {
				t.Fatalf("web citation recallSource mismatch: %#v", citation)
			}
		} else {
			if stringField(citation, "snippet") == "" {
				t.Fatalf("business citation missing snippet: %#v", citation)
			}
			if stringField(citation, "recallSource") == "" {
				t.Fatalf("business citation missing recallSource: %#v", citation)
			}
		}
	}

	for _, target := range []string{"article", "entity", "web"} {
		if !seenTargets[target] {
			t.Fatalf("missing citation target %q in %#v", target, result["citations"])
		}
	}
}

func stringField(body map[string]any, key string) string {
	value, _ := body[key].(string)
	return value
}
