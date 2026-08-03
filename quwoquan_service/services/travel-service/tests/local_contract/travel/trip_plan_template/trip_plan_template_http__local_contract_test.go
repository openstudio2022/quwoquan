// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
package trip_plan_template_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	httpadapter "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/adapters/inbound/http"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
)

func TestTripPlanTemplateHTTPCreateUsesServerIdentityAndStrictCreateBody(t *testing.T) {
	mux := newTemplateMux()
	created := httptest.NewRecorder()
	mux.ServeHTTP(created, newTemplateRequest(
		`{"title":"杭州周末","dayCount":2,"items":[{"templateItemId":"west_lake","dayOffset":0,"orderInDay":0,"kind":"sight","title":"西湖","attributionIds":[]}],"attributions":[]}`,
		"template-create-http",
	))
	if created.Code != http.StatusCreated ||
		!strings.Contains(created.Body.String(), `"id":"tpt_1"`) {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body.String())
	}

	for _, body := range []string{
		`{"templateId":"client-owned","title":"杭州周末","dayCount":2,"items":[],"attributions":[]}`,
		`{"expectedVersion":0,"title":"杭州周末","dayCount":2,"items":[],"attributions":[]}`,
	} {
		rejected := httptest.NewRecorder()
		newTemplateMux().ServeHTTP(rejected, newTemplateRequest(body, "template-create-rejected"))
		if rejected.Code != http.StatusBadRequest ||
			!strings.Contains(rejected.Body.String(), "TRAVEL.USER.trip_plan_template_invalid_argument") {
			t.Fatalf("create accepted undeclared identity/CAS field: status=%d body=%s", rejected.Code, rejected.Body.String())
		}
	}
}

func newTemplateMux() *http.ServeMux {
	store := &templateStore{values: map[string]model.Template{}, receipts: map[string]ports.Receipt{}}
	service := application.NewService(
		store,
		templateReferences{},
		templateIDs{},
		func() time.Time { return time.Date(2026, 8, 2, 9, 0, 0, 0, time.UTC) },
	)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).RegisterRoutes(mux)
	return mux
}

func newTemplateRequest(body, idempotencyKey string) *http.Request {
	request := httptest.NewRequest(http.MethodPost, "/travel/templates", strings.NewReader(body))
	current := operation.Context{
		OperationID:    "travel.trip_plan_template.CreateTripPlanTemplate",
		RequestID:      "request-template-http",
		TraceID:        "trace-template-http",
		Actor:          operation.ActorContext{PersonaID: "persona-guide"},
		IdempotencyKey: idempotencyKey,
	}
	return request.WithContext(operation.WithContext(context.Background(), current))
}
