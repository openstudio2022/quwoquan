package semantic_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
	"testing"
)

func TestProjectOnlyPublishedValidMentions(t *testing.T) {
	raw := []any{
		map[string]any{"kind": "entity", "status": "published", "targetRef": "/entity/地点/景区/九寨沟"},
		map[string]any{"kind": "tag", "status": "published", "targetRef": "Topic/旅行/四川"},
		map[string]any{"kind": "entity", "status": "pending_review", "candidateId": "candidate_entity_1"},
		map[string]any{"kind": "tag", "status": "offline", "targetRef": "Topic/旧标签"},
		map[string]any{"kind": "entity", "status": "published", "targetRef": "candidate:entity:bad"},
	}

	got := Project(raw)
	if len(got.EntityRefs) != 1 || got.EntityRefs[0] != "/entity/地点/景区/九寨沟" {
		t.Fatalf("entity refs = %#v", got.EntityRefs)
	}
	if len(got.TagRefs) != 1 || got.TagRefs[0] != "Topic/旅行/四川" {
		t.Fatalf("tag refs = %#v", got.TagRefs)
	}
	if got.InvalidPublishedCount != 1 {
		t.Fatalf("invalid published count = %d", got.InvalidPublishedCount)
	}
}

func TestValidateSuppliedRefsRejectsCandidateAndManualProjection(t *testing.T) {
	if err := ValidateSuppliedRefs(nil, []string{"candidate:entity:1"}, nil); err == nil {
		t.Fatal("expected candidate active ref rejection")
	}
	raw := []any{
		map[string]any{"kind": "tag", "status": "pending_review", "candidateId": "candidate_tag_1"},
	}
	if err := ValidateSuppliedRefs(raw, nil, []string{"Topic/未审核"}); err == nil {
		t.Fatal("expected manually supplied tag ref rejection")
	}
}

func TestApplyGovernanceEventPublishesThenOfflinesMention(t *testing.T) {
	raw := []any{
		map[string]any{
			"mentionId":   "mention_1",
			"kind":        "entity",
			"status":      "pending_review",
			"candidateId": "candidate_entity_1",
			"surface":     "九寨沟",
		},
	}
	published, count, err := ApplyGovernanceEvent(raw, GovernanceEvent{
		CandidateID: "candidate_entity_1",
		Kind:        "entity",
		Status:      "published",
		TargetRef:   "/entity/地点/景区/九寨沟",
	})
	if err != nil || count != 1 {
		t.Fatalf("publish event count=%d err=%v", count, err)
	}
	if refs := Project(published).EntityRefs; len(refs) != 1 {
		t.Fatalf("published refs = %#v", refs)
	}
	offline, count, err := ApplyGovernanceEvent(published, GovernanceEvent{
		CandidateID: "candidate_entity_1",
		Kind:        "entity",
		Status:      "offline",
	})
	if err != nil || count != 1 {
		t.Fatalf("offline event count=%d err=%v", count, err)
	}
	if refs := Project(offline).EntityRefs; len(refs) != 0 {
		t.Fatalf("offline refs = %#v", refs)
	}
}
