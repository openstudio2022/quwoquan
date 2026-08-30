// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
package http_test

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtgov "quwoquan_service/runtime/governance"
	httpadapter "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
)

func TestWriteContentFeedAdmissionRejectionEmitsFeedCapacityUnavailable(t *testing.T) {
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/content/feed", nil)

	httpadapter.WriteFeedAdmissionRejection(
		recorder,
		request,
		rtgov.OperationAdmissionInflightFull,
	)

	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf(
			"feed admission rejection status=%d want=%d body=%s",
			recorder.Code,
			http.StatusServiceUnavailable,
			recorder.Body.String(),
		)
	}
	if !strings.Contains(
		recorder.Body.String(),
		`"code":"CONTENT.SYSTEM.feed_capacity_unavailable"`,
	) {
		t.Fatalf(
			"feed admission rejection must carry the declared wire code: %s",
			recorder.Body.String(),
		)
	}
	if recorder.Header().Get("Retry-After") != "1" {
		t.Fatalf(
			"feed admission rejection must advertise Retry-After=1, got %q",
			recorder.Header().Get("Retry-After"),
		)
	}
}
