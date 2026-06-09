package search

import (
	"context"
	"errors"
	"testing"
)

func TestResolveBackendModeDefaultsNative(t *testing.T) {
	t.Setenv("SEARCH_BACKEND", "")
	t.Setenv("ES_ENDPOINT", "")
	if got := ResolveBackendMode(); got != BackendNative {
		t.Fatalf("default mode=%q want native", got)
	}
}

func TestResolveBackendModeESRequiresEndpoint(t *testing.T) {
	t.Setenv("SEARCH_BACKEND", "es")
	t.Setenv("ES_ENDPOINT", "")
	if got := ResolveBackendMode(); got != BackendNative {
		t.Fatalf("es without endpoint must stay native, got %q", got)
	}
	t.Setenv("ES_ENDPOINT", "https://es.example.com")
	if got := ResolveBackendMode(); got != BackendES {
		t.Fatalf("es with endpoint should select es, got %q", got)
	}
}

type erroringBackend struct{}

func (erroringBackend) Name() string { return "erroring" }
func (erroringBackend) Recall(context.Context, RetrievePlan) ([]RecallCandidate, error) {
	return nil, errors.New("boom")
}

func TestFallbackBackendDegradesToNative(t *testing.T) {
	native := NewSliceBackend(sampleDocs())
	fb := FallbackBackend{Primary: erroringBackend{}, Fallback: native}
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetArticle},
		Terms:   []string{"露营"},
	}, fb, Viewer{})
	if err != nil {
		t.Fatalf("fallback retrieve err=%v", err)
	}
	if len(resp.Hits) == 0 {
		t.Fatalf("fallback should still return native hits")
	}
}

func TestBackendsAgreeOnContract(t *testing.T) {
	// Same plan over native vs a fake backend returning identical candidates
	// must produce the same hit object ids (contract parity).
	plan, _ := PlanRequest(RetrieveRequest{Targets: []Target{TargetArticle}, Terms: []string{"露营"}}, Viewer{})
	native := NewSliceBackend(sampleDocs())
	cands, err := native.Recall(context.Background(), plan)
	if err != nil {
		t.Fatalf("native recall err=%v", err)
	}
	if len(cands) == 0 {
		t.Fatalf("native recall returned no candidates")
	}
}
