package api_integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func doRequest(t *testing.T, method, path string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buf).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	req := httptest.NewRequest(method, path, &buf)
	req.Header.Set("Content-Type", "application/json")
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

// executeCircleCommand 按 generated operation guard 语义执行 Circle 聚合命令：
// 可信 persona principal 来自服务端上下文，Idempotency-Key 必填。
func executeCircleCommand(t *testing.T, method, path string, body any, idempotencyKey, personaID, operationName, pathTemplate string) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buf).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	request := httptest.NewRequest(method, path, &buf)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	circleGuard(method, pathTemplate, operationName).ServeHTTP(recorder, request)
	return recorder
}

func circleGuard(method, pathTemplate, operationName string) http.Handler {
	operationKind, mutationTarget, invariantTarget := generatedTestOperationSemantics(
		method,
		"Circle",
	)
	return rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle." + operationName,
			ContractGraphSHA256:  "circle-api-integration", Method: method, PathTemplate: pathTemplate,
			OperationKind: operationKind, MutationTarget: mutationTarget, InvariantTarget: invariantTarget,
			AuthMode: "required", ActorRequirement: "persona", Principal: "persona",
			CommercialStatus: "ready", TimeoutMilliseconds: 1500,
		}}, method, pathTemplate,
	)(testHandler)
}

// createTestCircle 以圈主身份 test_user_001 创建圈子并返回 circleId。
func createTestCircle(t *testing.T, name string) string {
	t.Helper()
	return createTestCircleAs(t, name, "test_user_001")
}

func createTestCircleAs(t *testing.T, name, ownerPersonaID string) string {
	t.Helper()
	rec := executeCircleCommand(t, http.MethodPost, "/circles", map[string]any{
		"name":     name,
		"category": "interest",
		"tags":     []string{"test"},
	}, "create-"+name+"-"+ownerPersonaID, ownerPersonaID, "CreateCircle", "/circles")
	if rec.Code != http.StatusCreated {
		t.Fatalf("createTestCircle failed: status=%d body=%s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	circleID, _ := body["circleId"].(string)
	if circleID == "" {
		t.Fatalf("createTestCircle receipt missing circleId: %v", body)
	}
	return circleID
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

// drainCircleEvents 把 Circle 本体 outbox 事实投递给 eventSpy，
// 供事件断言消费（与生产 relay 同一读取链）。
func drainCircleEvents(t *testing.T) {
	t.Helper()
	if _, err := circleEventRelay.Drain(t.Context(), 100); err != nil {
		t.Fatalf("drain circle outbox: %v", err)
	}
}
