package es

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t7
func TestCreatorAliasReadbackRejectsSplitMissingAndDrift(t *testing.T) {
	for _, test := range []struct {
		name, reader, writer string
		ok                   bool
	}{{"same", "objects-v1", "objects-v1", true}, {"split", "objects-v1", "objects-v2", false}, {"drift", "objects-v2", "objects-v2", false}, {"missing", "", "", false}} {
		t.Run(test.name, func(t *testing.T) {
			writes := 0
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != "GET" {
					writes++
					http.Error(w, "write forbidden", 500)
					return
				}
				value := test.reader
				if r.URL.Path == "/_alias/objects-write" {
					value = test.writer
				}
				if value == "" {
					w.WriteHeader(404)
					return
				}
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte(`{"` + value + `":{"aliases":{}}}`))
			}))
			defer server.Close()
			client, err := NewClient(Config{Endpoints: []string{server.URL}, Index: "objects"})
			if err != nil {
				t.Fatal(err)
			}
			err = client.VerifyPhysicalNamespace(t.Context(), "objects-v1")
			if (err == nil) != test.ok {
				t.Fatal(err)
			}
			if writes != 0 {
				t.Fatal("readback repaired provider")
			}
		})
	}
}
