package persistence

import (
	"context"
	"errors"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

const contentReactionActorFenceCollection = "content_reaction_actor_fence_buckets"

type MongoLifecycleCleanupAdapter struct {
	store       *MongoContentReactionStore
	actorFences *mongo.Collection
}

func NewMongoLifecycleCleanupAdapter(store *MongoContentReactionStore) *MongoLifecycleCleanupAdapter {
	if store == nil {
		return nil
	}
	return &MongoLifecycleCleanupAdapter{store: store, actorFences: store.aggregates.Database().Collection(contentReactionActorFenceCollection)}
}

func (adapter *MongoLifecycleCleanupAdapter) EnsureIndexes(ctx context.Context) error {
	if adapter == nil || adapter.store == nil || adapter.actorFences == nil {
		return errors.New("ContentReaction lifecycle cleanup adapter is not configured")
	}
	if err := adapter.store.cleanupJobs.Indexes().DropOne(ctx, "idx_content_reaction_cleanup_source"); err != nil {
		var commandError mongo.CommandError
		if !errors.As(err, &commandError) || commandError.Code != 27 {
			return err
		}
	}
	if _, err := adapter.actorFences.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "actorDimension", Value: 1}, {Key: "actorId", Value: 1}, {Key: "bucket", Value: 1}},
		Options: options.Index().SetName("idx_content_reaction_actor_fence").SetUnique(true),
	}); err != nil {
		return err
	}
	_, err := adapter.store.cleanupJobs.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "scope", Value: 1}, {Key: "source", Value: 1}, {Key: "sourceEventId", Value: 1}, {Key: "sourceVersion", Value: 1}},
		Options: options.Index().SetName("idx_content_reaction_cleanup_authority"),
	})
	return err
}

func (adapter *MongoLifecycleCleanupAdapter) CloseTargetLifecycle(ctx context.Context, target reactiondomain.Target, closeSource string) error {
	if adapter == nil || adapter.store == nil {
		return errors.New("ContentReaction lifecycle cleanup adapter is not configured")
	}
	return adapter.store.CloseTargetLifecycle(ctx, target, closeSource)
}

func (adapter *MongoLifecycleCleanupAdapter) CloseActorLifecycle(ctx context.Context, actor reactiondomain.Actor, closeSource string) error {
	if adapter == nil || adapter.actorFences == nil {
		return errors.New("ContentReaction lifecycle cleanup adapter is not configured")
	}
	if err := actor.Validate(); err != nil {
		return err
	}
	session, err := adapter.actorFences.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		return nil, closeActorLifecycleFences(txCtx, adapter.actorFences, actor, closeSource, time.Now().UTC())
	})
	return err
}

func (adapter *MongoLifecycleCleanupAdapter) Ensure(ctx context.Context, job reactionapp.LifecycleCleanupJob) (reactionapp.LifecycleCleanupJob, error) {
	return adapter.store.Ensure(ctx, job)
}
func (adapter *MongoLifecycleCleanupAdapter) Claim(ctx context.Context, id string, now time.Time, lease time.Duration) (reactionapp.LifecycleCleanupJob, bool, error) {
	return adapter.store.Claim(ctx, id, now, lease)
}
func (adapter *MongoLifecycleCleanupAdapter) Advance(ctx context.Context, id string, epoch int64, cursor string, checkpoint int64, done bool) error {
	return adapter.store.Advance(ctx, id, epoch, cursor, checkpoint, done)
}
func (adapter *MongoLifecycleCleanupAdapter) ListActiveReactionsForCleanup(ctx context.Context, job reactionapp.LifecycleCleanupJob, limit int) ([]reactiondomain.Identity, error) {
	return adapter.store.ListActiveReactionsForCleanup(ctx, job, limit)
}

// Commit serializes active writes against the actor fence without widening the
// aggregate store. The target fence remains in the wrapped store transaction;
// this actor marker is the account/persona lifecycle barrier.
func (adapter *MongoLifecycleCleanupAdapter) MarkActorWriteOpen(ctx context.Context, identity reactiondomain.Identity, now time.Time) error {
	return markActorLifecycleFenceOpen(ctx, adapter.actorFences, identity.Actor, identity.AggregateID(), now)
}

func (adapter *MongoLifecycleCleanupAdapter) ActorLifecycleClosed(ctx context.Context, actor reactiondomain.Actor) (bool, error) {
	if adapter == nil || adapter.actorFences == nil {
		return false, errors.New("ContentReaction lifecycle cleanup adapter is not configured")
	}
	count, err := adapter.actorFences.CountDocuments(ctx, bson.M{"actorDimension": string(actor.Dimension), "actorId": actor.ID, "closed": true}, options.Count().SetLimit(1))
	return count != 0, err
}

var (
	_ reactionapp.LifecycleCleanupJobStore     = (*MongoLifecycleCleanupAdapter)(nil)
	_ reactionapp.LifecycleCleanupMemberReader = (*MongoLifecycleCleanupAdapter)(nil)
	_ reactionapp.TargetLifecycleCloser        = (*MongoLifecycleCleanupAdapter)(nil)
	_ reactionapp.ActorLifecycleCloser         = (*MongoLifecycleCleanupAdapter)(nil)
)
