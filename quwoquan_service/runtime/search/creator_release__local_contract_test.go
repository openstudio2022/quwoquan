package search

import (
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t6
func TestCreatorCanonicalDigestAndClosure(t *testing.T) {
	d, err := CreatorCanonicalDigest(map[string]any{"z": "中文<旅行>", "a": 1}, "")
	if err != nil {
		t.Fatal(err)
	}
	other, _ := CreatorCanonicalDigest(struct {
		Z string `json:"z"`
		A int    `json:"a"`
	}{"中文<旅行>", 1}, "")
	if d != other {
		t.Fatal("canonical key order diverged")
	}
	s := CreatorSearchCandidateSnapshot{Release: ReleaseCandidateBinding{"gamma", "qwq_data", "release-a", "sha256:" + strings.Repeat("a", 64)}, SourceClosureDigest: d, Profiles: []CreatorSearchPublicSnapshot{}}
	if err = s.Seal(); err != nil {
		t.Fatal(err)
	}
	if err = s.Validate(); err != nil {
		t.Fatal(err)
	}
	s.Release.ReleaseID = "release-b"
	if s.Validate() == nil {
		t.Fatal("drift accepted")
	}
	var unified SearchReleaseCandidateSnapshot
	if DecodeCreatorValue(strings.NewReader(`{"release":{},"profiles":[]}`), &unified) == nil {
		t.Fatal("retired preparation snapshot decoded")
	}
	var binding ReleaseQueryPreparationBinding
	if DecodeCreatorValue(strings.NewReader(`{"release":{},"projectionContractVersion":1,"providerBindingGeneration":"old"}`), &binding) == nil {
		t.Fatal("retired binding decoded")
	}
	var value map[string]any
	for _, raw := range []string{`{"a":1,"a":2}`, `{} {}`, `{"a":{"x":1,"x":2}}`} {
		if DecodeCreatorValue(strings.NewReader(raw), &value) == nil {
			t.Fatalf("accepted invalid wire %s", raw)
		}
	}
}
