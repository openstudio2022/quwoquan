package application

import (
	"context"

	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
)

type targetContextKey struct{}

// WithTarget carries the evaluated service-pool decision across API Edge
// objects without exposing an inbound adapter as a sibling dependency.
func WithTarget(ctx context.Context, target domain.Target) context.Context {
	return context.WithValue(ctx, targetContextKey{}, target)
}

// TargetFromContext defaults to stable so missing rollout state can never
// create candidate traffic.
func TargetFromContext(ctx context.Context) domain.Target {
	if target, ok := ctx.Value(targetContextKey{}).(domain.Target); ok {
		return target
	}
	return domain.TargetStable
}
