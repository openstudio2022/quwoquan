package post_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"reflect"
	"testing"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/runtime/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

func TestSubmitPostPublicationProjectsPublishedSemanticMentions(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := NewPostService(
		BindDataPorts(store),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	command := semanticPublicationCommand(
		"semantic-mention-publication",
		nil,
		[]postmodel.PostSemanticMention{
			{MentionId: "m_entity_published", Kind: "entity", Status: "published", TargetRef: "/entity/地点/景区/九寨沟"},
			{MentionId: "m_tag_published", Kind: "tag", Status: "published", TargetRef: "tag:topic:川西秋色"},
			{MentionId: "m_entity_pending", Kind: "entity", Status: "pending_review", CandidateId: "cand_huanglong"},
			{MentionId: "m_tag_rejected", Kind: "tag", Status: "rejected", TargetRef: "tag:topic:被驳回"},
		},
	)
	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), command.PublishIntentID),
		command,
	)
	if err != nil {
		t.Fatalf("SubmitPostPublication returned error: %v", err)
	}
	post, found := store.FindByID(context.Background(), receipt.PostID)
	if !found {
		t.Fatalf("post %q not found in store", receipt.PostID)
	}
	if got, want := post.EntityRefs, []string{"/entity/地点/景区/九寨沟"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("EntityRefs = %#v, want %#v", got, want)
	}
	if got, want := post.TagRefs, []string{"tag:topic:川西秋色"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("TagRefs = %#v, want %#v", got, want)
	}
}

func TestSubmitPostPublicationRejectsPublishedMentionWithInvalidTargetRef(t *testing.T) {
	service := NewPostService(
		BindDataPorts(testsupport.NewPostStore(nil)),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	command := semanticPublicationCommand(
		"semantic-mention-invalid-target",
		nil,
		[]postmodel.PostSemanticMention{{
			MentionId: "m_entity_bad", Kind: "entity", Status: "published", TargetRef: "entity:sight",
		}},
	)
	if _, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), command.PublishIntentID),
		command,
	); err == nil {
		t.Fatal("SubmitPostPublication should reject an invalid published targetRef")
	}
}

func TestSubmitPostPublicationRejectsClientSuppliedRefsDivergingFromMentions(t *testing.T) {
	service := NewPostService(
		BindDataPorts(testsupport.NewPostStore(nil)),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	command := semanticPublicationCommand(
		"semantic-mention-diverging-refs",
		[]string{"/entity/地点/景区/不存在的实体"},
		[]postmodel.PostSemanticMention{{
			MentionId: "m_entity_published", Kind: "entity", Status: "published", TargetRef: "/entity/地点/景区/九寨沟",
		}},
	)
	if _, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), command.PublishIntentID),
		command,
	); err == nil {
		t.Fatal("SubmitPostPublication should reject divergent entityRefs")
	}
}

func TestSubmitPostPublicationRequiresTransportIdempotencyContext(t *testing.T) {
	service := NewPostService(
		BindDataPorts(testsupport.NewPostStore(nil)),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	command := semanticPublicationCommand("semantic-no-transport-key", nil, nil)
	if _, err := service.SubmitPostPublication(context.Background(), command); err == nil {
		t.Fatal("SubmitPostPublication must reject a missing transport idempotency key")
	}
}

func semanticPublicationCommand(
	intentID string,
	entityRefs []string,
	semanticMentions []postmodel.PostSemanticMention,
) SubmitPostPublicationCommand {
	return SubmitPostPublicationCommand{
		PublishIntentID: intentID,
		LocalDraftID:    intentID + "-draft",
		AuthorID:        "author_sichuan",
		Content: postmodel.Post{
			ContentType:      "micro",
			Body:             "九寨沟秋天的海子真的很美",
			Visibility:       "public",
			EntityRefs:       entityRefs,
			SemanticMentions: semanticMentions,
		},
	}
}
