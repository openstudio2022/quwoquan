package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/accountrestriction"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	jobapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

const (
	notificationAccountRestrictionStateCollection     = "notification_user_account_restrictions"
	notificationAccountRestrictionInboxCollection     = "notification_user_account_restriction_inbox"
	notificationAccountRestrictionWatermarkCollection = "notification_user_account_restriction_watermarks"
)

type notificationAccountRestrictionInboxDocument struct {
	ID             string    `bson:"_id"`
	EventDigest    string    `bson:"eventDigest"`
	AccountDigest  string    `bson:"accountDigest"`
	AccountVersion int64     `bson:"accountVersion"`
	Stale          bool      `bson:"stale"`
	Affected       int64     `bson:"affected"`
	AppliedAt      time.Time `bson:"appliedAt"`
}

type notificationAccountRestrictionWatermarkDocument struct {
	ID             string `bson:"_id"`
	AccountVersion int64  `bson:"accountVersion"`
	EventDigest    string `bson:"eventDigest"`
	Terminal       bool   `bson:"terminal"`
}

type MongoUserAccountRestrictionProjection struct {
	db                *mongo.Database
	states            *mongo.Collection
	inbox             *mongo.Collection
	watermarks        *mongo.Collection
	appMessages       *mongo.Collection
	deliveryLifecycle jobapplication.AccountLifecycle
	now               func() time.Time
}

var _ application.UserAccountRestrictionProjectionStore = (*MongoUserAccountRestrictionProjection)(nil)

func NewMongoUserAccountRestrictionProjection(
	db *mongo.Database,
	deliveryLifecycle jobapplication.AccountLifecycle,
) (*MongoUserAccountRestrictionProjection, error) {
	if db == nil || deliveryLifecycle == nil {
		return nil, errors.New(
			"notification account restriction projection requires MongoDB",
		)
	}
	return &MongoUserAccountRestrictionProjection{
		db:                db,
		states:            db.Collection(notificationAccountRestrictionStateCollection),
		inbox:             db.Collection(notificationAccountRestrictionInboxCollection),
		watermarks:        db.Collection(notificationAccountRestrictionWatermarkCollection),
		appMessages:       db.Collection("app_messages"),
		deliveryLifecycle: deliveryLifecycle,
		now:               time.Now,
	}, nil
}

func (projection *MongoUserAccountRestrictionProjection) EnsureIndexes(
	ctx context.Context,
) error {
	if projection == nil || projection.db == nil {
		return errors.New(
			"notification account restriction projection is not configured",
		)
	}
	if _, err := projection.states.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "subjects", Value: 1}, {Key: "restricted", Value: 1}},
			Options: options.Index().
				SetName("idx_notification_account_restriction_subject_state"),
		},
		{
			Keys: bson.D{{Key: "accountVersion", Value: -1}},
			Options: options.Index().
				SetName("idx_notification_account_restriction_version"),
		},
	}); err != nil {
		return fmt.Errorf("ensure notification account restriction state indexes: %w", err)
	}
	if _, err := projection.inbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "accountDigest", Value: 1},
				{Key: "accountVersion", Value: 1},
			},
			Options: options.Index().
				SetName("uq_notification_account_restriction_account_version").
				SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "appliedAt", Value: -1}},
			Options: options.Index().
				SetName("idx_notification_account_restriction_applied"),
		},
	}); err != nil {
		return fmt.Errorf("ensure notification account restriction inbox indexes: %w", err)
	}
	if _, err := projection.watermarks.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "terminal", Value: 1}, {Key: "accountVersion", Value: -1}},
		Options: options.Index().
			SetName("idx_notification_account_restriction_terminal_version"),
	}); err != nil {
		return fmt.Errorf("ensure notification account restriction watermark index: %w", err)
	}
	return nil
}

