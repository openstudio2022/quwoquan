package http_test

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestRetiredBulkImportRouteIsPhysicallyAbsent(t *testing.T) {
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(
		http.MethodPost,
		"/admin/import",
		strings.NewReader("{}\n"),
	)

	newTestHandler().ServeHTTP(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("retired bulk import route status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}
