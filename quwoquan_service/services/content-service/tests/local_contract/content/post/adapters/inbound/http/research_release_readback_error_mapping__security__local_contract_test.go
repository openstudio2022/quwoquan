// readiness_case: get-research-release-readback-local
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
package http_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/auth/researchidentity"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	. "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
)

type researchReadbackErrorProbe struct {
	err error
}

func (probe researchReadbackErrorProbe) ReadActiveResearchRelease(
	context.Context,
) (postapp.ResearchReleaseBinding, error) {
	return postapp.ResearchReleaseBinding{}, probe.err
}

func newResearchReadbackErrorHandler(
	t *testing.T,
	readErr error,
) (http.Handler, string) {
	t.Helper()
	authority, err := researchidentity.NewAuthority(
		[]byte("research-attestation-key-32-bytes-long"),
	)
	if err != nil {
		t.Fatal(err)
	}
	issuedAt := time.Now().UTC().Add(-time.Minute)
	_, attestation, err := authority.Issue(
		"account-research-readback",
		issuedAt,
		issuedAt.Add(5*time.Minute),
		[]byte(strings.Repeat("r", 32)),
	)
	if err != nil {
		t.Fatal(err)
	}
	facet, err := postapp.NewResearchReleaseReadbackQueryFacet(
		authority,
		researchReadbackErrorProbe{err: readErr},
	)
	if err != nil {
		t.Fatal(err)
	}
	return NewContentHandler(
		nil, nil, nil, nil, nil, nil, nil,
		WithResearchReleaseReadback(facet),
	).Routes(), attestation
}

func requestResearchReadback(
	t *testing.T,
	handler http.Handler,
	attestation string,
) (*httptest.ResponseRecorder, rterr.ErrorResponse) {
	t.Helper()
	request := httptest.NewRequest(http.MethodGet, "/content/research/readback", nil)
	request.Header.Set("X-Research-Identity-Attestation", attestation)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "account-research-readback",
		}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	var response rterr.ErrorResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode RuntimeErrorResponse: %v body=%s", err, recorder.Body.String())
	}
	return recorder, response
}

func TestResearchReleaseReadbackMapsNonResearchReleaseToContentStateUnavailable(
	t *testing.T,
) {
	handler, attestation := newResearchReadbackErrorHandler(
		t,
		postapp.ErrResearchReleaseNotResearch,
	)
	recorder, response := requestResearchReadback(t, handler, attestation)

	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d want=503 body=%s", recorder.Code, recorder.Body.String())
	}
	if response.Code != "CONTENT.SYSTEM.research_release_state_unavailable" ||
		response.Reason != "research_release_state_unavailable" ||
		response.Recovery.Action != "retry" ||
		response.Recovery.AfterSeconds != 5 {
		t.Fatalf("unexpected typed state error: %+v", response)
	}
	if response.DebugMessage != rterr.RedactedDebugMessage {
		t.Fatalf("debug detail leaked: %q", response.DebugMessage)
	}
	wire := recorder.Body.String()
	for _, sensitive := range []string{
		"active release is not research-only",
		"active release does not satisfy research readback state",
		attestation,
	} {
		if strings.Contains(wire, sensitive) {
			t.Fatalf("response leaked sensitive readback detail %q: %s", sensitive, wire)
		}
	}
}

func TestResearchReleaseReadbackKeepsIdentityFailureMapping(t *testing.T) {
	wrapped := errors.New("dependency should not be reached")
	handler, _ := newResearchReadbackErrorHandler(t, wrapped)
	recorder, response := requestResearchReadback(t, handler, "invalid-attestation")

	if recorder.Code != http.StatusForbidden {
		t.Fatalf("status=%d want=403 body=%s", recorder.Code, recorder.Body.String())
	}
	if response.Code != "CONTENT.USER.research_identity_invalid" ||
		response.Reason != "forbidden" ||
		response.Recovery.Action != "surface" {
		t.Fatalf("identity mapping drifted: %+v", response)
	}
	if response.DebugMessage != rterr.RedactedDebugMessage {
		t.Fatalf("identity debug detail leaked: %q", response.DebugMessage)
	}
}
