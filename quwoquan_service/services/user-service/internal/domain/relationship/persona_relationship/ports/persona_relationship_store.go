package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
)

// ErrOutboxClaimLost means a different relay owns, completed, or removed the
// leased row. It is a normal concurrent-delivery outcome, not a transport
// failure to retry from this worker.
var ErrOutboxClaimLost = errors.New("persona relationship outbox claim lost")

// PersonaRelationshipStore owns every durable fact for a persona pair. Follow
// and block are deliberately not separate stores: the aggregate rules require
// a single transaction and a single version sequence.
type PersonaRelationshipStore interface {
	Apply(ctx context.Context, command model.Command) (model.MutationResult, error)
	Get(ctx context.Context, viewerPersonaID, targetPersonaID string) (model.RelationshipState, error)
	ListFollowing(ctx context.Context, sourcePersonaID, cursor string, limit int) ([]model.Direction, string, error)
	ListFollowers(ctx context.Context, targetPersonaID, cursor string, limit int) ([]model.Direction, string, error)
	ListBlocked(ctx context.Context, sourcePersonaID, cursor string, limit int) ([]model.Direction, string, error)
	CountFollowing(ctx context.Context, sourcePersonaID string) (int64, error)
	CountFollowers(ctx context.Context, targetPersonaID string) (int64, error)
}

// PersonaRelationshipOutbox is read only from the relay worker. Commands
// write it in the same PostgreSQL transaction as the aggregate mutation.
type PersonaRelationshipOutbox interface {
	ClaimPendingOutbox(ctx context.Context, owner string, lease time.Duration, limit int) ([]model.OutboxEvent, error)
	MarkOutboxPublished(ctx context.Context, eventID, owner string) error
	ReleaseOutboxClaim(ctx context.Context, eventID, owner string) error
}

// RelationshipReader is the narrow read port used by greeting and HTTP
// capability composition. It prevents either consumer from reaching storage.
type RelationshipReader interface {
	GetRelationship(ctx context.Context, viewerPersonaID, targetPersonaID string) (model.RelationshipState, error)
}