func (projection *MongoUserAccountRestrictionProjection) Apply(
	ctx context.Context,
	event accountrestriction.Event,
) (application.UserAccountRestrictionProjectionResult, error) {
	if projection == nil || projection.db == nil {
		return application.UserAccountRestrictionProjectionResult{}, errors.New(
			"notification account restriction projection is not configured",
		)
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountRestrictionProjectionResult{}, err
	}
	if replay, found, err := projection.loadInbox(ctx, event); err != nil {
		return application.UserAccountRestrictionProjectionResult{}, err
	} else if found {
		return replay, nil
	}

	session, err := projection.db.Client().StartSession()
	if err != nil {
		return application.UserAccountRestrictionProjectionResult{}, fmt.Errorf(
			"start notification account restriction transaction: %w",
			err,
		)
	}
	defer session.EndSession(ctx)
	result := application.UserAccountRestrictionProjectionResult{}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replay, found, loadErr := projection.loadInbox(txCtx, event); loadErr != nil {
			return nil, loadErr
		} else if found {
			result = replay
			return nil, nil
		}
		watermark, found, loadErr := projection.loadWatermark(txCtx, event.AccountID)
		if loadErr != nil {
			return nil, loadErr
		}
		if found && watermark.Terminal {
			result = application.UserAccountRestrictionProjectionResult{
				Replayed: true,
				Stale:    true,
				Terminal: true,
			}
			return nil, nil
		}
		if found && watermark.AccountVersion == event.AccountVersion {
			if watermark.EventDigest == event.Digest() {
				result.Replayed = true
				return nil, nil
			}
			return nil, application.ErrUserAccountRestrictionProjectionConflict
		}
		if found && watermark.AccountVersion > event.AccountVersion {
			result = application.UserAccountRestrictionProjectionResult{
				Replayed: true,
				Stale:    true,
			}
			return nil, projection.insertInbox(txCtx, event, result)
		}

		affected, mutationErr := projection.applyOwnedMutations(txCtx, event)
		if mutationErr != nil {
			return nil, mutationErr
		}
		result.Affected = affected
		now := projection.now().UTC()
		accountDigest := notificationAccountRestrictionDigest(event.AccountID)
		if _, updateErr := projection.states.UpdateOne(
			txCtx,
			bson.M{"_id": accountDigest},
			bson.M{"$set": bson.M{
				"subjects":       event.SubjectIDs(),
				"restricted":     event.Restricted(),
				"accountVersion": event.AccountVersion,
				"authEpoch":      event.AuthEpoch,
				"eventId":        event.EventID,
				"eventDigest":    event.Digest(),
				"decisionRef":    event.DecisionRef,
				"occurredAt":     event.OccurredAt.UTC(),
				"updatedAt":      now,
			}},
			options.UpdateOne().SetUpsert(true),
		); updateErr != nil {
			return nil, fmt.Errorf(
				"persist notification account restriction state: %w",
				updateErr,
			)
		}
		if _, updateErr := projection.watermarks.UpdateOne(
			txCtx,
			bson.M{"_id": accountDigest},
			bson.M{
				"$set": bson.M{
					"accountVersion": event.AccountVersion,
					"eventDigest":    event.Digest(),
					"terminal":       false,
					"updatedAt":      now,
				},
				"$setOnInsert": bson.M{"createdAt": now},
			},
			options.UpdateOne().SetUpsert(true),
		); updateErr != nil {
			return nil, fmt.Errorf(
				"persist notification account restriction watermark: %w",
				updateErr,
			)
		}
		return nil, projection.insertInbox(txCtx, event, result)
	})
	if err == nil {
		return result, nil
	}
	if mongo.IsDuplicateKeyError(err) {
		if replay, found, loadErr := projection.loadInbox(ctx, event); loadErr == nil && found {
			return replay, nil
		} else if loadErr != nil {
			return application.UserAccountRestrictionProjectionResult{}, loadErr
		}
		return application.UserAccountRestrictionProjectionResult{},
			application.ErrUserAccountRestrictionProjectionConflict
	}
	if errors.Is(err, application.ErrUserAccountRestrictionProjectionConflict) {
		return application.UserAccountRestrictionProjectionResult{}, err
	}
	return application.UserAccountRestrictionProjectionResult{}, fmt.Errorf(
		"apply notification account restriction projection: %w",
		err,
	)
}

func (projection *MongoUserAccountRestrictionProjection) RestrictedSubjects(
	ctx context.Context,
	subjects []string,
) (map[string]bool, error) {
	subjects = accountrestriction.NormalizeSubjects(subjects)
	result := make(map[string]bool, len(subjects))
	if len(subjects) == 0 {
		return result, nil
	}
	if projection == nil || projection.states == nil {
		return nil, errors.New(
			"notification account restriction projection is not configured",
		)
	}
	cursor, err := projection.states.Find(
		ctx,
		bson.M{"restricted": true, "subjects": bson.M{"$in": subjects}},
		options.Find().SetProjection(bson.M{"subjects": 1}),
	)
	if err != nil {
		return nil, fmt.Errorf("read notification account restrictions: %w", err)
	}
	defer cursor.Close(ctx)
	wanted := make(map[string]struct{}, len(subjects))
	for _, subject := range subjects {
		wanted[subject] = struct{}{}
	}
	for cursor.Next(ctx) {
		var document struct {
			Subjects []string `bson:"subjects"`
		}
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode notification account restriction: %w", err)
		}
		for _, subject := range document.Subjects {
			if _, exists := wanted[subject]; exists {
				result[subject] = true
			}
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate notification account restrictions: %w", err)
	}
	return result, nil
}

