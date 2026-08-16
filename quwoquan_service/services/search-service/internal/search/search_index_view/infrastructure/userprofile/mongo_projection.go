package userprofile

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

const (
	userProfileInboxCollection     = "search_user_profile_projection_inbox"
	userProfileWatermarkCollection = "search_user_profile_projection_watermarks"
)

type projectionWriter interface {
	Apply(context.Context, es.ChangeEvent) error
}

type inboxDocument struct {
	ID             string    `bson:"_id"`
	EventID        string    `bson:"eventId"`
	ProjectionHash string    `bson:"projectionHash"`
	UserID         string    `bson:"userId"`
	ProfileVersion int64     `bson:"profileVersion"`
	Stale          bool      `bson:"stale"`
	Deleted        bool      `bson:"deleted"`
	AppliedAt      time.Time `bson:"appliedAt"`
}

type watermarkDocument struct {
	ID             string `bson:"_id"`
	UserID         string `bson:"userId"`
	ProfileVersion int64  `bson:"profileVersion"`
	ProjectionHash string `bson:"projectionHash"`
	Deleted        bool   `bson:"deleted"`
}

type MongoUserProfileSearchProjection struct {
	db         *mongo.Database
	inbox      *mongo.Collection
	watermarks *mongo.Collection
	writer     projectionWriter
	now        func() time.Time
}

var _ application.UserProfileSearchProjection = (*MongoUserProfileSearchProjection)(nil)

func NewMongoUserProfileSearchProjection(
	db *mongo.Database,
	writer projectionWriter,
) (*MongoUserProfileSearchProjection, error) {
	if db == nil || writer == nil {
		return nil, errors.New("Search UserProfile projection requires MongoDB and provider writer")
	}
	return &MongoUserProfileSearchProjection{
		db: db, inbox: db.Collection(userProfileInboxCollection),
		watermarks: db.Collection(userProfileWatermarkCollection),
		writer:     writer, now: time.Now,
	}, nil
}

func (projection *MongoUserProfileSearchProjection) EnsureIndexes(ctx context.Context) error {
	if projection == nil || projection.db == nil {
		return errors.New("Search UserProfile projection is not configured")
	}
	if _, err := projection.inbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "eventId", Value: 1}}, Options: options.Index().SetName("uq_search_user_profile_projection_event").SetUnique(true)},
		{Keys: bson.D{{Key: "appliedAt", Value: -1}}, Options: options.Index().SetName("idx_search_user_profile_projection_applied")},
	}); err != nil {
		return fmt.Errorf("ensure Search UserProfile inbox indexes: %w", err)
	}
	if _, err := projection.watermarks.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "userId", Value: 1}}, Options: options.Index().SetName("uq_search_user_profile_projection_user").SetUnique(true)},
		{Keys: bson.D{{Key: "profileVersion", Value: -1}}, Options: options.Index().SetName("idx_search_user_profile_projection_version")},
	}); err != nil {
		return fmt.Errorf("ensure Search UserProfile watermark indexes: %w", err)
	}
	return nil
}

func (projection *MongoUserProfileSearchProjection) Apply(
	ctx context.Context,
	event application.UserProfileSearchProjectionEvent,
) (application.UserProfileSearchProjectionResult, error) {
	if projection == nil || projection.db == nil || projection.writer == nil {
		return application.UserProfileSearchProjectionResult{}, errors.New(
			"Search UserProfile projection is not configured",
		)
	}
	if err := event.Validate(); err != nil {
		return application.UserProfileSearchProjectionResult{}, err
	}
	if replay, found, err := projection.loadInbox(ctx, event); err != nil {
		return application.UserProfileSearchProjectionResult{}, err
	} else if found {
		return replay, nil
	}
	watermark, found, err := projection.loadWatermark(ctx, event.UserID)
	if err != nil {
		return application.UserProfileSearchProjectionResult{}, err
	}
	if found && watermark.ProfileVersion > event.ProfileVersion {
		return projection.commitCheckpoint(ctx, event, true, false)
	}
	if found && watermark.ProfileVersion == event.ProfileVersion {
		if watermark.ProjectionHash != event.Digest() {
			return application.UserProfileSearchProjectionResult{},
				application.ErrUserProfileSearchProjectionConflict
		}
		if err := projection.applyProviderProjection(ctx, event); err != nil {
			return application.UserProfileSearchProjectionResult{}, err
		}
		return projection.commitCheckpoint(ctx, event, false, true)
	}

	if err := projection.applyProviderProjection(ctx, event); err != nil {
		return application.UserProfileSearchProjectionResult{}, err
	}
	return projection.commitCheckpoint(ctx, event, false, false)
}

func (projection *MongoUserProfileSearchProjection) applyProviderProjection(
	ctx context.Context,
	event application.UserProfileSearchProjectionEvent,
) error {
	if err := projection.writer.Apply(ctx, BuildProviderChangeEvent(event)); err != nil {
		// The Search checkpoint is deliberately not advanced. Provider upserts and
		// deletes use a stable object ID, so the pending stream event can replay.
		return fmt.Errorf(
			"write Search UserProfile provider projection: %w", err,
		)
	}
	return nil
}

