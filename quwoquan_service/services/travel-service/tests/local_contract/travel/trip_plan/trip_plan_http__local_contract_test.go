// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	httpadapter "quwoquan_service/services/travel-service/internal/travel/trip_plan/adapters/inbound/http"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
)

func TestTripPlanHTTPUsesGeneratedRoutesTrustedPersonaAndCanonicalWire(t *testing.T) {
	store := newMemoryTripStore()
	service := application.NewService(
		store, store, nil, &sequenceIDs{},
		func() time.Time { return time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC) },
	)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).RegisterRoutes(mux)

	create := newTripRequest(
		t,
		http.MethodPost,
		"/travel/trips",
		`{"title":"杭州共同旅行","items":[{"itemId":"hotel","dayIndex":0,"orderInDay":0,"kind":"stay","title":"入住"}]}`,
		"travel.trip_plan.CreateTripPlan",
		"persona-organizer",
		"create-trip-http",
	)
	created := httptest.NewRecorder()
	mux.ServeHTTP(created, create)
	if created.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body.String())
	}
	var createResult struct {
		TripID                string `json:"tripId"`
		CurrentRevisionNumber int64  `json:"currentRevisionNumber"`
	}
	if err := json.Unmarshal(created.Body.Bytes(), &createResult); err != nil ||
		createResult.TripID == "" || createResult.CurrentRevisionNumber != 1 {
		t.Fatalf("create result=%+v err=%v", createResult, err)
	}
	if strings.Contains(created.Body.String(), `"_id"`) {
		t.Fatalf("public wire leaked Mongo identity: %s", created.Body.String())
	}

	get := newTripRequest(
		t,
		http.MethodGet,
		"/travel/trips/"+createResult.TripID,
		"",
		"travel.trip_plan.GetTripPlan",
		"persona-organizer",
		"",
	)
	got := httptest.NewRecorder()
	mux.ServeHTTP(got, get)
	if got.Code != http.StatusOK || !strings.Contains(got.Body.String(), `"items"`) ||
		!strings.Contains(got.Body.String(), `"organizerPersonaId":"persona-organizer"`) {
		t.Fatalf("get status=%d body=%s", got.Code, got.Body.String())
	}

	list := newTripRequest(
		t,
		http.MethodGet,
		"/travel/trips?status=planning&limit=20",
		"",
		"travel.trip_plan.ListTripPlans",
		"persona-organizer",
		"",
	)
	listed := httptest.NewRecorder()
	mux.ServeHTTP(listed, list)
	if listed.Code != http.StatusOK ||
		!strings.Contains(listed.Body.String(), `"tripId":"`+createResult.TripID+`"`) ||
		!strings.Contains(listed.Body.String(), `"itemCount":1`) ||
		strings.Contains(listed.Body.String(), `"organizerPersonaId"`) {
		t.Fatalf("list status=%d body=%s", listed.Code, listed.Body.String())
	}

	revise := newTripRequest(
		t,
		http.MethodPost,
		"/travel/trips/"+createResult.TripID+"/revisions",
		`{"expectedRevisionNumber":1,"changeReason":"改住两晚","severity":"important","items":[{"itemId":"hotel","dayIndex":0,"orderInDay":0,"kind":"stay","title":"入住两晚"}]}`,
		"travel.trip_plan.ReviseTripPlan",
		"persona-organizer",
		"revise-trip-http",
	)
	revised := httptest.NewRecorder()
	mux.ServeHTTP(revised, revise)
	if revised.Code != http.StatusOK || !strings.Contains(revised.Body.String(), `"currentRevisionNumber":2`) {
		t.Fatalf("revise status=%d body=%s", revised.Code, revised.Body.String())
	}
}

func TestTripPlanHTTPIgnoresSpoofedPersonaHeader(t *testing.T) {
	store := newMemoryTripStore()
	service := application.NewService(store, store, nil, &sequenceIDs{}, time.Now)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).RegisterRoutes(mux)
	request := httptest.NewRequest(
		http.MethodPost,
		"/travel/trips",
		strings.NewReader(`{"title":"伪造请求","items":[]}`),
	)
	request.Header.Set("X-Client-Persona-Id", "persona-spoofed")
	request.Header.Set("Idempotency-Key", "spoofed-key")
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)
	if response.Code != http.StatusForbidden ||
		!strings.Contains(response.Body.String(), "TRAVEL.USER.trip_permission_denied") {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
}

func newTripRequest(
	t *testing.T,
	method string,
	path string,
	body string,
	operationID string,
	personaID string,
	idempotencyKey string,
) *http.Request {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	current := operation.Context{
		OperationID:    operationID,
		RequestID:      "request-trip-http",
		TraceID:        "trace-trip-http",
		Actor:          operation.ActorContext{PersonaID: personaID},
		IdempotencyKey: idempotencyKey,
	}
	return request.WithContext(operation.WithContext(context.Background(), current))
}
