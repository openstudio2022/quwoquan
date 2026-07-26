package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

// ErrOutboxClaimLost means a different relay owns, completed, or removed the
// leased row. It is a normal concurrent-delivery outcome, not a transport
// failure to retry from this worker.
var ErrOutboxClaimLost = errors.New("persona relationship outbox claim lost")

// BlockedListItem 是当前 persona 的私有拉黑列表切片。展示字段来自同域
// Persona named reader 的公开快照；聚合内部 pair/version/direction 不向外暴露。
type BlockedListItem struct {
	TargetSubAccountID string
	DisplayName        string
	UserHandle         string
	AvatarURL          string
	BlockedAt          time.Time
}

// PersonaRelationshipStore owns every durable fact for a persona pair. Follow
// and block are deliberately not separate stores: the aggregate rules require
// a single transaction and a single version sequence.
type PersonaRelationshipStore interface {
	Apply(ctx context.Context, command model.Command) (model.MutationResult, error)
	Get(ctx context.Context, viewerPersonaID, targetPersonaID string) (model.RelationshipState, error)
	ListFollowing(ctx context.Context, sourcePersonaID, cursor string, limit int) ([]model.Direction, string, error)
	ListFollowers(ctx context.Context, targetPersonaID, cursor string, limit int) ([]model.Direction, string, error)
	ListBlocked(ctx context.Context, sourcePersonaID, cursor string, limit int) ([]BlockedListItem, string, error)
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
