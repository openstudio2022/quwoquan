package http

import (
	"net/http"
	"net/http/httptest"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
)

// subjectKeyFor must prefer viewer id, then session id, and must NEVER fall back
// to the per-request id (which would re-roll the AB arm on every request and make
// the same query jump between control and term_heat).
func TestSubjectKeyForStableIdentityOnly(t *testing.T) {
	cases := []struct {
		name    string
		viewer  string
		session string
		wantKey string
		stable  bool
	}{
		{name: "logged_in", viewer: "user-9", session: "sess-1", wantKey: "user-9", stable: true},
		{name: "anon_with_session", viewer: "", session: "sess-7", wantKey: "sess-7", stable: true},
		{name: "anon_no_session", viewer: "", session: "", wantKey: "", stable: true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			r := httptest.NewRequest(http.MethodPost, "/v1/search", nil)
			if tc.session != "" {
				r.Header.Set("X-Session-Id", tc.session)
			}
			viewer := rtsearch.Viewer{UserID: tc.viewer}
			// Pass two DIFFERENT request ids to prove the result does not depend on it.
			got1 := subjectKeyFor(viewer, r, "req-AAAA")
			got2 := subjectKeyFor(viewer, r, "req-BBBB")
			if got1 != tc.wantKey || got2 != tc.wantKey {
				t.Fatalf("subjectKeyFor=%q/%q want %q (must ignore requestID)", got1, got2, tc.wantKey)
			}
		})
	}
}
