// spec_ref: specs/feature-tree/runtime/runtime-governance/resilience-policy-engine/spec.md#gwt-002
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004
package governance_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	rtgov "quwoquan_service/runtime/governance"
)

const admissionOperationID = "content.post.GetFeed"

func TestOperationAdmissionInflightShedsAndReleases(t *testing.T) {
	policy := rtgov.OperationAdmissionPolicy{
		CanonicalOperationID: admissionOperationID,
		InflightLimiter:      rtgov.NewInflightLimiter(1),
	}
	started := make(chan struct{})
	release := make(chan struct{})
	rejections := make([]rtgov.OperationAdmissionRejection, 0, 1)
	handler := guardedAdmissionHandler(
		policy,
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			close(started)
			<-release
			w.WriteHeader(http.StatusNoContent)
		}),
		func(w http.ResponseWriter, _ *http.Request, reason rtgov.OperationAdmissionRejection) {
			rejections = append(rejections, reason)
			w.WriteHeader(http.StatusServiceUnavailable)
		},
	)

	first := httptest.NewRecorder()
	firstDone := make(chan struct{})
	go func() {
		defer close(firstDone)
		handler.ServeHTTP(first, httptest.NewRequest(http.MethodGet, "/content/feed", nil))
	}()
	<-started

	second := httptest.NewRecorder()
	handler.ServeHTTP(second, httptest.NewRequest(http.MethodGet, "/content/feed", nil))
	if second.Code != http.StatusServiceUnavailable {
		t.Fatalf("second status=%d want=%d", second.Code, http.StatusServiceUnavailable)
	}
	if len(rejections) != 1 || rejections[0] != rtgov.OperationAdmissionInflightFull {
		t.Fatalf("rejections=%v want=[%s]", rejections, rtgov.OperationAdmissionInflightFull)
	}
	close(release)
	<-firstDone
	if first.Code != http.StatusNoContent {
		t.Fatalf("first status=%d want=%d", first.Code, http.StatusNoContent)
	}

	third := httptest.NewRecorder()
	thirdStarted := make(chan struct{})
	thirdHandler := guardedAdmissionHandler(
		policy,
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			close(thirdStarted)
			w.WriteHeader(http.StatusNoContent)
		}),
		func(w http.ResponseWriter, _ *http.Request, _ rtgov.OperationAdmissionRejection) {
			w.WriteHeader(http.StatusServiceUnavailable)
		},
	)
	thirdHandler.ServeHTTP(third, httptest.NewRequest(http.MethodGet, "/content/feed", nil))
	<-thirdStarted
	if third.Code != http.StatusNoContent {
		t.Fatalf("third status=%d want=%d", third.Code, http.StatusNoContent)
	}
}

func guardedAdmissionHandler(
	policy rtgov.OperationAdmissionPolicy,
	next http.Handler,
	reject rtgov.OperationAdmissionRejectWriter,
) http.Handler {
	descriptor := rtauth.OperationSecurityDescriptor{
		CanonicalOperationID: admissionOperationID,
		ContractGraphSHA256:  "test-contract-graph",
		Method:               http.MethodGet,
		PathTemplate:         "/content/feed",
		OperationKind:        "query",
		AuthMode:             "public",
		ActorRequirement:     "none",
		Principal:            "public",
		OwnershipPolicy:      "public_discovery_feed",
		TimeoutMilliseconds:  1500,
		Idempotency:          "none",
		CommercialStatus:     "ready",
	}
	admission := rtgov.OperationAdmissionMiddleware(
		[]rtgov.OperationAdmissionPolicy{policy},
		reject,
	)(next)
	return rtauth.RequireGeneratedOperationAuthorization(
		[]rtauth.OperationSecurityDescriptor{descriptor},
	)(admission)
}
