package application

import (
	"encoding/json"
	"strings"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/event"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

func (o *CallOrchestrator) buildEvent(
	eventType string,
	session *model.CallSession,
	actorID string,
	payload CallEventPayload,
	now time.Time,
	recipients []string,
) CallOutboxEvent {
	targetPersonaID := ""
	if eventType == event.CallRinging && len(recipients) == 1 {
		targetPersonaID = strings.TrimSpace(recipients[0])
	}
	aggregateVersion := session.Version + 1
	eventID := eventIdentifier(
		session.ID,
		eventType,
		aggregateVersion,
		targetPersonaID,
	)
	payload.CallID = session.ID
	payload.EventID = eventID
	payload.CallType = session.CallType
	payload.InitiatorID = session.InitiatorID
	payload.InitiatorRingtoneID = session.InitiatorRingtoneID
	payload.ConversationID = session.ConversationID
	payload.CircleID = session.CircleID
	payload.MaxParticipants = session.MaxParticipants
	payload.UserID = actorID
	payload.Status = session.Status
	payload.ParticipantCount = session.ParticipantCount
	payload.EndReason = session.EndReason
	payload.DurationMs = session.DurationMs
	if session.StartedAt != nil {
		payload.StartedAt = session.StartedAt.UTC().Format(time.RFC3339Nano)
	}
	if session.EndedAt != nil {
		payload.EndedAt = session.EndedAt.UTC().Format(time.RFC3339Nano)
	}
	if eventType == event.CallRinging {
		payload.TargetPersonaID = targetPersonaID
		payload.CallerName = actorID
		payload.CallerAvatarURL = ""
		payload.SourceLabel = callSourceLabel(session)
		payload.TrustRelation = callTrustRelation(session)
		payload.DeliveryKey = incomingCallDeliveryKey(
			session.ID,
			targetPersonaID,
		)
		payload.ExpiresAt = now.Add(
			callRingingTTL(session),
		).UTC().Format(time.RFC3339Nano)
	}
	if participant := participantOf(session, actorID); participant != nil {
		payload.Role = participant.Role
	}
	// wire type（call.ringing 等）与 events.yaml client_ws_type 同源，
	// 是客户端消费契约；领域事件名只作为 outbox EventType 存档。
	body, _ := json.Marshal(callEventBody{
		Type:       signalWireType(eventType),
		CallID:     session.ID,
		ActorID:    actorID,
		Payload:    payload,
		Recipients: recipients,
		Timestamp:  now,
	})
	return CallOutboxEvent{
		EventID:          eventID,
		EventType:        eventType,
		AggregateID:      session.ID,
		AggregateVersion: aggregateVersion,
		DeliveryKey:      payload.DeliveryKey,
		Payload:          body,
		OccurredAt:       now,
	}
}

func (o *CallOrchestrator) buildRingingEvents(
	session *model.CallSession,
	actorID string,
	payload CallEventPayload,
	now time.Time,
	targets []string,
) []CallOutboxEvent {
	seen := make(map[string]struct{}, len(targets))
	events := make([]CallOutboxEvent, 0, len(targets))
	for _, target := range targets {
		target = strings.TrimSpace(target)
		if target == "" || target == actorID {
			continue
		}
		if _, exists := seen[target]; exists {
			continue
		}
		seen[target] = struct{}{}
		events = append(
			events,
			o.buildEvent(
				event.CallRinging,
				session,
				actorID,
				payload,
				now,
				[]string{target},
			),
		)
	}
	return events
}

type callEventBody struct {
	Type       string           `json:"type"`
	CallID     string           `json:"callId"`
	ActorID    string           `json:"actorId,omitempty"`
	Payload    CallEventPayload `json:"payload"`
	Recipients []string         `json:"recipients"`
	Timestamp  time.Time        `json:"timestamp"`
}

func decodeRecipients(evt CallOutboxEvent) []string {
	var body callEventBody
	if err := json.Unmarshal(evt.Payload, &body); err != nil {
		return nil
	}
	return body.Recipients
}

// participantIDs 返回事件接收者。ringing 只推给发起者以外的被邀人（来电提示），
// 其余事件推给全部参与者。
func (o *CallOrchestrator) participantIDs(
	session *model.CallSession,
	actorID string,
	ringingOnly bool,
) []string {
	ids := make([]string, 0, len(session.Participants))
	for _, participant := range session.Participants {
		if ringingOnly && participant.UserID == actorID {
			continue
		}
		ids = append(ids, participant.UserID)
	}
	return ids
}
