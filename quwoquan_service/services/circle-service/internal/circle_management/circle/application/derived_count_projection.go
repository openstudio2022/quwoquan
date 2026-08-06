package application

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

const (
	DerivedCountSourceMembership    = "circle_membership"
	DerivedCountSourcePostPlacement = "circle_post_placement"
	DerivedCountSourceBehaviorFact  = "circle_behavior_fact"
)

// DerivedCountEvent is the target-owned representation of an authored
// lifecycle edge into circle.circle. Source-object outbox record types stay at
// their source boundary and are converted only by the composition root.
type DerivedCountEvent struct {
	Source           string
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          json.RawMessage
	OccurredAt       time.Time
}

type DerivedCountProjection interface {
	Apply(context.Context, DerivedCountEvent) error
}

type CircleMemberCountProjectionHandler struct{ projection DerivedCountProjection }
type CirclePostCountProjectionHandler struct{ projection DerivedCountProjection }
type CircleWeeklyActiveProjectionHandler struct{ projection DerivedCountProjection }

func NewCircleMemberCountProjectionHandler(projection DerivedCountProjection) *CircleMemberCountProjectionHandler {
	return &CircleMemberCountProjectionHandler{projection: projection}
}

func NewCirclePostCountProjectionHandler(projection DerivedCountProjection) *CirclePostCountProjectionHandler {
	return &CirclePostCountProjectionHandler{projection: projection}
}

func NewCircleWeeklyActiveProjectionHandler(projection DerivedCountProjection) *CircleWeeklyActiveProjectionHandler {
	return &CircleWeeklyActiveProjectionHandler{projection: projection}
}

func (handler *CircleMemberCountProjectionHandler) Apply(ctx context.Context, event DerivedCountEvent) error {
	if err := requireDerivedCountHandler(handler != nil && handler.projection != nil, event, DerivedCountSourceMembership); err != nil {
		return err
	}
	switch event.EventType {
	case "CircleMembershipRequested", "CircleMembershipJoined", "CircleMembershipApproved",
		"CircleMembershipLeft", "CircleMembershipRoleChanged", "CircleMembershipRejected":
		return handler.projection.Apply(ctx, event)
	default:
		return fmt.Errorf("unsupported CircleMembership event type %q", event.EventType)
	}
}

func (handler *CirclePostCountProjectionHandler) Apply(ctx context.Context, event DerivedCountEvent) error {
	if err := requireDerivedCountHandler(handler != nil && handler.projection != nil, event, DerivedCountSourcePostPlacement); err != nil {
		return err
	}
	switch event.EventType {
	case "CirclePostPlaced", "CirclePostPlacementRemoved", "CirclePostPlacementPresentationChanged":
		return handler.projection.Apply(ctx, event)
	default:
		return fmt.Errorf("unsupported CirclePostPlacement event type %q", event.EventType)
	}
}

func (handler *CircleWeeklyActiveProjectionHandler) Apply(ctx context.Context, event DerivedCountEvent) error {
	if err := requireDerivedCountHandler(handler != nil && handler.projection != nil, event, DerivedCountSourceBehaviorFact); err != nil {
		return err
	}
	if event.EventType != "CircleBehaviorFactAppended" {
		return fmt.Errorf("unsupported CircleBehaviorFact event type %q", event.EventType)
	}
	return handler.projection.Apply(ctx, event)
}

func requireDerivedCountHandler(configured bool, event DerivedCountEvent, source string) error {
	if !configured {
		return fmt.Errorf("Circle derived-count projection handler is not configured")
	}
	if strings.TrimSpace(event.Source) != source {
		return fmt.Errorf("Circle derived-count source %q does not match %q", event.Source, source)
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || len(event.Payload) == 0 {
		return fmt.Errorf("Circle derived-count event identity is incomplete")
	}
	if source != DerivedCountSourceBehaviorFact && event.AggregateVersion <= 0 {
		return fmt.Errorf("Circle derived-count aggregate version must be positive")
	}
	return nil
}
