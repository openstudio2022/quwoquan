// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
// readiness_case: get-skill-surface-placement-local
// readiness_case: put-skill-surface-placement-local
package local_contract

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	placementmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/messaging"
)

type placementStore struct {
	mu        sync.Mutex
	placement *model.Placement
}

func (store *placementStore) Get(
	_ context.Context,
	surfaceKind string,
	surfaceID string,
) (model.Placement, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.placement == nil || store.placement.SurfaceKind != surfaceKind || store.placement.SurfaceID != surfaceID {
		return model.Placement{}, model.ErrNotFound
	}
	return *store.placement, nil
}

func (store *placementStore) Apply(
	_ context.Context,
	command model.Command,
) (model.MutationResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.placement == nil {
		if command.ExpectedRevision != 0 {
			return model.MutationResult{}, model.ErrRevisionConflict
		}
		store.placement = &model.Placement{
			ID:                 "placement-1",
			SurfaceKind:        command.SurfaceKind,
			SurfaceID:          command.SurfaceID,
			Policy:             command.Policy,
			DisabledSkillIDs:   command.DisabledSkillIDs,
			Status:             command.Status,
			Revision:           1,
			CreatedByAccountID: command.ActorAccountID,
			UpdatedByAccountID: command.ActorAccountID,
			CreatedAt:          command.OccurredAt,
			UpdatedAt:          command.OccurredAt,
		}
		return model.MutationResult{Placement: *store.placement, Changed: true}, nil
	}
	if store.placement.Revision != command.ExpectedRevision {
		return model.MutationResult{}, model.ErrRevisionConflict
	}
	store.placement.DisabledSkillIDs = command.DisabledSkillIDs
	store.placement.Status = command.Status
	store.placement.Revision++
	store.placement.UpdatedAt = command.OccurredAt
	return model.MutationResult{Placement: *store.placement, Changed: true}, nil
}

type surfaceAuthority struct {
	member bool
	admin  bool
	err    error
}

func (authority surfaceAuthority) RequireMember(context.Context, string, string, string) error {
	if authority.err != nil {
		return authority.err
	}
	if !authority.member {
		return model.ErrForbidden
	}
	return nil
}

func (authority surfaceAuthority) RequireAdmin(context.Context, string, string, string) error {
	if authority.err != nil {
		return authority.err
	}
	if !authority.admin {
		return model.ErrForbidden
	}
	return nil
}

type sharedCatalog struct {
	err error
}

func (catalog sharedCatalog) ValidateSharedSkillIDs(context.Context, string, []string) error {
	return catalog.err
}

func TestPlacementAdminCASDisablesOnlySharedSkillRouting(t *testing.T) {
	t.Parallel()
	store := &placementStore{}
	now := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
	commands := application.NewCommandFacade(
		store,
		surfaceAuthority{member: true, admin: true},
		sharedCatalog{},
		func() time.Time { return now },
	)
	result, err := commands.Put(context.Background(), model.PutInput{
		SurfaceKind:      model.SurfaceConversation,
		SurfaceID:        "conversation-a",
		ActorAccountID:   "account-admin",
		ActorPersonaID:   "persona-admin",
		Policy:           model.PolicyAllSharedEligible,
		DisabledSkillIDs: []string{"travel_companion"},
		Status:           model.StatusActive,
		ExpectedRevision: 0,
		IdempotencyKey:   "placement-command-1",
	})
	if err != nil || !result.Changed || result.Placement.Revision != 1 {
		t.Fatalf("Put() result=%+v error=%v", result, err)
	}
	queries := application.NewQueryFacade(store, surfaceAuthority{member: true})
	loaded, err := queries.Get(
		context.Background(),
		"account-admin",
		"persona-admin",
		model.SurfaceConversation,
		"conversation-a",
	)
	if err != nil || loaded.ID != result.Placement.ID ||
		loaded.Revision != result.Placement.Revision {
		t.Fatalf("Get() placement=%+v error=%v", loaded, err)
	}
	allowed, err := queries.AllowsSkill(
		context.Background(),
		model.SurfaceConversation,
		"conversation-a",
		"travel_companion",
	)
	if err != nil || allowed {
		t.Fatalf("disabled Skill allowed=%v error=%v", allowed, err)
	}
	allowed, err = queries.AllowsSkill(
		context.Background(),
		model.SurfaceConversation,
		"conversation-a",
		"knowledge_general",
	)
	if err != nil || !allowed {
		t.Fatalf("non-disabled shared Skill allowed=%v error=%v", allowed, err)
	}
}

