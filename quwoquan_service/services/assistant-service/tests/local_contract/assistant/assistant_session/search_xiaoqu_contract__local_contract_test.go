package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	rtsearch "quwoquan_service/runtime/search"
	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
)

type fixedSearchReader struct{}

func (fixedSearchReader) Retrieve(
	context.Context,
	string,
	[]string,
	int,
) (rtsearch.RetrieveResponse, error) {
	return rtsearch.RetrieveResponse{
		Citations: []rtsearch.Citation{
			{CitationID: "citation-article", ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post-1", Title: "四川露营路线", Snippet: "露营攻略", SourceDomain: "content", Score: 0.95},
			{CitationID: "citation-entity", ObjectType: rtsearch.ObjectTypeEntityHomepage, ObjectID: "homepage-1", Title: "四川露营地", Snippet: "地点主页", SourceDomain: "entity", Score: 0.92},
			{CitationID: "citation-web", ObjectType: rtsearch.ObjectTypeWebDocument, ObjectID: "web-1", Title: "公开露营信息", URL: "https://example.test/camping", SourceDomain: "web", Score: 0.88},
		},
		Provenance: rtsearch.Provenance{Provider: "search-service"},
	}, nil
}

func TestSearchXiaoquContractApiIntegration(t *testing.T) {
	service := orchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		rtredis.NewMemoryClient(),
		orchestration.WithXiaoquSearchReader(fixedSearchReader{}),
	)
	handler := assistanthttp.NewHandler(service).Routes()

	payload, err := json.Marshal(map[string]any{
		"userQuery":        "四川露营攻略",
		"searchIntensity":  "medium",
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

	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if got := stringField(result, "queryEcho"); got != "四川露营攻略" {
		t.Fatalf("queryEcho=%q, want 四川露营攻略", got)
	}
	if got := stringField(result, "searchIntensity"); got != "medium" {
		t.Fatalf("searchIntensity=%q, want medium", got)
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
		destination, ok := citation["destination"].(map[string]any)
		if !ok {
			t.Fatalf("canonical destination missing: %#v", citation)
		}
		if objectType == rtsearch.ObjectTypeWebDocument {
			if stringField(destination, "kind") != "external" || stringField(destination, "url") == "" {
				t.Fatalf("web citation external destination invalid: %#v", citation)
			}
			if stringField(citation, "recallSource") != "search-service" {
				t.Fatalf("web citation recallSource mismatch: %#v", citation)
			}
		} else {
			if stringField(destination, "kind") != "internal" ||
				stringField(destination, "objectTypeRef") != objectType ||
				stringField(destination, "objectId") != stringField(citation, "objectId") {
				t.Fatalf("business citation internal destination invalid: %#v", citation)
			}
			if stringField(citation, "snippet") == "" {
				t.Fatalf("business citation missing snippet: %#v", citation)
			}
			if stringField(citation, "recallSource") == "" {
				t.Fatalf("business citation missing recallSource: %#v", citation)
			}
		}
	}

	for _, target := range []string{
		rtsearch.ObjectTypeContentPost,
		rtsearch.ObjectTypeEntityHomepage,
		rtsearch.ObjectTypeWebDocument,
	} {
		if !seenTargets[target] {
			t.Fatalf("missing citation target %q in %#v", target, result["citations"])
		}
	}
}

func TestSearchXiaoquRejectsNonCanonicalSearchIntensity(t *testing.T) {
	service := orchestration.NewAssistantService(
		skillconsenttest.NewMemoryStore(),
		rtredis.NewMemoryClient(),
		orchestration.WithXiaoquSearchReader(fixedSearchReader{}),
	)
	handler := assistanthttp.NewHandler(service).Routes()
	payload, err := json.Marshal(map[string]any{
		"userQuery":       "四川露营攻略",
		"searchIntensity": "balanced",
	})
	if err != nil {
		t.Fatalf("marshal request: %v", err)
	}
	req := httptest.NewRequest(
		http.MethodPost,
		"/assistant/search/xiaoqu",
		bytes.NewReader(payload),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_xiaoqu_invalid_intensity")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "ASSISTANT.USER.run_invalid_argument") {
		t.Fatalf("expected canonical run_invalid_argument, body=%s", rec.Body.String())
	}
}

func stringField(body map[string]any, key string) string {
	value, _ := body[key].(string)
	return value
}
