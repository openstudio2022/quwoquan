package assistant_run_test

import (
	"errors"
	"testing"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	presentation "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
)

func TestPresentationStreamAppliesOrderedSnapshotPatchCommitAndIdempotentReplay(t *testing.T) {
	template := validPresentationTemplate()
	document := presentation.Document{
		TemplateRef:       presentation.TemplateRef(template),
		TemplateDigest:    template.AssetDigest,
		Revision:          1,
		RootNodeID:        template.RootNodeID,
		Nodes:             template.Nodes,
		FallbackMarkdown:  template.FallbackMarkdown,
		FallbackPlainText: "fallback",
	}
	projection := presentation.NewStreamProjection()
	snapshot := presentation.StreamEvent{
		Type:     generated.AssistantStreamEventTypePresentationSnapshot,
		Revision: 1,
		Document: &document,
	}
	if err := projection.Apply(snapshot); err != nil {
		t.Fatalf("Apply(snapshot) error = %v", err)
	}
	if err := projection.Apply(snapshot); err != nil {
		t.Fatalf("Apply(idempotent snapshot) error = %v", err)
	}
	updatedTitle := template.Nodes[1]
	updatedTitle.Title = "updated title"
	patch := presentation.StreamEvent{
		Type:         generated.AssistantStreamEventTypePresentationPatch,
		BaseRevision: 1,
		Revision:     2,
		Patches: []presentation.NodePatch{{
			Operation: presentation.PatchReplace,
			NodeID:    updatedTitle.NodeID,
			Node:      &updatedTitle,
		}},
	}
	if err := projection.Apply(patch); err != nil {
		t.Fatalf("Apply(patch) error = %v", err)
	}
	commit := presentation.StreamEvent{
		Type:         generated.AssistantStreamEventTypePresentationCommit,
		BaseRevision: 2,
		Revision:     3,
	}
	if err := projection.Apply(commit); err != nil {
		t.Fatalf("Apply(commit) error = %v", err)
	}
	result, committed := projection.Snapshot()
	if !committed || result.Revision != 3 || result.Nodes[1].Title != "updated title" {
		t.Fatalf("projection snapshot = %#v committed=%v", result, committed)
	}
	if err := projection.Apply(commit); err != nil {
		t.Fatalf("Apply(idempotent commit) error = %v", err)
	}
}

func TestPresentationStreamRejectsOutOfOrderConflictAndUnsafeTreePatch(t *testing.T) {
	template := validPresentationTemplate()
	document := presentation.Document{
		TemplateRef:       presentation.TemplateRef(template),
		TemplateDigest:    template.AssetDigest,
		Revision:          1,
		RootNodeID:        template.RootNodeID,
		Nodes:             template.Nodes,
		FallbackMarkdown:  template.FallbackMarkdown,
		FallbackPlainText: "fallback",
	}
	projection := presentation.NewStreamProjection()
	if err := projection.Apply(presentation.StreamEvent{
		Type:     generated.AssistantStreamEventTypePresentationSnapshot,
		Revision: 1,
		Document: &document,
	}); err != nil {
		t.Fatal(err)
	}
	if err := projection.Apply(presentation.StreamEvent{
		Type:         generated.AssistantStreamEventTypePresentationCommit,
		BaseRevision: 3,
		Revision:     4,
	}); !errors.Is(err, presentation.ErrPresentationRevision) {
		t.Fatalf("out-of-order error = %v", err)
	}
	if err := projection.Apply(presentation.StreamEvent{
		Type:         generated.AssistantStreamEventTypePresentationPatch,
		BaseRevision: 1,
		Revision:     2,
		Patches: []presentation.NodePatch{{
			Operation: presentation.PatchRemove,
			NodeID:    template.RootNodeID,
		}},
	}); !errors.Is(err, presentation.ErrPresentationRevision) {
		t.Fatalf("root removal error = %v", err)
	}
	conflictingDocument := document
	conflictingDocument.FallbackMarkdown = "different"
	if err := projection.Apply(presentation.StreamEvent{
		Type:     generated.AssistantStreamEventTypePresentationSnapshot,
		Revision: 1,
		Document: &conflictingDocument,
	}); !errors.Is(err, presentation.ErrPresentationRevision) {
		t.Fatalf("same-revision conflict error = %v", err)
	}
}
