package application

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
)

func TestCallRingingOutboxPayloadIsDurableAndStable(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 20, 14, 0, 0, 0, time.UTC)
	callID := uuid.NewString()
	session := &model.CallSession{
		ID:              callID,
		Version:         4,
		CallType:        model.CallTypeVideo,
		Status:          model.StatusRinging,
		InitiatorID:     "persona-caller",
		ConversationID:  "conversation-1",
		MaxParticipants: model.MaxParticipants1v1,
		Participants: []model.Participant{
			{UserID: "persona-caller"},
			{UserID: "persona-target"},
		},
	}
	orchestrator := &CallOrchestrator{}

	events := orchestrator.buildRingingEvents(
		session,
		"persona-caller",
		CallEventPayload{},
		now,
		[]string{"persona-target", "persona-target"},
	)
	if len(events) != 1 {
		t.Fatalf("ringing events=%d, want one per distinct target", len(events))
	}
	event := events[0]
	if _, err := uuid.Parse(callID); err != nil {
		t.Fatalf("callId must remain RFC4122 UUID: %v", err)
	}
	var envelope callEventBody
	if err := json.Unmarshal(event.Payload, &envelope); err != nil {
		t.Fatalf("decode CallRinging envelope: %v", err)
	}
	payload := envelope.Payload
	expectedDigest := sha256.Sum256(
		[]byte(callID + "\x00" + "persona-target"),
	)
	expectedDeliveryKey := "sha256:" + hex.EncodeToString(expectedDigest[:])
	if payload.EventID != event.EventID ||
		payload.CallID != callID ||
		payload.TargetPersonaID != "persona-target" ||
		payload.CallType != model.CallTypeVideo ||
		payload.CallerName != "persona-caller" ||
		payload.CallerAvatarURL != "" ||
		payload.SourceLabel != "conversation" ||
		payload.TrustRelation != "known" ||
		payload.DeliveryKey != expectedDeliveryKey ||
		event.DeliveryKey != expectedDeliveryKey {
		t.Fatalf("unexpected CallRinging payload: %+v event=%+v", payload, event)
	}
	expiresAt, err := time.Parse(time.RFC3339Nano, payload.ExpiresAt)
	if err != nil || !expiresAt.Equal(now.Add(30*time.Second)) {
		t.Fatalf("1v1 expiresAt=%q err=%v", payload.ExpiresAt, err)
	}

	replayed := orchestrator.buildRingingEvents(
		session,
		"persona-caller",
		CallEventPayload{},
		now,
		[]string{"persona-target"},
	)[0]
	if replayed.EventID != event.EventID ||
		replayed.DeliveryKey != event.DeliveryKey {
		t.Fatalf("replay identity drifted: first=%+v replay=%+v", event, replayed)
	}

	session.MaxParticipants = model.MaxParticipantsGroup
	group := orchestrator.buildRingingEvents(
		session,
		"persona-caller",
		CallEventPayload{},
		now,
		[]string{"persona-group-target"},
	)[0]
	if err := json.Unmarshal(group.Payload, &envelope); err != nil {
		t.Fatalf("decode group CallRinging envelope: %v", err)
	}
	groupExpiry, err := time.Parse(time.RFC3339Nano, envelope.Payload.ExpiresAt)
	if err != nil || !groupExpiry.Equal(now.Add(60*time.Second)) {
		t.Fatalf("group expiresAt=%q err=%v", envelope.Payload.ExpiresAt, err)
	}
	if envelope.Payload.TrustRelation != "possibly_unknown" {
		t.Fatalf("group trustRelation=%q", envelope.Payload.TrustRelation)
	}
}
