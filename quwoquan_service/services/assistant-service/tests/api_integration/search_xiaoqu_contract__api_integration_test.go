package api_integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	assistanthttp "quwoquan_service/services/assistant-service/internal/adapters/http"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

func TestSearchXiaoquContractApiIntegration(t *testing.T) {
	service := application.NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)
	handler := assistanthttp.NewHandler(service).Routes()

	payload, err := json.Marshal(map[string]any{
		"userQuery":       "四川露营攻略",
		"searchIntensity": "balanced",
		"sourceSurfaceId": "assistant_dialog",
		"fromGlobalSearch": true,
	})
	if err != nil {
		t.Fatalf("marshal request: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, "/v1/assistant/search/xiaoqu", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_xiaoqu_api_1")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
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
			if stringField(citation, "recallSource") != "web_supplement" {
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
