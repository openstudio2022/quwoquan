package main

import (
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestOwningEventGoUsesNonEmptyNestedClosure(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{"Fence": {Fields: []fieldDef{{Name: "revision", Type: "int64", Constraints: []string{"NOT_NULL"}}, {Name: "activatedAt", Type: "timestamp", Constraints: []string{"NULLABLE"}}}}, "Changed": {Fields: []fieldDef{{Name: "before", Type: "Fence", Constraints: []string{"NOT_NULL"}}, {Name: "after", Type: "Fence", Constraints: []string{"NOT_NULL"}}}}}}
	order, err := resolveEventPayloadClosure(fields, nil, "Changed", []string{"before", "after"})
	if err != nil {
		t.Fatal(err)
	}
	out, err := renderConsumedEventGo(fields, order, "content/content/post/events.yaml", "content.post.Changed")
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"event_ref: content.post.Changed", "type Changed struct", "Before Fence", "After Fence", "ActivatedAt *time.Time"} {
		if !strings.Contains(strings.Join(strings.Fields(string(out)), " "), want) {
			t.Fatalf("missing %s: %s", want, out)
		}
	}
	if _, err = parser.ParseFile(token.NewFileSet(), "payload.g.go", out, parser.AllErrors); err != nil {
		t.Fatal(err)
	}
	again, _ := renderConsumedEventGo(fields, order, "content/content/post/events.yaml", "content.post.Changed")
	if string(out) != string(again) {
		t.Fatal("nondeterministic")
	}
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestCanonicalSearchOwningEvents(t *testing.T) {
	view := os.Getenv("QWQ_TEST_CONTRACT_VIEW")
	if view == "" {
		t.Skip("explicit view required")
	}
	source, err := contractcodegen.NewSource(view, validate.ProfileBaseline)
	if err != nil {
		t.Fatal(err)
	}
	out := t.TempDir()
	if err = generateConsumedEvents(source, "search/search/search_index_view", out, true); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(out, "content_post_ContentReleaseFenceChanged", "payload.g.go")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), "type ContentActiveReleaseFence struct") || !strings.Contains(string(raw), "Before ContentActiveReleaseFence") {
		t.Fatal(string(raw))
	}
	if err = generateOrCheckConsumedEvents(source, "search/search/search_index_view", out, true, true); err != nil {
		t.Fatal(err)
	}
}

func TestRuntimePythonRequiresNullablePresence(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{"Fact": {Fields: []fieldDef{{Name: "previousBinding", Type: "string", Constraints: []string{"NULLABLE"}}, {Name: "mode", Type: "string", Constraints: []string{"NOT_NULL"}}}}}}
	strict := generateRequestResponsePyForNames(fields, []string{"Fact"}, true)
	if strings.Contains(strict, " = None") || !strings.Contains(strict, "previousBinding: str | None") {
		t.Fatal(strict)
	}
	existing := generateRequestResponsePyForNames(fields, []string{"Fact"})
	if !strings.Contains(existing, " = None") {
		t.Fatal("unrelated event output changed")
	}
}

func TestFormalEmitterIncludesFeatureAndSearchOwningEvents(t *testing.T) {
	view := os.Getenv("QWQ_TEST_CONTRACT_VIEW")
	if view == "" {
		t.Skip("explicit current canonical view required")
	}
	root := t.TempDir()
	out := filepath.Join(root, "recommendation", "recommendation_model_release")
	search := filepath.Join(root, "search_events")
	if err := run(view, out, "recommendation/recommendation/recommendation_model_release", "", "", search); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{filepath.Join(root, "recommendation", "recommendation_feature_profile_view", "events", "content_post_ContentReleaseFenceChanged.py"), filepath.Join(search, "content_post_ContentReleaseFenceChanged", "payload.g.go")} {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(string(raw), "ContentActiveReleaseFence") || !strings.Contains(string(raw), "event_ref: content.post.ContentReleaseFenceChanged") {
			t.Fatal("missing source or nested fence", path)
		}
	}
}
