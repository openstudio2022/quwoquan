package api_integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func doRequest(t *testing.T, method, path string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	if body != nil {
		json.NewEncoder(&buf).Encode(body)
	}
	req := httptest.NewRequest(method, path, &buf)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "test_user_001")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	return rec
}

func doRequestAs(t *testing.T, method, path, userID string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	if body != nil {
		json.NewEncoder(&buf).Encode(body)
	}
	req := httptest.NewRequest(method, path, &buf)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", userID)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	return rec
}

func doRequestAsWithHeaders(
	t *testing.T,
	method,
	path,
	userID string,
	headers map[string]string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	if body != nil {
		json.NewEncoder(&buf).Encode(body)
	}
	req := httptest.NewRequest(method, path, &buf)
	req.Header.Set("Content-Type", "application/json")
	if userID != "" {
		req.Header.Set("X-Client-User-Id", userID)
	}
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	return rec
}

func decodeBody(t *testing.T, rec *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var result map[string]any
	if err := json.NewDecoder(rec.Body).Decode(&result); err != nil {
		t.Fatalf("decode response body: %v", err)
	}
	return result
}

func createTestCircle(t *testing.T, name string) string {
	t.Helper()
	rec := doRequest(t, http.MethodPost, "/circles", map[string]any{
		"name":     name,
		"category": "interest",
		"tags":     []string{"test"},
	})
	if rec.Code != http.StatusCreated {
		t.Fatalf("createTestCircle failed: status=%d body=%s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	data := body["data"].(map[string]any)
	return data["id"].(string)
}

func toInt64(value any) int64 {
	switch number := value.(type) {
	case int64:
		return number
	case int32:
		return int64(number)
	case float64:
		return int64(number)
	default:
		return 0
	}
}

// generatedTestOperationSemantics keeps the hand-written integration harness
// aligned with the generated descriptor contract. Production descriptors never
// infer semantics from HTTP methods; they carry the metadata-owned values.
func generatedTestOperationSemantics(method, aggregateTarget string) (string, string, string) {
	if method == http.MethodGet {
		return "query", "", ""
	}
	return "command", aggregateTarget, aggregateTarget
}
