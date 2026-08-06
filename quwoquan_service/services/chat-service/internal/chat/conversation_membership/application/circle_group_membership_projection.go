package application

import (
	"context"
	"fmt"
	"strings"
	"time"
)

type CircleGroupMembershipFact struct {
	EventID    string
	EventType  string
	GroupID    string
	CircleID   string
	Version    int64
	UserID     string
	Role       string
	State      string
	OccurredAt time.Time
}

type CircleGroupMembershipProjection interface {
	ProjectCircleGroupMembership(context.Context, CircleGroupMembershipFact) error
}

// CircleGroupMembershipProjectionHandler is the target-owned application
// boundary for CircleGroupMembership source facts. It rejects malformed or
// semantically mismatched events before the durable Chat membership projector
// is invoked.
type CircleGroupMembershipProjectionHandler struct {
	projection CircleGroupMembershipProjection
}

func NewCircleGroupMembershipProjectionHandler(
	projection CircleGroupMembershipProjection,
) *CircleGroupMembershipProjectionHandler {
	return &CircleGroupMembershipProjectionHandler{projection: projection}
}

func (handler *CircleGroupMembershipProjectionHandler) Apply(
	ctx context.Context,
	fact CircleGroupMembershipFact,
) error {
	if handler == nil || handler.projection == nil {
		return fmt.Errorf("CircleGroupMembership projection handler is not configured")
	}
	fact.EventID = strings.TrimSpace(fact.EventID)
	fact.EventType = strings.TrimSpace(fact.EventType)
	fact.GroupID = strings.TrimSpace(fact.GroupID)
	fact.CircleID = strings.TrimSpace(fact.CircleID)
	fact.UserID = strings.TrimSpace(fact.UserID)
	fact.Role = strings.TrimSpace(fact.Role)
	fact.State = strings.TrimSpace(fact.State)
	if fact.EventID == "" || fact.GroupID == "" || fact.CircleID == "" ||
		fact.UserID == "" || fact.Version <= 0 {
		return fmt.Errorf("CircleGroupMembership source fact identity is incomplete")
	}
	switch fact.EventType {
	case "CircleGroupMembershipActivated", "CircleGroupMembershipRoleChanged":
		if fact.Role == "" || fact.State != "active" {
			return fmt.Errorf("%s requires active role and state", fact.EventType)
		}
	case "CircleGroupMembershipLeft":
		if fact.State != "left" {
			return fmt.Errorf("CircleGroupMembershipLeft requires left state")
		}
	case "CircleGroupMembershipRemoved":
		if fact.State != "removed" {
			return fmt.Errorf("CircleGroupMembershipRemoved requires removed state")
		}
	default:
		return fmt.Errorf("unsupported CircleGroupMembership event %q", fact.EventType)
	}
	return handler.projection.ProjectCircleGroupMembership(ctx, fact)
}
