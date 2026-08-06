package http_test

import (
	"net/http"
	"testing"

	gatheringhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

// contract_ref: services/circle-service/contracts/circle_management/gathering/operations.yaml
func TestScopeALifecycleRoutesUseMethodAwareResourcePattern(t *testing.T) {
	mux := http.NewServeMux()
	// The legacy unqualified route can coexist while composition migrates.
	mux.HandleFunc("/gatherings", func(http.ResponseWriter, *http.Request) {})
	gatheringhttp.NewLifecycleHandler(&app.LifecycleFacade{}).Register(mux)

	tests := []struct {
		method  string
		path    string
		pattern string
	}{
		{http.MethodPost, "/gatherings", "POST /gatherings"},
		{http.MethodPut, "/gatherings/gathering-1", "PUT /gatherings/{resource}"},
		{http.MethodPost, "/gatherings/gathering-1:publish", "POST /gatherings/{resource}"},
		{http.MethodPost, "/gatherings/gathering-1:safety-terminate", "POST /gatherings/{resource}"},
	}
	for _, test := range tests {
		request, err := http.NewRequest(test.method, test.path, nil)
		if err != nil {
			t.Fatalf("new request: %v", err)
		}
		_, pattern := mux.Handler(request)
		if pattern != test.pattern {
			t.Fatalf("%s %s pattern = %q, want %q", test.method, test.path, pattern, test.pattern)
		}
	}
}
