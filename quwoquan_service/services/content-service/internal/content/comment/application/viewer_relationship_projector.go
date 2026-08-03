package comment

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

// ViewerRelationshipEventName is the typed subset of User PersonaRelationship
// lifecycle facts that affects Comment read presentation.
type ViewerRelationshipEventName string

const (
	ViewerFollowStateChanged ViewerRelationshipEventName = "PersonaFollowStateChanged"
	ViewerBlocked            ViewerRelationshipEventName = "PersonaBlocked"
	ViewerUnblocked          ViewerRelationshipEventName = "PersonaUnblocked"
)

// ViewerRelationshipEvent carries the immutable identity and ordering fields
// published by user.PersonaRelationship. Dynamic stream maps are decoded only
// by the inbound messaging adapter.
type ViewerRelationshipEvent struct {
	EventID         string
	EventName       ViewerRelationshipEventName
	PairID          string
	SourcePersonaID string
	TargetPersonaID string
	Following       bool
	Version         int64
	OccurredAt      time.Time
}

// ViewerRelationshipProjectionWriter is Comment's object-local projection
// port. The User service remains authoritative; Comment owns only its bounded
// read model and inbox.
type ViewerRelationshipProjectionWriter interface {
	ApplyFollowState(context.Context, ViewerRelationshipEvent) error
	ApplyBlockState(context.Context, ViewerRelationshipEvent, bool) error
	RecordAppliedEvent(context.Context, ViewerRelationshipEvent) (bool, error)
}

type ViewerRelationshipProjector struct {
	writer ViewerRelationshipProjectionWriter
}

func NewViewerRelationshipProjector(
	writer ViewerRelationshipProjectionWriter,
) *ViewerRelationshipProjector {
	return &ViewerRelationshipProjector{writer: writer}
}

// Apply is replay-safe: every state mutation is version guarded and the inbox
// marker is written last. A crash before the marker can therefore be retried
// without allowing an older relationship state to overwrite a newer one.
func (projector *ViewerRelationshipProjector) Apply(
	ctx context.Context,
	event ViewerRelationshipEvent,
) error {
	if projector == nil || projector.writer == nil {
		return errors.New("comment viewer relationship projector is not configured")
	}
	if err := ValidateViewerRelationshipEvent(event); err != nil {
		return err
	}
	switch event.EventName {
	case ViewerFollowStateChanged:
		if err := projector.writer.ApplyFollowState(ctx, event); err != nil {
			return err
		}
	case ViewerBlocked:
		// Blocking irreversibly clears both follow directions for this version;
		// unblocking never restores an earlier relationship.
		for _, direction := range []ViewerRelationshipEvent{
			{
				EventID: event.EventID, EventName: ViewerFollowStateChanged,
				PairID: event.PairID, SourcePersonaID: event.SourcePersonaID,
				TargetPersonaID: event.TargetPersonaID, Following: false,
				Version: event.Version, OccurredAt: event.OccurredAt,
			},
			{
				EventID: event.EventID, EventName: ViewerFollowStateChanged,
				PairID: event.PairID, SourcePersonaID: event.TargetPersonaID,
				TargetPersonaID: event.SourcePersonaID, Following: false,
				Version: event.Version, OccurredAt: event.OccurredAt,
			},
		} {
			if err := projector.writer.ApplyFollowState(ctx, direction); err != nil {
				return err
			}
		}
		if err := projector.writer.ApplyBlockState(ctx, event, true); err != nil {
			return err
		}
	case ViewerUnblocked:
		if err := projector.writer.ApplyBlockState(ctx, event, false); err != nil {
			return err
		}
	default:
		return fmt.Errorf("unsupported persona relationship event %q", event.EventName)
	}
	_, err := projector.writer.RecordAppliedEvent(ctx, event)
	return err
}

func ValidateViewerRelationshipEvent(event ViewerRelationshipEvent) error {
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.PairID) == "" ||
		strings.TrimSpace(event.SourcePersonaID) == "" ||
		strings.TrimSpace(event.TargetPersonaID) == "" ||
		event.SourcePersonaID == event.TargetPersonaID ||
		event.Version <= 0 || event.OccurredAt.IsZero() {
		return errors.New("invalid comment viewer relationship event")
	}
	switch event.EventName {
	case ViewerFollowStateChanged, ViewerBlocked, ViewerUnblocked:
		return nil
	default:
		return fmt.Errorf("unsupported persona relationship event %q", event.EventName)
	}
}