func TestPlacementRejectsNonAdminUnknownSkillAndUnavailableAuthority(t *testing.T) {
	t.Parallel()
	base := model.PutInput{
		SurfaceKind:      model.SurfaceCircle,
		SurfaceID:        "circle-a",
		ActorAccountID:   "account-a",
		ActorPersonaID:   "persona-a",
		Policy:           model.PolicyAllSharedEligible,
		DisabledSkillIDs: []string{},
		Status:           model.StatusActive,
		ExpectedRevision: 0,
		IdempotencyKey:   "placement-command-1",
	}
	store := &placementStore{}
	nonAdmin := application.NewCommandFacade(
		store,
		surfaceAuthority{member: true, admin: false},
		sharedCatalog{},
		nil,
	)
	if _, err := nonAdmin.Put(context.Background(), base); !errors.Is(err, model.ErrForbidden) {
		t.Fatalf("non-admin error=%v", err)
	}
	unknown := application.NewCommandFacade(
		store,
		surfaceAuthority{member: true, admin: true},
		sharedCatalog{err: catalogmodel.ErrSkillNotShared},
		nil,
	)
	if _, err := unknown.Put(context.Background(), base); !errors.Is(err, model.ErrUnknownSkill) {
		t.Fatalf("unknown shared Skill error=%v", err)
	}
	failClosed := application.NewCommandFacade(
		store,
		application.FailClosedSurfaceAuthority{},
		sharedCatalog{},
		nil,
	)
	if _, err := failClosed.Put(context.Background(), base); !errors.Is(err, model.ErrAuthorityUnavailable) {
		t.Fatalf("unavailable authority error=%v", err)
	}
}

func TestAssistantMembershipProjectorCreatesPreservesAndArchivesPlacement(t *testing.T) {
	t.Parallel()
	store := &placementStore{}
	now := time.Date(2026, 8, 2, 11, 0, 0, 0, time.UTC)
	projector := application.NewMembershipProjector(store, func() time.Time { return now })
	added := application.AssistantMembershipChange{
		EventID:        "chat-member-added-1",
		EventType:      application.AssistantConversationMemberAdded,
		ConversationID: "conversation-a",
		ActorAccountID: "account-owner",
		ActorPersonaID: "persona-owner",
		OccurredAt:     now,
	}
	if err := projector.Apply(t.Context(), added); err != nil {
		t.Fatalf("project assistant add: %v", err)
	}
	commands := application.NewCommandFacade(
		store,
		surfaceAuthority{member: true, admin: true},
		sharedCatalog{},
		func() time.Time { return now.Add(time.Minute) },
	)
	if _, err := commands.Put(t.Context(), model.PutInput{
		SurfaceKind:      model.SurfaceConversation,
		SurfaceID:        "conversation-a",
		ActorAccountID:   "account-owner",
		ActorPersonaID:   "persona-owner",
		Policy:           model.PolicyAllSharedEligible,
		DisabledSkillIDs: []string{"travel_companion"},
		Status:           model.StatusActive,
		ExpectedRevision: 1,
		IdempotencyKey:   "admin-disable-travel",
	}); err != nil {
		t.Fatalf("admin update: %v", err)
	}
	added.EventID = "chat-member-added-replayed-later"
	if err := projector.Apply(t.Context(), added); err != nil {
		t.Fatalf("repeat assistant add: %v", err)
	}
	current, err := store.Get(t.Context(), model.SurfaceConversation, "conversation-a")
	if err != nil || current.Revision != 2 || len(current.DisabledSkillIDs) != 1 ||
		current.DisabledSkillIDs[0] != "travel_companion" {
		t.Fatalf("projector overwrote admin policy: placement=%+v error=%v", current, err)
	}
	if err := projector.Apply(t.Context(), application.AssistantMembershipChange{
		EventID:        "chat-member-removed-1",
		EventType:      application.AssistantConversationMemberRemoved,
		ConversationID: "conversation-a",
		ActorAccountID: "account-owner",
		ActorPersonaID: "persona-owner",
		OccurredAt:     now.Add(2 * time.Minute),
	}); err != nil {
		t.Fatalf("project assistant removal: %v", err)
	}
	archived, err := store.Get(t.Context(), model.SurfaceConversation, "conversation-a")
	if err != nil || archived.Status != model.StatusArchived ||
		len(archived.DisabledSkillIDs) != 1 ||
		archived.DisabledSkillIDs[0] != "travel_companion" {
		t.Fatalf("archived placement=%+v error=%v", archived, err)
	}
}

func TestAssistantMembershipDurableConsumerProjectsDefaultPlacement(t *testing.T) {
	t.Parallel()
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"assistant-service-test",
		runtimemessaging.RedisMessageTransportFixture,
		redis,
		redis,
	)
	if err != nil {
		t.Fatal(err)
	}
	store := &placementStore{}
	consumer := placementmessaging.NewAssistantMembershipConsumer(
		transport,
		application.NewMembershipProjector(store, nil),
		"placement-worker",
		nil,
	)
	if err := consumer.EnsureGroup(t.Context()); err != nil {
		t.Fatal(err)
	}
	if _, err := redis.XAdd(
		t.Context(),
		placementmessaging.AssistantMembershipStream,
		map[string]string{
			"eventId":            "chat-member-added-1",
			"eventType":          application.AssistantConversationMemberAdded,
			"conversationId":     "conversation-a",
			"memberType":         "assistant",
			"invitedByAccountId": "account-owner",
			"invitedBy":          "persona-owner",
			"occurredAt":         "2026-08-02T11:00:00Z",
		},
	); err != nil {
		t.Fatal(err)
	}
	processed, err := consumer.ProcessOnce(t.Context())
	if err != nil || processed != 1 {
		t.Fatalf("ProcessOnce() processed=%d error=%v", processed, err)
	}
	placement, err := store.Get(t.Context(), model.SurfaceConversation, "conversation-a")
	if err != nil || placement.Status != model.StatusActive ||
		placement.Policy != model.PolicyAllSharedEligible {
		t.Fatalf("projected placement=%+v error=%v", placement, err)
	}
}
