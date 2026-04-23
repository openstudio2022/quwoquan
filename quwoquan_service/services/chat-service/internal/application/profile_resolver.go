package application

import (
	"context"
)

// ProfileSnapshot is display data resolved from the user domain for chat members.
type ProfileSnapshot struct {
	DisplayName   string
	AvatarURL     string
	AvatarAssetID string
	AvatarVersion int
}

// ProfileSnapshotResolver loads display name / avatar for user IDs (batch).
// Implementations must not perform unbounded per-ID fan-out on hot paths.
type ProfileSnapshotResolver interface {
	ResolveMany(ctx context.Context, userIDs []string) (map[string]ProfileSnapshot, error)
}

type noopProfileResolver struct{}

func (noopProfileResolver) ResolveMany(ctx context.Context, userIDs []string) (map[string]ProfileSnapshot, error) {
	_ = ctx
	_ = userIDs
	return map[string]ProfileSnapshot{}, nil
}
