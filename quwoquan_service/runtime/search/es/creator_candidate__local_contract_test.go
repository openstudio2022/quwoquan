package es

import (
	"context"
	"encoding/json"
	rt "quwoquan_service/runtime/search"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
type creatorCapture struct{ body map[string]any }

func (c *creatorCapture) Search(_ context.Context, _ string, b map[string]any) ([]rt.RecallCandidate, error) {
	c.body = b
	return nil, nil
}
func TestReleaseFenceAppliedBeforeProvider(t *testing.T) {
	capture := &creatorCapture{}
	backend := NewBackend(capture, "test")
	d := "sha256:" + strings.Repeat("a", 64)
	a := rt.ReleaseQueryPreparationBinding{Release: rt.ReleaseCandidateBinding{"gamma", "qwq_data", "a", d}, Slice: "post_search", ProviderBindingGeneration: d, SchemaGeneration: d}
	b := a
	b.Release.ReleaseID = "b"
	for _, binding := range []*rt.ReleaseQueryPreparationBinding{nil, &a, &b, &a} {
		if _, err := backend.Recall(WithReleaseBinding(t.Context(), binding), rt.RetrievePlan{}); err != nil {
			t.Fatal(err)
		}
		raw, _ := json.Marshal(capture.body)
		if !strings.Contains(string(raw), "releaseSliceBinding") || !strings.Contains(string(raw), "sourceKind") {
			t.Fatal("missing release fence")
		}
	}
	i := rt.ReleaseCandidateObjectIdentity{ObjectType: "content.post", ObjectID: "same"}
	if ReleaseDocumentID(a, i) == ReleaseDocumentID(b, i) {
		t.Fatal("candidate collision")
	}
}
