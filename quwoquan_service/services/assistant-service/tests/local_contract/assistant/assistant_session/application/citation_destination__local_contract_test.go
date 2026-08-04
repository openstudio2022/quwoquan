// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
package local_contract

import (
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
)

func TestCanonicalToolReferenceBuildsSingleTrackInternalDestination(t *testing.T) {
	reference, ok := orchestration.CanonicalToolReference(map[string]any{
		"title":      "站内文章",
		"objectType": rtsearch.ObjectTypeContentPost,
		"objectId":   "post-1",
		"url":        "https://public.example/post-1",
	})
	if !ok {
		t.Fatal("CanonicalToolReference() rejected canonical internal object")
	}
	if _, keepsURLAlias := reference["url"]; keepsURLAlias {
		t.Fatalf("reference retained URL-only alias: %#v", reference)
	}
	destination, ok := reference["destination"].(map[string]any)
	if !ok ||
		stringValue(destination["kind"]) != "internal" ||
		stringValue(destination["objectTypeRef"]) != rtsearch.ObjectTypeContentPost ||
		stringValue(destination["objectId"]) != "post-1" {
		t.Fatalf("internal destination = %#v", reference["destination"])
	}
}

func TestCanonicalToolReferenceRejectsURLOnlyAndInsecureExternalReferences(t *testing.T) {
	if reference, ok := orchestration.CanonicalToolReference(map[string]any{
		"title": "URL-only",
		"url":   "https://example.com",
	}); ok {
		t.Fatalf("URL-only reference accepted: %#v", reference)
	}
	if reference, ok := orchestration.CanonicalToolReference(map[string]any{
		"title": "insecure",
		"destination": map[string]any{
			"kind": "external",
			"url":  "http://example.com",
		},
	}); ok {
		t.Fatalf("insecure external reference accepted: %#v", reference)
	}
}

func TestMergeReferencesKeepsOnlyToolAuthorizedDestinations(t *testing.T) {
	authorized := map[string]any{
		"title":  "权威来源",
		"source": "official",
		"destination": map[string]any{
			"kind": "external",
			"url":  "https://official.example/source",
		},
	}
	hallucinated := map[string]any{
		"title":  "模型臆造来源",
		"source": "model",
		"destination": map[string]any{
			"kind": "external",
			"url":  "https://hallucinated.example/source",
		},
	}

	merged := orchestration.MergeReferences(
		[]map[string]any{hallucinated},
		[]map[string]any{authorized},
	)

	if len(merged) != 1 {
		t.Fatalf("merged references = %#v, want one authorized reference", merged)
	}
	destination := merged[0]["destination"].(map[string]any)
	if stringValue(destination["url"]) != "https://official.example/source" {
		t.Fatalf("merged destination = %#v", destination)
	}
}

func TestUserProcessReferencePreservesCanonicalDestination(t *testing.T) {
	references := orchestration.UserProcessReferences([]map[string]any{{
		"sourceId": "source-ledger-1",
		"title":    "站内文章",
		"source":   "content",
		"destination": map[string]any{
			"kind":          "internal",
			"objectTypeRef": rtsearch.ObjectTypeContentPost,
			"objectId":      "post-1",
		},
	}})

	if len(references) != 1 {
		t.Fatalf("process references = %#v", references)
	}
	if references[0].Destination.Kind != "internal" ||
		references[0].Destination.ObjectTypeRef != rtsearch.ObjectTypeContentPost ||
		references[0].Destination.ObjectID != "post-1" ||
		references[0].SourceID != "source-ledger-1" {
		t.Fatalf("process destination = %#v", references[0].Destination)
	}
}

func stringValue(raw any) string {
	value, _ := raw.(string)
	return value
}
