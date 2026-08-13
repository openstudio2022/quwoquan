package search

import (
	"context"
	"errors"
	"testing"
)

type failingSource struct{}

func (failingSource) Candidates(context.Context, RetrievePlan) ([]Document, error) {
	return nil, errors.New("store down")
}
func (failingSource) SourceName() string { return "failing" }

func TestNativeStoreBackendAggregatesSourcesAndSkipsFailures(t *testing.T) {
	contentSrc := SliceCandidateSource{Source: "content", Docs: []Document{{
		ObjectType: ObjectTypeContentPost, ObjectID: "post_1", Title: "露营攻略",
		ContentType: "article", Visibility: "public",
	}}}
	userSrc := SliceCandidateSource{Source: "user", Docs: []Document{{
		ObjectType: ObjectTypeUserProfile, ObjectID: "user_1", Title: "露营达人",
		Visibility: "public",
	}}}
	backend := NewNativeStoreBackend(contentSrc, failingSource{}, userSrc)

	plan, _ := PlanRequest(RetrieveRequest{
		Targets: []Target{TargetArticle, TargetUser},
		Terms:   []string{"露营"},
	}, Viewer{})

	cands, err := backend.Recall(context.Background(), plan)
	if err != nil {
		t.Fatalf("recall err=%v", err)
	}
	if len(cands) != 2 {
		t.Fatalf("expected 2 candidates from healthy sources, got %d", len(cands))
	}
}

func TestObjectTypesForTargets(t *testing.T) {
	got := ObjectTypesForTargets([]Target{TargetArticle, TargetPhoto, TargetChat})
	hasContent, hasChatMsg := false, false
	for _, ot := range got {
		if ot == ObjectTypeContentPost {
			hasContent = true
		}
		if ot == ObjectTypeChatMessage {
			hasChatMsg = true
		}
	}
	if !hasContent || !hasChatMsg {
		t.Fatalf("object types mapping incomplete: %#v", got)
	}
}
