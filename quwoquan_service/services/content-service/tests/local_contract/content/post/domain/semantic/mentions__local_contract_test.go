package semantic_test

import (
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
	"testing"
)

func TestProjectOnlyPublishedValidMentions(t *testing.T) {
	raw := []postmodel.PostSemanticMention{
		{Kind: "entity", Status: "published", TargetRef: "/entity/地点/景区/九寨沟"},
		{Kind: "tag", Status: "published", TargetRef: "Topic/旅行/四川"},
		{Kind: "entity", Status: "pending_review", CandidateId: "candidate_entity_1"},
		{Kind: "tag", Status: "offline", TargetRef: "Topic/旧标签"},
		{Kind: "entity", Status: "published", TargetRef: "candidate:entity:bad"},
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
	raw := []postmodel.PostSemanticMention{
		{Kind: "tag", Status: "pending_review", CandidateId: "candidate_tag_1"},
	}
	if err := ValidateSuppliedRefs(raw, nil, []string{"Topic/未审核"}); err == nil {
		t.Fatal("expected manually supplied tag ref rejection")
	}
}

func TestApplyGovernanceEventPublishesThenOfflinesMention(t *testing.T) {
	raw := []postmodel.PostSemanticMention{
		{
			MentionId:   "mention_1",
			Kind:        "entity",
			Status:      "pending_review",
			CandidateId: "candidate_entity_1",
			Surface:     "九寨沟",
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
