// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package local_contract

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/mq"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	sfmodel "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/model"
)

type recordedMessageTransport struct {
	ephemeral []runtimemessaging.EphemeralMessage
	durable   []runtimemessaging.DurableMessage
}

func (transport *recordedMessageTransport) PublishEphemeral(
	_ context.Context,
	message runtimemessaging.EphemeralMessage,
) error {
	transport.ephemeral = append(transport.ephemeral, message)
	return nil
}

func (*recordedMessageTransport) SubscribeEphemeral(
	context.Context,
	...string,
) (runtimemessaging.EphemeralSubscription, error) {
	return nil, nil
}

func (transport *recordedMessageTransport) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	transport.durable = append(transport.durable, message)
	return "1-0", nil
}

func TestUserEventPublisherRetainsObjectOwnedMessageCoordinatesAndFields(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	now := time.Date(2026, time.July, 21, 12, 30, 0, 0, time.UTC)
	transport := &recordedMessageTransport{}
	publisher := mq.NewEventPublisher(transport)

	if err := publisher.PublishUserEvent(
		ctx,
		"UserProfileUpdated",
		"user-1",
		"actor-1",
		map[string]any{"nickname": "小趣"},
	); err != nil {
		t.Fatalf("publish user event: %v", err)
	}
	if err := publisher.AppendUserAccountEvent(
		ctx,
		accountports.UserAccountOutboxEvent{
			EventID:        "account-event-1",
			AccountID:      "account-1",
			AccountVersion: 2,
			EventType:      "UserAccountClosed",
			OccurredAt:     now,
		},
		map[string]any{
			"userId":       "account-1",
			"personaIds":   []string{"persona-1", "persona-2"},
			"accountState": "closed",
			"updatedAt":    now.Format(time.RFC3339Nano),
		},
	); err != nil {
		t.Fatalf("append account event: %v", err)
	}
	if err := publisher.PublishPersonaRelationship(
		ctx,
		relmodel.OutboxEvent{
			EventID:   "relationship-event-1",
			EventName: "PersonaFollowStateChanged",
			Payload: relmodel.OutboxPayload{
				PairID:                  "pair-1",
				SourcePersonaID:         "persona-1",
				TargetPersonaID:         "persona-2",
				Following:               true,
				ClearedFollowDirections: 1,
				Version:                 3,
				OccurredAt:              now,
			},
		},
	); err != nil {
		t.Fatalf("publish persona relationship: %v", err)
	}
	if err := publisher.PublishGreetingEvent(
		ctx,
		greetingapp.GreetingStreamEvent{
			EventID:                      "greeting-event-1",
			EventName:                    "GreetingRequested",
			GreetingID:                   "greeting-1",
			RequesterPersonaID:           "persona-1",
			TargetPersonaID:              "persona-2",
			Source:                       "profile",
			PromotedConversationID:       "conversation-1",
			TargetAllowsStrangerGreeting: true,
			OccurredAt:                   now,
		},
	); err != nil {
		t.Fatalf("publish greeting event: %v", err)
	}
	if err := publisher.PublishSubjectFollow(
		ctx,
		sfmodel.OutboxEvent{
			EventID:   "subject-follow-event-1",
			EventName: sfmodel.EventSubjectFollowStateChanged,
			Payload: sfmodel.EventPayload{
				ID:          "follow-1",
				PersonaID:   "persona-1",
				SubjectType: "homepage",
				SubjectID:   "homepage-1",
				State:       "following",
				Version:     4,
				OccurredAt:  now,
			},
		},
	); err != nil {
		t.Fatalf("publish subject follow: %v", err)
	}

	if len(transport.ephemeral) != 2 {
		t.Fatalf("ephemeral messages = %d, want 2", len(transport.ephemeral))
	}
	assertEphemeralUserEvent(
		t,
		transport.ephemeral[0],
		"UserProfileUpdated",
		"user-1",
		"actor-1",
	)
	assertEphemeralUserEvent(
		t,
		transport.ephemeral[1],
		"PersonaFollowStateChanged",
		"persona-2",
		"persona-1",
	)

	if len(transport.durable) != 4 {
		t.Fatalf("durable messages = %d, want 4", len(transport.durable))
	}
	assertDurableFields(t, transport.durable[0], mq.UserAccountEventStream, map[string]string{
		"eventId":        "account-event-1",
		"eventName":      "UserAccountClosed",
		"accountId":      "account-1",
		"accountVersion": "2",
		"payload":        `{"accountState":"closed","personaIds":["persona-1","persona-2"],"updatedAt":"2026-07-21T12:30:00Z","userId":"account-1"}`,
		"occurredAt":     now.Format(time.RFC3339Nano),
	})
	assertDurableFields(t, transport.durable[1], mq.PersonaRelationshipEventStream, map[string]string{
		"eventId":                 "relationship-event-1",
		"eventName":               "PersonaFollowStateChanged",
		"pairId":                  "pair-1",
		"sourcePersonaId":         "persona-1",
		"targetPersonaId":         "persona-2",
		"following":               "true",
		"version":                 "3",
		"occurredAt":              now.Format(time.RFC3339Nano),
		"clearedFollowDirections": "1",
	})
	assertDurableFields(t, transport.durable[2], mq.GreetingEventStream, map[string]string{
		"eventId":                      "greeting-event-1",
		"eventName":                    "GreetingRequested",
		"id":                           "greeting-1",
		"requesterPersonaId":           "persona-1",
		"targetPersonaId":              "persona-2",
		"targetAllowsStrangerGreeting": "true",
		"occurredAt":                   now.Format(time.RFC3339Nano),
		"source":                       "profile",
		"promotedConversationId":       "conversation-1",
	})
	assertDurableFields(t, transport.durable[3], mq.SubjectFollowEventStream, map[string]string{
		"eventId":     "subject-follow-event-1",
		"eventName":   sfmodel.EventSubjectFollowStateChanged,
		"id":          "follow-1",
		"personaId":   "persona-1",
		"subjectType": "homepage",
		"subjectId":   "homepage-1",
		"state":       "following",
		"version":     "4",
		"occurredAt":  now.Format(time.RFC3339Nano),
	})
}

func assertEphemeralUserEvent(
	t *testing.T,
	message runtimemessaging.EphemeralMessage,
	eventType, userID, actorID string,
) {
	t.Helper()
	if message.Channel != "event:user-profile" {
		t.Fatalf("ephemeral channel = %q, want event:user-profile", message.Channel)
	}
	var event mq.DomainEvent
	if err := json.Unmarshal(message.Payload, &event); err != nil {
		t.Fatalf("decode ephemeral event: %v", err)
	}
	if event.Type != eventType || event.UserID != userID || event.ActorID != actorID {
		t.Fatalf("ephemeral event = %+v, want type=%s user=%s actor=%s", event, eventType, userID, actorID)
	}
}

func assertDurableFields(
	t *testing.T,
	message runtimemessaging.DurableMessage,
	stream string,
	want map[string]string,
) {
	t.Helper()
	if message.Stream != stream {
		t.Fatalf("durable stream = %q, want %q", message.Stream, stream)
	}
	got := make(map[string]string, len(message.Fields))
	for _, field := range message.Fields {
		if _, duplicate := got[field.Name]; duplicate {
			t.Fatalf("durable stream %s has duplicate field %q", stream, field.Name)
		}
		got[field.Name] = field.Value
	}
	if len(got) != len(want) {
		t.Fatalf("durable fields = %#v, want %#v", got, want)
	}
	for name, value := range want {
		if got[name] != value {
			t.Fatalf("durable field %s[%s] = %q, want %q", stream, name, got[name], value)
		}
	}
}
