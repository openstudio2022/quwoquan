package ports

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// PersonaProfileProjector materializes the active Persona's public profile into
// UserAccount's read projection. Project is idempotent for one Persona outbox
// coordinate; ProjectNext and Run provide durable recovery after process or
// dependency failures.
type PersonaProfileProjector interface {
	Project(
		ctx context.Context,
		personaID string,
		aggregateVersion int64,
	) (*model.UserProfile, error)
	ProjectNext(ctx context.Context) (bool, error)
	Run(ctx context.Context, interval time.Duration) error
}
