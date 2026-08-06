package local_contract

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
)

type invitationProjectionMemoryStore struct {
	messages map[string]notification.AppMessage
}

func (store *invitationProjectionMemoryStore) UpsertGatheringInvitation(
	_ context.Context,
	message notification.AppMessage,
) (notification.AppMessage, bool, error) {
	if store.messages == nil {
		store.messages = make(map[string]notification.AppMessage)
	}
	existing, found := store.messages[message.MessageID]
	if found {
		current := existing.GatheringInvitation
		incoming := message.GatheringInvitation
		if current.ParticipationVersion > incoming.ParticipationVersion ||
			(current.ParticipationVersion == incoming.ParticipationVersion &&
				current.Status != "pending") ||
			(current.ParticipationVersion == incoming.ParticipationVersion &&
				current.Status == incoming.Status) {
			return existing, false, nil
		}
		message.Read = existing.Read
		message.CreatedAt = existing.CreatedAt
	}
	store.messages[message.MessageID] = message
	return message, true, nil
}

func (store *invitationProjectionMemoryStore) CancelGatheringInvitations(
	_ context.Context,
	gatheringID string,
) error {
	for key, message := range store.messages {
		card := message.GatheringInvitation
		if card != nil && card.GatheringID == gatheringID && card.Status == "pending" {
			card.Status = "cancelled"
			card.ActionIntents = []notification.AppMessageGatheringInvitationActionIntent{}
			store.messages[key] = message
		}
	}
	return nil
}

// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-002
func TestGatheringInvitationProjectionFoldsReplayAndTerminalEvents(t *testing.T) {
	store := &invitationProjectionMemoryStore{}
	projection, err := application.NewGatheringInvitationProjection(store)
	if err != nil {
		t.Fatalf("NewGatheringInvitationProjection: %v", err)
	}
	now := time.Now().UTC()
	pending := gatheringInvitationEvent(t, "event-1", 1, "pending", true, now)
	if err := projection.Handle(context.Background(), pending); err != nil {
		t.Fatalf("project pending: %v", err)
	}
	if err := projection.Handle(context.Background(), pending); err != nil {
		t.Fatalf("replay pending: %v", err)
	}
	if len(store.messages) != 1 {
		t.Fatalf("message count=%d", len(store.messages))
	}
	message := onlyInvitationMessage(t, store)
	if message.UserID != "persona-recipient" ||
		message.GatheringInvitation.Place.ExactMeetingPoint != "" {
		t.Fatalf("projected message=%+v", message)
	}
	if len(message.GatheringInvitation.ActionIntents) != 2 {
		t.Fatalf("pending actions=%+v", message.GatheringInvitation.ActionIntents)
	}

	revoked := gatheringInvitationEvent(t, "event-2", 2, "revoked", false, now.Add(time.Minute))
	if err := projection.Handle(context.Background(), revoked); err != nil {
		t.Fatalf("project revoked: %v", err)
	}
	if err := projection.Handle(context.Background(), pending); err != nil {
		t.Fatalf("late pending replay: %v", err)
	}
	message = onlyInvitationMessage(t, store)
	if message.GatheringInvitation.Status != "revoked" ||
		len(message.GatheringInvitation.ActionIntents) != 0 {
		t.Fatalf("revoked card=%+v", message.GatheringInvitation)
	}
}

// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-002
func TestGatheringCancellationInvalidatesPendingActions(t *testing.T) {
	store := &invitationProjectionMemoryStore{}
	projection, _ := application.NewGatheringInvitationProjection(store)
	now := time.Now().UTC()
	if err := projection.Handle(
		context.Background(),
		gatheringInvitationEvent(t, "event-1", 1, "pending", true, now),
	); err != nil {
		t.Fatalf("project pending: %v", err)
	}
	payload, _ := json.Marshal(map[string]any{
		"gatheringId": "g-1", "lifecycleStatus": "cancelled", "occurredAt": now,
	})
	if err := projection.Handle(context.Background(), application.InteractionStreamEvent{
		EventID: "cancel-1", EventType: "GatheringCancelled",
		Payload: payload, OccurredAt: now,
	}); err != nil {
		t.Fatalf("cancel Gathering cards: %v", err)
	}
	card := onlyInvitationMessage(t, store).GatheringInvitation
	if card.Status != "cancelled" || len(card.ActionIntents) != 0 {
		t.Fatalf("cancelled card=%+v", card)
	}
}

func gatheringInvitationEvent(
	t *testing.T,
	eventID string,
	version int64,
	status string,
	withActions bool,
	occurredAt time.Time,
) application.InteractionStreamEvent {
	t.Helper()
	actions := []map[string]any{}
	if withActions {
		actions = []map[string]any{
			{"action": "accept", "expectedGatheringVersion": 9, "expectedParticipationVersion": version},
			{"action": "decline", "expectedGatheringVersion": 9, "expectedParticipationVersion": version},
		}
	}
	payload, err := json.Marshal(map[string]any{
		"gatheringId": "g-1", "inviterPersonaId": "persona-inviter",
		"recipientPersonaId": "persona-recipient", "purposeSummary": "一起看展",
		"schedule":             map[string]any{"timezone": "Asia/Shanghai", "dateLabel": "2026-08-07"},
		"place":                map[string]any{"mode": "physical", "coarsePlaceLabel": "浦东新区"},
		"participationVersion": version, "status": status,
		"actionIntents": actions, "expiresAt": occurredAt.Add(time.Hour),
		"occurredAt": occurredAt,
	})
	if err != nil {
		t.Fatalf("marshal event: %v", err)
	}
	return application.InteractionStreamEvent{
		EventID: eventID, EventType: "GatheringInvitationChanged",
		Payload: payload, OccurredAt: occurredAt,
	}
}

func onlyInvitationMessage(
	t *testing.T,
	store *invitationProjectionMemoryStore,
) notification.AppMessage {
	t.Helper()
	for _, message := range store.messages {
		return message
	}
	t.Fatal("invitation message not found")
	return notification.AppMessage{}
}
