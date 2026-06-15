package application

import (
	"context"
	"testing"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postsemantic "quwoquan_service/services/content-service/internal/domain/post/semantic"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

type recordingProjector struct {
	events []ProjectorEvent
}

func (p *recordingProjector) Project(_ context.Context, event ProjectorEvent) error {
	p.events = append(p.events, event)
	return nil
}

func TestApplySemanticMentionGovernanceEventReprojectsActiveRefs(t *testing.T) {
	now := time.Now().UTC()
	store := persistence.NewPostStore([]postmodel.Post{{
		ID:          "post_semantic_1",
		AuthorId:    "author_1",
		ContentType: "article",
		Body:        "九寨沟仍作为普通正文参与检索",
		Status:      "published",
		Visibility:  "public",
		CreatedAt:   now,
		PublishedAt: now,
		SemanticMentions: []any{map[string]any{
			"mentionId":   "mention_1",
			"kind":        "entity",
			"surface":     "九寨沟",
			"status":      "pending_review",
			"candidateId": "candidate_entity_1",
		}},
	}})
	projector := &recordingProjector{}
	service := NewPostService(store, WithProjector(projector))

	published, err := service.ApplySemanticMentionGovernanceEvent(context.Background(), postsemantic.GovernanceEvent{
		CandidateID: "candidate_entity_1",
		Kind:        "entity",
		Status:      "published",
		TargetRef:   "/entity/地点/景区/九寨沟",
	})
	if err != nil {
		t.Fatal(err)
	}
	if published.MatchedPosts != 1 || published.ActiveReferenceChanges != 1 {
		t.Fatalf("published report = %+v", published)
	}
	post, ok := store.FindByID(context.Background(), "post_semantic_1")
	if !ok || len(post.EntityRefs) != 1 {
		t.Fatalf("published post = %+v ok=%v", post, ok)
	}

	offline, err := service.ApplySemanticMentionGovernanceEvent(context.Background(), postsemantic.GovernanceEvent{
		CandidateID: "candidate_entity_1",
		Kind:        "entity",
		Status:      "offline",
	})
	if err != nil {
		t.Fatal(err)
	}
	if offline.ActiveReferenceChanges != 1 {
		t.Fatalf("offline report = %+v", offline)
	}
	post, _ = store.FindByID(context.Background(), "post_semantic_1")
	if len(post.EntityRefs) != 0 {
		t.Fatalf("offline entity refs = %#v", post.EntityRefs)
	}
	if len(projector.events) != 2 {
		t.Fatalf("projected events = %d", len(projector.events))
	}
}