func (projection *MongoUserAccountRestrictionProjection) applyOwnedMutations(
	ctx context.Context,
	event accountrestriction.Event,
) (int64, error) {
	baseSet := bson.M{
		"accountRestricted":           event.Restricted(),
		"accountRestrictionVersion":   event.AccountVersion,
		"accountRestrictionUpdatedAt": event.OccurredAt.UTC(),
	}
	messageResult, err := projection.appMessages.UpdateMany(
		ctx,
		bson.M{"$or": bson.A{
			bson.M{"userId": bson.M{"$in": event.SubjectIDs()}},
			bson.M{"destination.id": bson.M{"$in": event.SubjectIDs()}},
		}},
		bson.M{"$set": baseSet},
	)
	if err != nil {
		return 0, fmt.Errorf("project notification restriction to app messages: %w", err)
	}
	deliveryAffected, err := projection.deliveryLifecycle.ApplyRestriction(ctx, event)
	if err != nil {
		return 0, err
	}
	return messageResult.ModifiedCount + deliveryAffected, nil
}

func (projection *MongoUserAccountRestrictionProjection) loadWatermark(
	ctx context.Context,
	accountID string,
) (notificationAccountRestrictionWatermarkDocument, bool, error) {
	var document notificationAccountRestrictionWatermarkDocument
	err := projection.watermarks.FindOne(
		ctx,
		bson.M{"_id": notificationAccountRestrictionDigest(accountID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return notificationAccountRestrictionWatermarkDocument{}, false, nil
	}
	if err != nil {
		return notificationAccountRestrictionWatermarkDocument{}, false,
			fmt.Errorf("load notification account restriction watermark: %w", err)
	}
	return document, true, nil
}

func (projection *MongoUserAccountRestrictionProjection) loadInbox(
	ctx context.Context,
	event accountrestriction.Event,
) (application.UserAccountRestrictionProjectionResult, bool, error) {
	var document notificationAccountRestrictionInboxDocument
	err := projection.inbox.FindOne(ctx, bson.M{"_id": event.EventID}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return application.UserAccountRestrictionProjectionResult{}, false, nil
	}
	if err != nil {
		return application.UserAccountRestrictionProjectionResult{}, false,
			fmt.Errorf("load notification account restriction inbox: %w", err)
	}
	if document.EventDigest != event.Digest() ||
		document.AccountDigest != notificationAccountRestrictionDigest(event.AccountID) ||
		document.AccountVersion != event.AccountVersion {
		return application.UserAccountRestrictionProjectionResult{}, false,
			application.ErrUserAccountRestrictionProjectionConflict
	}
	return application.UserAccountRestrictionProjectionResult{
		Replayed: true,
		Stale:    document.Stale,
		Affected: document.Affected,
	}, true, nil
}

func (projection *MongoUserAccountRestrictionProjection) insertInbox(
	ctx context.Context,
	event accountrestriction.Event,
	result application.UserAccountRestrictionProjectionResult,
) error {
	_, err := projection.inbox.InsertOne(ctx, notificationAccountRestrictionInboxDocument{
		ID:             event.EventID,
		EventDigest:    event.Digest(),
		AccountDigest:  notificationAccountRestrictionDigest(event.AccountID),
		AccountVersion: event.AccountVersion,
		Stale:          result.Stale,
		Affected:       result.Affected,
		AppliedAt:      projection.now().UTC(),
	})
	if err != nil {
		return fmt.Errorf("append notification account restriction inbox: %w", err)
	}
	return nil
}

func finalizeNotificationAccountRestrictionClosure(
	ctx context.Context,
	db *mongo.Database,
	event application.UserAccountClosedEvent,
) error {
	if db == nil {
		return errors.New("notification account restriction closure requires MongoDB")
	}
	now := time.Now().UTC()
	accountDigest := notificationAccountRestrictionDigest(event.UserID)
	if _, err := db.Collection(notificationAccountRestrictionWatermarkCollection).UpdateOne(
		ctx,
		bson.M{"_id": accountDigest},
		bson.M{
			"$max": bson.M{
				"accountVersion": event.AccountVersion,
				"closedAt":       event.UpdatedAt.UTC(),
			},
			"$set": bson.M{
				"eventDigest": event.Digest(),
				"terminal":    true,
				"updatedAt":   now,
			},
			"$setOnInsert": bson.M{"createdAt": now},
		},
		options.UpdateOne().SetUpsert(true),
	); err != nil {
		return fmt.Errorf(
			"persist notification account restriction terminal watermark: %w",
			err,
		)
	}
	accountID := strings.TrimSpace(event.UserID)
	if _, err := db.Collection(notificationAccountRestrictionStateCollection).DeleteMany(
		ctx,
		bson.M{"_id": bson.M{"$in": bson.A{accountDigest, accountID}}},
	); err != nil {
		return fmt.Errorf("delete notification account restriction identity state: %w", err)
	}
	if _, err := db.Collection(notificationAccountRestrictionInboxCollection).DeleteMany(
		ctx,
		bson.M{"$or": bson.A{
			bson.M{"accountDigest": accountDigest},
			bson.M{"accountId": accountID},
		}},
	); err != nil {
		return fmt.Errorf("delete notification account restriction inbox: %w", err)
	}
	return nil
}

func notificationAccountRestrictionDigest(accountID string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(accountID)))
	return hex.EncodeToString(digest[:])
}
