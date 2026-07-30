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
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
)

const (
	circleAccountRestrictionStateCollection     = "circle_user_account_restrictions"
	circleAccountRestrictionInboxCollection     = "circle_user_account_restriction_inbox"
	circleAccountRestrictionWatermarkCollection = "circle_user_account_restriction_watermarks"
)

type circleAccountRestrictionInboxDocument struct {
	ID             string    `bson:"_id"`
	EventDigest    string    `bson:"eventDigest"`
	AccountDigest  string    `bson:"accountDigest"`
	AccountVersion int64     `bson:"accountVersion"`
	Stale          bool      `bson:"stale"`
	Affected       int64     `bson:"affected"`
	AppliedAt      time.Time `bson:"appliedAt"`
}

type circleAccountRestrictionWatermarkDocument struct {
	ID             string `bson:"_id"`
	AccountVersion int64  `bson:"accountVersion"`
	EventDigest    string `bson:"eventDigest"`
	Terminal       bool   `bson:"terminal"`
}

type MongoUserAccountRestrictionProjection struct {
	db               *mongo.Database
	states           *mongo.Collection
	inbox            *mongo.Collection
	watermarks       *mongo.Collection
	memberships      *mongo.Collection
	groupMemberships *mongo.Collection
	posts            *mongo.Collection
	placements       *mongo.Collection
	now              func() time.Time
}

var _ application.UserAccountRestrictionProjection = (*MongoUserAccountRestrictionProjection)(nil)

func NewMongoUserAccountRestrictionProjection(
	db *mongo.Database,
) (*MongoUserAccountRestrictionProjection, error) {
	if db == nil {
		return nil, errors.New(
			"circle account restriction projection requires MongoDB",
		)
	}
	return &MongoUserAccountRestrictionProjection{
		db:               db,
		states:           db.Collection(circleAccountRestrictionStateCollection),
		inbox:            db.Collection(circleAccountRestrictionInboxCollection),
		watermarks:       db.Collection(circleAccountRestrictionWatermarkCollection),
		memberships:      db.Collection("circle_memberships"),
		groupMemberships: db.Collection("circle_group_memberships"),
		posts:            db.Collection("posts"),
		placements:       db.Collection("circle_post_placements"),
		now:              time.Now,
	}, nil
}

func (projection *MongoUserAccountRestrictionProjection) EnsureIndexes(
	ctx context.Context,
) error {
	if projection == nil || projection.db == nil {
		return errors.New("circle account restriction projection is not configured")
	}
	if _, err := projection.states.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "subjects", Value: 1}, {Key: "restricted", Value: 1}},
			Options: options.Index().
				SetName("idx_circle_account_restriction_subject_state"),
		},
		{
			Keys: bson.D{{Key: "accountVersion", Value: -1}},
			Options: options.Index().
				SetName("idx_circle_account_restriction_version"),
		},
	}); err != nil {
		return fmt.Errorf("ensure circle account restriction state indexes: %w", err)
	}
	if _, err := projection.inbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "accountDigest", Value: 1},
				{Key: "accountVersion", Value: 1},
			},
			Options: options.Index().
				SetName("uq_circle_account_restriction_account_version").
				SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "appliedAt", Value: -1}},
			Options: options.Index().
				SetName("idx_circle_account_restriction_applied"),
		},
	}); err != nil {
		return fmt.Errorf("ensure circle account restriction inbox indexes: %w", err)
	}
	if _, err := projection.watermarks.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "terminal", Value: 1}, {Key: "accountVersion", Value: -1}},
		Options: options.Index().
			SetName("idx_circle_account_restriction_terminal_version"),
	}); err != nil {
		return fmt.Errorf("ensure circle account restriction watermark index: %w", err)
	}
	return nil
}

