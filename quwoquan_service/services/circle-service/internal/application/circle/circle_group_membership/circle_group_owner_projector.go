package circlegroupmembership

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"quwoquan_service/runtime/operation"
	groupports "quwoquan_service/services/circle-service/internal/domain/circle/circle_group/ports"
)

type CircleGroupOwnerProjector struct{ commands *CommandFacade }

func NewCircleGroupOwnerProjector(commands *CommandFacade) *CircleGroupOwnerProjector {
	if commands == nil {
		panic("CircleGroupOwnerProjector requires CircleGroupMembership CommandFacade")
	}
	return &CircleGroupOwnerProjector{commands: commands}
}

func (projector *CircleGroupOwnerProjector) Publish(ctx context.Context, event groupports.OutboxEvent) error {
	if event.EventType != "CircleGroupCreated" {
		return nil
	}
	var payload struct {
		GroupID            string `json:"_id"`
		CircleID           string `json:"circleId"`
		CreatedByPersonaID string `json:"createdByPersonaId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode CircleGroupCreated owner payload: %w", err)
	}
	if strings.TrimSpace(payload.GroupID) == "" || strings.TrimSpace(payload.CircleID) == "" || strings.TrimSpace(payload.CreatedByPersonaID) == "" {
		return fmt.Errorf("CircleGroupCreated owner payload is incomplete")
	}
	projectorContext := operation.WithContext(ctx, operation.Context{
		OperationID: "circle.circle_group_membership.ActivateOwnerFromCircleGroupCreated",
		RequestID:   event.EventID, TraceID: event.EventID, IdempotencyKey: "circle-group-owner:" + event.EventID,
		Actor: operation.ActorContext{PersonaID: payload.CreatedByPersonaID},
	})
	_, err := projector.commands.ActivateOwner(projectorContext, payload.CircleID, payload.GroupID, payload.CreatedByPersonaID)
	return err
}

var _ groupports.OutboxPublisher = (*CircleGroupOwnerProjector)(nil)
