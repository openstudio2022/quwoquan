package runtimeerrors

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHTTPWriteOptionsFromRequest(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/v1/assistant/run", nil)
	req.Header.Set("X-Request-Id", "req-1")
	req.Header.Set("X-Trace-Id", "trace-1")

	opts := HTTPWriteOptionsFromRequest(req)

	if opts.RequestID != "req-1" || opts.TraceID != "trace-1" {
		t.Fatalf("unexpected opts: %+v", opts)
	}
}

func TestWriteHTTPErrorPropagatesIDs(t *testing.T) {
	rec := httptest.NewRecorder()
	err := NewInvalidArgument(ModuleAssistant, "请求体无效", "bad body")

	WriteHTTPError(rec, err, HTTPWriteOptions{
		RequestID: "req-1",
		TraceID:   "trace-1",
	})

	if rec.Header().Get("X-Request-Id") != "req-1" {
		t.Fatalf("missing request id header: %s", rec.Header().Get("X-Request-Id"))
	}
	if rec.Header().Get("X-Trace-Id") != "trace-1" {
		t.Fatalf("missing trace id header: %s", rec.Header().Get("X-Trace-Id"))
	}
	var body ErrorResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.RequestID != "req-1" || body.TraceID != "trace-1" {
		t.Fatalf("ids not propagated to body: %+v", body)
	}
	if body.Origin == "" || body.Nature == "" || body.Location.BusinessObject == "" {
		t.Fatalf("runtime fields should be present: %+v", body)
	}
}

func TestRouteNotFoundMapsToHTTPNotFound(t *testing.T) {
	rec := httptest.NewRecorder()
	WriteHTTPError(
		rec,
		NewAppError(
			NewCode(ModuleContent, KindUser, "route_not_found"),
			"接口不存在",
			"route not found",
		),
		HTTPWriteOptions{},
	)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for route_not_found, got %d", rec.Code)
	}
	var body ErrorResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Code != "CONTENT.USER.route_not_found" {
		t.Fatalf("expected route_not_found code, got %q", body.Code)
	}
}

func TestRuntimeOriginFromCurrentKindUsesCanonicalMapping(t *testing.T) {
	cases := []struct {
		name   string
		err    *AppError
		origin string
	}{
		{
			name: "network is environment",
			err: NewAppError(
				NewCode(ModuleGateway, KindNetwork, "connection_refused"),
				"网络不可用",
				"dial refused",
			),
			origin: "environment",
		},
		{
			name:   "middleware is remote dependency",
			err:    NewUnavailable(ModuleGateway, "上游不可用", "upstream unavailable"),
			origin: "remoteDependency",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			body := ToResponse(tc.err, "req-1", "trace-1")
			if body.Origin != tc.origin {
				t.Fatalf("expected origin %q, got %q", tc.origin, body.Origin)
			}
		})
	}
}