func (projection *MongoUserAccountRestrictionProjection) Apply(
	ctx context.Context,
	event accountrestriction.Event,
) (application.UserAccountRestrictionProjectionResult, error) {
	if projection == nil || projection.db == nil {
		return application.UserAccountRestrictionProjectionResult{}, errors.New(
			"circle account restriction projection is not configured",
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
			"start circle account restriction transaction: %w",
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
		accountDigest := circleAccountRestrictionDigest(event.AccountID)
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
			return nil, fmt.Errorf("persist circle account restriction state: %w", updateErr)
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
			return nil, fmt.Errorf("persist circle account restriction watermark: %w", updateErr)
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
		"apply circle account restriction projection: %w",
		err,
	)
}

func (projection *MongoUserAccountRestrictionProjection) applyOwnedMutations(
	ctx context.Context,
	event accountrestriction.Event,
) (int64, error) {
	update := bson.M{"$set": bson.M{
		"accountRestricted":           event.Restricted(),
		"accountRestrictionVersion":   event.AccountVersion,
		"accountRestrictionUpdatedAt": event.OccurredAt.UTC(),
	}}
	targets := []struct {
		name       string
		collection *mongo.Collection
		field      string
	}{
		{"circle membership", projection.memberships, "personaId"},
		{"circle group membership", projection.groupMemberships, "personaId"},
		{"circle post", projection.posts, "authorId"},
		{"circle post placement", projection.placements, "authorId"},
	}
	var affected int64
	for _, target := range targets {
		result, err := target.collection.UpdateMany(
			ctx,
			bson.M{target.field: bson.M{"$in": event.SubjectIDs()}},
			update,
		)
		if err != nil {
			return 0, fmt.Errorf("project restriction to %s: %w", target.name, err)
		}
		affected += result.ModifiedCount
	}
	return affected, nil
}

func (projection *MongoUserAccountRestrictionProjection) loadWatermark(
	ctx context.Context,
	accountID string,
) (circleAccountRestrictionWatermarkDocument, bool, error) {
	var document circleAccountRestrictionWatermarkDocument
	err := projection.watermarks.FindOne(
		ctx,
		bson.M{"_id": circleAccountRestrictionDigest(accountID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return circleAccountRestrictionWatermarkDocument{}, false, nil
	}
	if err != nil {
		return circleAccountRestrictionWatermarkDocument{}, false,
			fmt.Errorf("load circle account restriction watermark: %w", err)
	}
	return document, true, nil
}

func (projection *MongoUserAccountRestrictionProjection) loadInbox(
	ctx context.Context,
	event accountrestriction.Event,
) (application.UserAccountRestrictionProjectionResult, bool, error) {
	var document circleAccountRestrictionInboxDocument
	err := projection.inbox.FindOne(ctx, bson.M{"_id": event.EventID}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return application.UserAccountRestrictionProjectionResult{}, false, nil
	}
	if err != nil {
		return application.UserAccountRestrictionProjectionResult{}, false,
			fmt.Errorf("load circle account restriction inbox: %w", err)
	}
	if document.EventDigest != event.Digest() ||
		document.AccountDigest != circleAccountRestrictionDigest(event.AccountID) ||
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
	_, err := projection.inbox.InsertOne(ctx, circleAccountRestrictionInboxDocument{
		ID:             event.EventID,
		EventDigest:    event.Digest(),
		AccountDigest:  circleAccountRestrictionDigest(event.AccountID),
		AccountVersion: event.AccountVersion,
		Stale:          result.Stale,
		Affected:       result.Affected,
		AppliedAt:      projection.now().UTC(),
	})
	if err != nil {
		return fmt.Errorf("append circle account restriction inbox: %w", err)
	}
	return nil
}

func finalizeCircleAccountRestrictionClosure(
	ctx context.Context,
	db *mongo.Database,
	event application.UserAccountClosedEvent,
) error {
	if db == nil {
		return errors.New("circle account restriction closure requires MongoDB")
	}
	now := time.Now().UTC()
	accountDigest := circleAccountRestrictionDigest(event.AccountID)
	if _, err := db.Collection(circleAccountRestrictionWatermarkCollection).UpdateOne(
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
		return fmt.Errorf("persist circle account restriction terminal watermark: %w", err)
	}
	accountID := strings.TrimSpace(event.AccountID)
	if _, err := db.Collection(circleAccountRestrictionStateCollection).DeleteMany(
		ctx,
		bson.M{"_id": bson.M{"$in": bson.A{accountDigest, accountID}}},
	); err != nil {
		return fmt.Errorf("delete circle account restriction identity state: %w", err)
	}
	if _, err := db.Collection(circleAccountRestrictionInboxCollection).DeleteMany(
		ctx,
		bson.M{"$or": bson.A{
			bson.M{"accountDigest": accountDigest},
			bson.M{"accountId": accountID},
		}},
	); err != nil {
		return fmt.Errorf("delete circle account restriction inbox: %w", err)
	}
	return nil
}

func circleAccountRestrictionDigest(accountID string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(accountID)))
	return hex.EncodeToString(digest[:])
}
