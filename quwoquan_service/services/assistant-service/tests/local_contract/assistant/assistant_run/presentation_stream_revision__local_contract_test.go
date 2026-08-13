package assistant_run_test

import (
	"errors"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	presentation "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
)

func TestPresentationStreamAppliesSnapshotCommitReplacementAndIdempotentReplay(t *testing.T) {
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
	commit := presentation.StreamEvent{
		Type:         generated.AssistantStreamEventTypePresentationCommit,
		BaseRevision: 1,
		Revision:     2,
	}
	if err := projection.Apply(commit); err != nil {
		t.Fatalf("Apply(commit) error = %v", err)
	}
	if err := projection.Apply(commit); err != nil {
		t.Fatalf("Apply(idempotent commit) error = %v", err)
	}
	replacement := document
	replacement.Revision = 3
	replacement.Nodes = append([]presentation.Node(nil), document.Nodes...)
	replacement.Nodes[1].Title = "updated title"
	replacementSnapshot := presentation.StreamEvent{
		Type:         generated.AssistantStreamEventTypePresentationSnapshot,
		BaseRevision: 2,
		Revision:     3,
		Document:     &replacement,
	}
	if err := projection.Apply(replacementSnapshot); err != nil {
		t.Fatalf("Apply(replacement snapshot) error = %v", err)
	}
	replacementCommit := presentation.StreamEvent{
		Type:         generated.AssistantStreamEventTypePresentationCommit,
		BaseRevision: 3,
		Revision:     4,
	}
	if err := projection.Apply(replacementCommit); err != nil {
		t.Fatalf("Apply(replacement commit) error = %v", err)
	}
	result, committed := projection.Snapshot()
	if !committed || result.Revision != 4 || result.Nodes[1].Title != "updated title" {
		t.Fatalf("projection snapshot = %#v committed=%v", result, committed)
	}
}

func TestPresentationStreamRejectsOutOfOrderConflictAndInvalidReplacement(t *testing.T) {
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
	conflictingDocument := document
	conflictingDocument.FallbackMarkdown = "different"
	if err := projection.Apply(presentation.StreamEvent{
		Type:     generated.AssistantStreamEventTypePresentationSnapshot,
		Revision: 1,
		Document: &conflictingDocument,
	}); !errors.Is(err, presentation.ErrPresentationRevision) {
		t.Fatalf("same-revision conflict error = %v", err)
	}
	if err := projection.Apply(presentation.StreamEvent{
		Type:         generated.AssistantStreamEventTypePresentationCommit,
		BaseRevision: 1,
		Revision:     2,
	}); err != nil {
		t.Fatalf("Apply(commit) error = %v", err)
	}
	committedReplacement := document
	committedReplacement.Revision = 3
	committedReplacement.CommittedAt = time.Date(
		2026, time.August, 8, 0, 0, 0, 0, time.UTC,
	)
	if err := projection.Apply(presentation.StreamEvent{
		Type:         generated.AssistantStreamEventTypePresentationSnapshot,
		BaseRevision: 2,
		Revision:     3,
		Document:     &committedReplacement,
	}); !errors.Is(err, presentation.ErrPresentationRevision) {
		t.Fatalf("committed replacement snapshot error = %v", err)
	}
}
