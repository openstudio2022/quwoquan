package http_test

import (
	"net/http"
	"testing"

	gatheringhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

// contract_ref: services/circle-service/contracts/circle_management/gathering/operations.yaml
func TestGatheringRuntimeRegistersAll36OperationsOnUniquePatterns(t *testing.T) {
	mux := http.NewServeMux()
	gatheringhttp.NewHandler(
		&app.LifecycleFacade{},
		&app.CommandFacade{},
		&app.HostOutcomeFacade{},
		&app.GatheringQueryFacade{},
	).Register(mux)

	cases := []struct {
		method  string
		path    string
		pattern string
	}{
		{http.MethodPost, "/gatherings", "POST /gatherings"},
		{http.MethodPut, "/gatherings/g-1", "PUT /gatherings/{resource}"},
		{http.MethodGet, "/gatherings/g-1", "GET /gatherings/{gatheringId}"},
		{http.MethodGet, "/public/gatherings/g-1", "GET /public/gatherings/{gatheringId}"},
		{http.MethodGet, "/gatherings/by-host", "GET /gatherings/by-host"},
		{http.MethodGet, "/gatherings/by-source", "GET /gatherings/by-source"},
		{http.MethodGet, "/gatherings/g-1/applications", "GET /gatherings/{gatheringId}/applications"},
		{http.MethodGet, "/gatherings/g-1/roster", "GET /gatherings/{gatheringId}/roster"},
	}
	for _, action := range []string{
		"publish", "join-open", "apply", "withdraw-application",
		"review-application", "invite", "accept-invitation",
		"decline-invitation", "revoke-invitation", "leave", "remove",
		"reinstate", "pause-admission", "resume-admission",
		"change-capacity", "assign-co-host", "revoke-co-host",
		"transfer-organizer", "acknowledge-revision", "cancel",
		"declare-arrival", "leave-early", "complete-self", "complete",
		"end-early", "safety-terminate", "watch-availability",
		"unwatch-availability",
	} {
		cases = append(cases, struct {
			method  string
			path    string
			pattern string
		}{
			method:  http.MethodPost,
			path:    "/gatherings/g-1:" + action,
			pattern: "POST /gatherings/{resource}",
		})
	}
	if len(cases) != 36 {
		t.Fatalf("route inventory has %d operations, want 36", len(cases))
	}
	for _, current := range cases {
		request, err := http.NewRequest(current.method, current.path, nil)
		if err != nil {
			t.Fatalf("new request %s %s: %v", current.method, current.path, err)
		}
		_, pattern := mux.Handler(request)
		if pattern != current.pattern {
			t.Fatalf(
				"%s %s pattern=%q want=%q",
				current.method,
				current.path,
				pattern,
				current.pattern,
			)
		}
	}
}
