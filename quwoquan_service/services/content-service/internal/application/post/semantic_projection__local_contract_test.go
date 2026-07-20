package post

import (
	"context"
	"reflect"
	"testing"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/testsupport"
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
		[]any{
			map[string]any{
				"mentionId": "m_entity_published",
				"kind":      "entity",
				"status":    "published",
				"targetRef": "/entity/地点/景区/九寨沟",
			},
			map[string]any{
				"mentionId": "m_tag_published",
				"kind":      "tag",
				"status":    "published",
				"targetRef": "tag:topic:川西秋色",
			},
			map[string]any{
				"mentionId":   "m_entity_pending",
				"kind":        "entity",
				"status":      "pending_review",
				"candidateId": "cand_huanglong",
			},
			map[string]any{
				"mentionId": "m_tag_rejected",
				"kind":      "tag",
				"status":    "rejected",
				"targetRef": "tag:topic:被驳回",
			},
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
		[]any{map[string]any{
			"mentionId": "m_entity_bad",
			"kind":      "entity",
			"status":    "published",
			"targetRef": "entity:sight",
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
		[]any{map[string]any{
			"mentionId": "m_entity_published",
			"kind":      "entity",
			"status":    "published",
			"targetRef": "/entity/地点/景区/九寨沟",
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
	semanticMentions []any,
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
