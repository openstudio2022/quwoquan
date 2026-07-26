package reaction

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"strings"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

func decodeReactionStateChangedFact(
	fact reactionports.OutboxFact,
) (reactionStateChangedFact, error) {
	if fact.EventType != EventTypeContentReactionSet &&
		fact.EventType != EventTypeContentReactionCleared {
		return reactionStateChangedFact{}, fmt.Errorf(
			"unsupported ContentReaction event type %q",
			fact.EventType,
		)
	}
	var payload reactionStateChangedFact
	decoder := json.NewDecoder(bytes.NewReader(fact.Payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return reactionStateChangedFact{}, fmt.Errorf(
			"decode ContentReaction projection fact: %w",
			err,
		)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return reactionStateChangedFact{}, fmt.Errorf(
			"ContentReaction projection fact contains trailing JSON",
		)
	}
	if strings.TrimSpace(payload.TargetKind) == "" ||
		strings.TrimSpace(payload.TargetID) == "" ||
		strings.TrimSpace(payload.ReactionID) == "" ||
		strings.TrimSpace(payload.ActorID) == "" ||
		strings.TrimSpace(payload.ActorDimension) == "" ||
		strings.TrimSpace(payload.IdempotencyKey) == "" ||
		payload.Version <= 0 || payload.OccurredAt.IsZero() ||
		strings.TrimSpace(fact.AggregateID) != strings.TrimSpace(payload.ReactionID) ||
		fact.AggregateVersion != payload.Version ||
		fact.OccurredAt.IsZero() || !fact.OccurredAt.Equal(payload.OccurredAt) {
		return reactionStateChangedFact{}, fmt.Errorf(
			"ContentReaction projection fact identity is incomplete",
		)
	}
	actor, err := reactiondomain.NewActor(
		reactiondomain.ActorDimension(payload.ActorDimension),
		payload.ActorID,
	)
	if err != nil {
		return reactionStateChangedFact{}, fmt.Errorf(
			"ContentReaction projection fact actor is invalid: %w",
			err,
		)
	}
	target, err := reactiondomain.NewTarget(
		reactiondomain.TargetKind(payload.TargetKind),
		payload.TargetID,
	)
	if err != nil {
		return reactionStateChangedFact{}, fmt.Errorf(
			"ContentReaction projection fact target is invalid: %w",
			err,
		)
	}
	identity, err := reactiondomain.NewIdentity(target, actor)
	if err != nil || identity.AggregateID() != payload.ReactionID {
		return reactionStateChangedFact{}, fmt.Errorf("ContentReaction projection identity is invalid")
	}
	value := reactiondomain.Value(payload.Reaction)
	if err := value.ValidateFor(target.Kind); err != nil {
		return reactionStateChangedFact{}, fmt.Errorf("ContentReaction projection value is invalid: %w", err)
	}
	if (fact.EventType == EventTypeContentReactionCleared) != (value == reactiondomain.ValueNone) {
		return reactionStateChangedFact{}, fmt.Errorf(
			"ContentReaction event %q cannot carry reaction %q",
			fact.EventType,
			payload.Reaction,
		)
	}
	return payload, nil
}