// BuildProviderChangeEvent translates one durable UserProfile projection event
// into the provider-owned Search document mutation. The search-service internal
// boundary exports the pure translation so canonical local contracts can verify
// replay identity without reaching into a concrete Mongo projection instance.
func BuildProviderChangeEvent(
	event application.UserProfileSearchProjectionEvent,
) es.ChangeEvent {
	op := es.OpUpsert
	if event.Operation == "delete" {
		op = es.OpDelete
	}
	return es.ChangeEvent{Op: op, Doc: event.Document()}
}

func (projection *MongoUserProfileSearchProjection) commitCheckpoint(
	ctx context.Context,
	event application.UserProfileSearchProjectionEvent,
	knownStale bool,
	knownReplay bool,
) (application.UserProfileSearchProjectionResult, error) {
	session, err := projection.db.Client().StartSession()
	if err != nil {
		return application.UserProfileSearchProjectionResult{}, fmt.Errorf(
			"start Search UserProfile checkpoint transaction: %w", err,
		)
	}
	defer session.EndSession(ctx)
	result := application.UserProfileSearchProjectionResult{
		Stale: knownStale, Replayed: knownReplay,
		Deleted: event.Operation == "delete",
	}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, loadErr := projection.loadInbox(txCtx, event); loadErr != nil {
			return nil, loadErr
		} else if found {
			result = replay
			return nil, nil
		}
		watermark, found, loadErr := projection.loadWatermark(txCtx, event.UserID)
		if loadErr != nil {
			return nil, loadErr
		}
		if found && watermark.ProfileVersion > event.ProfileVersion {
			result.Stale = true
			result.Replayed = true
			return nil, projection.insertInbox(txCtx, event, result)
		}
		if found && watermark.ProfileVersion == event.ProfileVersion {
			if watermark.ProjectionHash != event.Digest() {
				return nil, application.ErrUserProfileSearchProjectionConflict
			}
			result.Replayed = true
			return nil, projection.insertInbox(txCtx, event, result)
		}
		if knownStale || knownReplay {
			return nil, errors.New("Search UserProfile checkpoint changed before commit")
		}
		now := projection.now().UTC()
		if _, updateErr := projection.watermarks.UpdateOne(
			txCtx,
			bson.M{"_id": event.UserID},
			bson.M{"$set": bson.M{
				"userId": event.UserID, "profileVersion": event.ProfileVersion,
				"projectionHash": event.Digest(), "deleted": result.Deleted,
				"eventId": event.EventID, "updatedAt": now,
			}, "$setOnInsert": bson.M{"createdAt": now}},
			options.UpdateOne().SetUpsert(true),
		); updateErr != nil {
			return nil, fmt.Errorf("persist Search UserProfile watermark: %w", updateErr)
		}
		return nil, projection.insertInbox(txCtx, event, result)
	})
	if err == nil {
		return result, nil
	}
	if mongo.IsDuplicateKeyError(err) {
		if replay, found, loadErr := projection.loadInbox(ctx, event); loadErr == nil && found {
			return replay, nil
		}
		return application.UserProfileSearchProjectionResult{},
			application.ErrUserProfileSearchProjectionConflict
	}
	return application.UserProfileSearchProjectionResult{}, err
}

func (projection *MongoUserProfileSearchProjection) loadInbox(
	ctx context.Context,
	event application.UserProfileSearchProjectionEvent,
) (application.UserProfileSearchProjectionResult, bool, error) {
	var document inboxDocument
	err := projection.inbox.FindOne(ctx, bson.M{"_id": event.EventID}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return application.UserProfileSearchProjectionResult{}, false, nil
	}
	if err != nil {
		return application.UserProfileSearchProjectionResult{}, false,
			fmt.Errorf("load Search UserProfile inbox: %w", err)
	}
	if document.ProjectionHash != event.Digest() ||
		document.UserID != event.UserID || document.ProfileVersion != event.ProfileVersion {
		return application.UserProfileSearchProjectionResult{}, false,
			application.ErrUserProfileSearchProjectionConflict
	}
	return application.UserProfileSearchProjectionResult{
		Replayed: true, Stale: document.Stale, Deleted: document.Deleted,
	}, true, nil
}

func (projection *MongoUserProfileSearchProjection) loadWatermark(
	ctx context.Context,
	userID string,
) (watermarkDocument, bool, error) {
	var document watermarkDocument
	err := projection.watermarks.FindOne(ctx, bson.M{"_id": userID}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return watermarkDocument{}, false, nil
	}
	if err != nil {
		return watermarkDocument{}, false,
			fmt.Errorf("load Search UserProfile watermark: %w", err)
	}
	return document, true, nil
}

func (projection *MongoUserProfileSearchProjection) insertInbox(
	ctx context.Context,
	event application.UserProfileSearchProjectionEvent,
	result application.UserProfileSearchProjectionResult,
) error {
	_, err := projection.inbox.InsertOne(ctx, inboxDocument{
		ID: event.EventID, EventID: event.EventID,
		ProjectionHash: event.Digest(), UserID: event.UserID,
		ProfileVersion: event.ProfileVersion, Stale: result.Stale,
		Deleted: result.Deleted, AppliedAt: projection.now().UTC(),
	})
	if err != nil {
		return fmt.Errorf("persist Search UserProfile inbox: %w", err)
	}
	return nil
}
