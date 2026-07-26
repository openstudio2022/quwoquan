package circlebehaviorfact

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	generated "quwoquan_service/services/circle-service/generated/circle_management/circle"
	behaviorfactmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/domain/model"
	behaviorfactports "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/domain/ports"
)

type AppendCommand struct {
	CircleID  string
	EventType behaviorfactmodel.BehaviorEventType
}

type AppendResult struct {
	FactID           string `json:"factId"`
	IdempotentReplay bool   `json:"idempotentReplay"`
}

type Writer struct {
	sink    behaviorfactports.AppendSink
	circles behaviorfactports.CircleStateReader
	now     func() time.Time
}

func NewWriter(sink behaviorfactports.AppendSink, circles behaviorfactports.CircleStateReader) *Writer {
	if sink == nil || circles == nil {
		panic("CircleBehaviorFact Writer requires append sink and Circle state Reader")
	}
	return &Writer{sink: sink, circles: circles, now: time.Now}
}

func (writer *Writer) Append(ctx context.Context, command AppendCommand) (AppendResult, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Validate(operation.ActorPersonaOrDevice) != nil ||
		strings.TrimSpace(current.IdempotencyKey) == "" || strings.TrimSpace(current.SessionID) == "" {
		return AppendResult{}, generated.AppErrorFromInvalidArgument("trusted actor, session and Idempotency-Key are required")
	}
	circleID := strings.TrimSpace(command.CircleID)
	if circleID == "" || !behaviorfactmodel.IsValidBehaviorEventType(command.EventType) {
		return AppendResult{}, generated.AppErrorFromInvalidArgument("circleId and registered eventType are required")
	}
	state, found, err := writer.circles.ReadCircleState(ctx, circleID)
	if err != nil {
		return AppendResult{}, generated.AppErrorFromBehaviorFactWriteFailed(err.Error())
	}
	if !found {
		return AppendResult{}, generated.AppErrorFromCircleNotFound("CircleBehaviorFact target Circle not found")
	}
	if state != "active" {
		return AppendResult{}, generated.AppErrorFromInvalidArgument("CircleBehaviorFact target Circle is not active")
	}
	actorKind, actorID := trustedFactActor(current.Actor)
	factID := stableFactID(actorKind, actorID, current.IdempotencyKey)
	fact := behaviorfactmodel.CircleBehaviorFact{
		ID: factID, ActorKind: actorKind, CircleID: circleID, EventType: command.EventType,
		SessionID: strings.TrimSpace(current.SessionID), RequestID: strings.TrimSpace(current.RequestID),
		OccurredAt: writer.now().UTC(),
	}
	if actorKind == "persona" {
		fact.PersonaID = actorID
	} else {
		fact.DeviceActorID = actorID
	}
	digest, err := factCommandDigest(actorKind, actorID, current.SessionID, circleID, command.EventType)
	if err != nil {
		return AppendResult{}, generated.AppErrorFromBehaviorFactWriteFailed(err.Error())
	}
	receipt, err := writer.sink.Append(ctx, behaviorfactports.AppendRequest{Fact: fact, CommandDigest: digest})
	if err != nil {
		if errors.Is(err, behaviorfactmodel.ErrIdempotencyConflict) {
			return AppendResult{}, generated.AppErrorFromBehaviorFactIdempotencyConflict(err.Error())
		}
		return AppendResult{}, generated.AppErrorFromBehaviorFactWriteFailed(err.Error())
	}
	return AppendResult{FactID: receipt.FactID, IdempotentReplay: receipt.Replayed}, nil
}

func trustedFactActor(actor operation.ActorContext) (string, string) {
	if personaID := strings.TrimSpace(actor.PersonaID); personaID != "" {
		return "persona", personaID
	}
	return "device", strings.TrimSpace(actor.DeviceActorID)
}

func stableFactID(actorKind, actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(actorKind + "\x00" + actorID + "\x00" + strings.TrimSpace(idempotencyKey)))
	return "cbf_" + hex.EncodeToString(sum[:16])
}

func factCommandDigest(actorKind, actorID, sessionID, circleID string, eventType behaviorfactmodel.BehaviorEventType) (string, error) {
	payload, err := json.Marshal(struct {
		ActorKind string `json:"actorKind"`
		ActorID   string `json:"actorId"`
		SessionID string `json:"sessionId"`
		CircleID  string `json:"circleId"`
		EventType string `json:"eventType"`
	}{actorKind, actorID, strings.TrimSpace(sessionID), circleID, string(eventType)})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}
