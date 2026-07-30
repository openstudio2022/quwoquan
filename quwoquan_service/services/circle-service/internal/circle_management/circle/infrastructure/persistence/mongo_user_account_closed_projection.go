package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
)

const (
	circleAccountClosedInboxCollection   = "circle_user_account_closed_inbox"
	circleAccountClosedFailureCollection = "circle_user_account_closed_failures"
	circleClosedSubjectCollection        = "circle_closed_account_subjects"

	circleAccountClosedFailureRetention = 30 * 24 * time.Hour
	closedAccountDisplayName            = "已注销用户"
	closedAccountAnonymousPrefix        = "closed_"
)

type circleAccountClosedInboxDocument struct {
	ID                string     `bson:"_id"`
	EventDigest       string     `bson:"eventDigest"`
	AccountDigest     string     `bson:"accountDigest"`
	AccountVersion    int64      `bson:"accountVersion"`
	AffectedCircleIDs []string   `bson:"affectedCircleIds"`
	AppliedAt         time.Time  `bson:"appliedAt"`
	CacheCompletedAt  *time.Time `bson:"cacheCompletedAt,omitempty"`
}

type MongoUserAccountClosedProjection struct {
	db               *mongo.Database
	redis            rtredis.Client
	inbox            *mongo.Collection
	failures         *mongo.Collection
	closedSubjects   *mongo.Collection
	restrictions     *mongo.Collection
	restrictionInbox *mongo.Collection
	now              func() time.Time
}

var _ application.UserAccountClosedProjection = (*MongoUserAccountClosedProjection)(nil)

func NewMongoUserAccountClosedProjection(
	db *mongo.Database,
	redis rtredis.Client,
) *MongoUserAccountClosedProjection {
	if db == nil || redis == nil {
		panic(
			"circle UserAccountClosed projection requires MongoDB and redis.general",
		)
	}
	return &MongoUserAccountClosedProjection{
		db:               db,
		redis:            redis,
		inbox:            db.Collection(circleAccountClosedInboxCollection),
		failures:         db.Collection(circleAccountClosedFailureCollection),
		closedSubjects:   db.Collection(circleClosedSubjectCollection),
		restrictions:     db.Collection("circle_user_account_restrictions"),
		restrictionInbox: db.Collection("circle_user_account_restriction_inbox"),
		now:              time.Now,
	}
}

func (projection *MongoUserAccountClosedProjection) EnsureIndexes(
	ctx context.Context,
) error {
	if projection == nil || projection.db == nil || projection.redis == nil {
		return errors.New(
			"circle UserAccountClosed projection is not configured",
		)
	}
	if _, err := projection.inbox.Indexes().CreateMany(
		ctx,
		[]mongo.IndexModel{
			{
				Keys: bson.D{
					{Key: "accountDigest", Value: 1},
					{Key: "accountVersion", Value: 1},
				},
				Options: options.Index().
					SetName("uq_circle_account_closed_account_version").
					SetUnique(true),
			},
			{
				Keys: bson.D{{Key: "appliedAt", Value: -1}},
				Options: options.Index().
					SetName("idx_circle_account_closed_applied"),
			},
		},
	); err != nil {
		return fmt.Errorf(
			"ensure circle UserAccountClosed inbox indexes: %w",
			err,
		)
	}
	if _, err := projection.failures.Indexes().CreateMany(
		ctx,
		[]mongo.IndexModel{
			{
				Keys: bson.D{{Key: "eventDigest", Value: 1}},
				Options: options.Index().
					SetName("idx_circle_account_closed_failure_event"),
			},
			{
				Keys: bson.D{{Key: "expiresAt", Value: 1}},
				Options: options.Index().
					SetName("ttl_circle_account_closed_failure").
					SetExpireAfterSeconds(0),
			},
		},
	); err != nil {
		return fmt.Errorf(
			"ensure circle UserAccountClosed failure indexes: %w",
			err,
		)
	}
	if _, err := projection.closedSubjects.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "eventDigest", Value: 1}},
			Options: options.Index().
				SetName("idx_circle_closed_subject_event"),
		},
	); err != nil {
		return fmt.Errorf(
			"ensure circle closed-subject indexes: %w",
			err,
		)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) ApplyUserAccountClosed(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedApplyResult, error) {
	if projection == nil || projection.db == nil || projection.redis == nil {
		return application.UserAccountClosedApplyResult{}, errors.New(
			"circle UserAccountClosed projection is not configured",
		)
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedApplyResult{}, err
	}
	inbox, found, err := projection.loadInboxByEventID(ctx, event)
	if err != nil {
		return application.UserAccountClosedApplyResult{}, err
	}
	if found {
		if err := projection.completeCacheInvalidation(
			ctx,
			event,
			inbox,
		); err != nil {
			return application.UserAccountClosedApplyResult{}, err
		}
		return application.UserAccountClosedApplyResult{Replayed: true}, nil
	}
	if _, found, err := projection.loadInboxByAccountVersion(
		ctx,
		event,
	); err != nil {
		return application.UserAccountClosedApplyResult{}, err
	} else if found {
		return application.UserAccountClosedApplyResult{},
			application.ErrUserAccountClosedEventConflict
	}

	session, err := projection.db.Client().StartSession()
	if err != nil {
		return application.UserAccountClosedApplyResult{},
			fmt.Errorf("start circle UserAccountClosed transaction: %w", err)
	}
	defer session.EndSession(ctx)

	var applied circleAccountClosedInboxDocument
	_, err = session.WithTransaction(
		ctx,
		func(txCtx context.Context) (any, error) {
			if existing, txFound, findErr := projection.loadInboxByEventID(
				txCtx,
				event,
			); findErr != nil {
				return nil, findErr
			} else if txFound {
				applied = existing
				return nil, nil
			}
			if _, conflict, findErr := projection.loadInboxByAccountVersion(
				txCtx,
				event,
			); findErr != nil {
				return nil, findErr
			} else if conflict {
				return nil, application.ErrUserAccountClosedEventConflict
			}
			if err := finalizeCircleAccountRestrictionClosure(
				txCtx,
				projection.db,
				event,
			); err != nil {
				return nil, err
			}
			if err := projection.persistClosedSubjects(
				txCtx,
				event,
			); err != nil {
				return nil, err
			}
			summary, cleanupErr := projection.applyAccountClosureCleanup(
				txCtx,
				event,
			)
			if cleanupErr != nil {
				return nil, cleanupErr
			}
			if cleanupErr := projection.deleteAccountRestrictionState(
				txCtx,
				event,
			); cleanupErr != nil {
				return nil, cleanupErr
			}
			applied = circleAccountClosedInboxDocument{
				ID:                event.EventID,
				EventDigest:       event.Digest(),
				AccountDigest:     irreversibleCircleDigest(event.AccountID),
				AccountVersion:    event.AccountVersion,
				AffectedCircleIDs: sortedStringSet(summary.affectedCircleIDs),
				AppliedAt:         projection.now().UTC(),
			}
			if _, insertErr := projection.inbox.InsertOne(
				txCtx,
				applied,
			); insertErr != nil {
				return nil, insertErr
			}
			return nil, nil
		},
	)
	if err != nil {
		if existing, existingFound, findErr := projection.loadInboxByEventID(
			ctx,
			event,
		); findErr == nil && existingFound {
			applied = existing
			err = nil
		}
	}
	if err != nil {
		if errors.Is(
			err,
			application.ErrUserAccountClosedEventConflict,
		) {
			return application.UserAccountClosedApplyResult{}, err
		}
		if mongo.IsDuplicateKeyError(err) {
			return application.UserAccountClosedApplyResult{},
				application.ErrUserAccountClosedEventConflict
		}
		return application.UserAccountClosedApplyResult{},
			fmt.Errorf("apply circle UserAccountClosed cleanup: %w", err)
	}
	if err := projection.completeCacheInvalidation(
		ctx,
		event,
		applied,
	); err != nil {
		return application.UserAccountClosedApplyResult{}, err
	}
	return application.UserAccountClosedApplyResult{}, nil
}

func (projection *MongoUserAccountClosedProjection) deleteAccountRestrictionState(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) error {
	subjects := event.SubjectIDs()
	if _, err := projection.restrictions.DeleteMany(
		ctx,
		bson.M{"$or": bson.A{
			bson.M{"_id": event.AccountID},
			bson.M{"subjects": bson.M{"$in": subjects}},
		}},
	); err != nil {
		return fmt.Errorf("delete closed circle account restriction state: %w", err)
	}
	if _, err := projection.restrictionInbox.DeleteMany(
		ctx,
		bson.M{"accountId": event.AccountID},
	); err != nil {
		return fmt.Errorf("delete closed circle account restriction inbox: %w", err)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) persistClosedSubjects(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) error {
	now := projection.now().UTC()
	for _, subject := range event.SubjectIDs() {
		_, err := projection.closedSubjects.UpdateOne(
			ctx,
			bson.M{"_id": application.UserAccountClosedSubjectID(subject)},
			bson.M{
				"$max": bson.M{"accountVersion": event.AccountVersion},
				"$set": bson.M{
					"eventDigest": event.Digest(),
					"closedAt":    event.UpdatedAt.UTC(),
					"updatedAt":   now,
				},
				"$setOnInsert": bson.M{"createdAt": now},
			},
			options.UpdateOne().SetUpsert(true),
		)
		if err != nil {
			return fmt.Errorf(
				"persist circle closed-account subject: %w",
				err,
			)
		}
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) loadInboxByEventID(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (circleAccountClosedInboxDocument, bool, error) {
	var document circleAccountClosedInboxDocument
	err := projection.inbox.FindOne(
		ctx,
		bson.M{"_id": event.EventID},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return circleAccountClosedInboxDocument{}, false, nil
	}
	if err != nil {
		return circleAccountClosedInboxDocument{}, false,
			fmt.Errorf("read circle UserAccountClosed inbox: %w", err)
	}
	if document.EventDigest != event.Digest() ||
		document.AccountVersion != event.AccountVersion ||
		document.AccountDigest != irreversibleCircleDigest(event.AccountID) {
		return circleAccountClosedInboxDocument{}, true,
			application.ErrUserAccountClosedEventConflict
	}
	return document, true, nil
}

func (projection *MongoUserAccountClosedProjection) loadInboxByAccountVersion(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (circleAccountClosedInboxDocument, bool, error) {
	var document circleAccountClosedInboxDocument
	err := projection.inbox.FindOne(
		ctx,
		bson.M{
			"accountDigest":  irreversibleCircleDigest(event.AccountID),
			"accountVersion": event.AccountVersion,
		},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return circleAccountClosedInboxDocument{}, false, nil
	}
	if err != nil {
		return circleAccountClosedInboxDocument{}, false,
			fmt.Errorf(
				"read circle UserAccountClosed account receipt: %w",
				err,
			)
	}
	return document, true, nil
}

func (projection *MongoUserAccountClosedProjection) completeCacheInvalidation(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	inbox circleAccountClosedInboxDocument,
) error {
	for _, circleID := range inbox.AffectedCircleIDs {
		if err := projection.redis.Del(
			ctx,
			"cache:circle:"+circleID,
		); err != nil {
			return fmt.Errorf(
				"invalidate circle account-closure cache: %w",
				err,
			)
		}
	}
	if inbox.CacheCompletedAt != nil {
		return nil
	}
	completedAt := projection.now().UTC()
	result, err := projection.inbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         event.EventID,
			"eventDigest": event.Digest(),
		},
		bson.M{"$set": bson.M{"cacheCompletedAt": completedAt}},
	)
	if err != nil {
		return fmt.Errorf(
			"complete circle account-closure cache receipt: %w",
			err,
		)
	}
	if result.MatchedCount != 1 {
		return errors.New(
			"circle UserAccountClosed inbox disappeared before cache completion",
		)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) RecordUserAccountClosedFailure(
	ctx context.Context,
	messageID string,
	eventID string,
	cause error,
) (int64, error) {
	if strings.TrimSpace(messageID) == "" || cause == nil {
		return 0, errors.New(
			"circle UserAccountClosed failure identity and cause are required",
		)
	}
	now := projection.now().UTC()
	var document struct {
		Attempts int64 `bson:"attempts"`
	}
	err := projection.failures.FindOneAndUpdate(
		ctx,
		bson.M{
			"_id":            irreversibleCircleDigest(messageID),
			"deadLetteredAt": bson.M{"$exists": false},
		},
		bson.M{
			"$inc": bson.M{"attempts": int64(1)},
			"$set": bson.M{
				"sourceStreamId": messageID,
				"eventDigest":    irreversibleCircleDigest(eventID),
				"errorDigest":    irreversibleCircleDigest(cause.Error()),
				"lastFailedAt":   now,
				"expiresAt": now.Add(
					circleAccountClosedFailureRetention,
				),
			},
			"$setOnInsert": bson.M{"createdAt": now},
		},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, fmt.Errorf(
			"persist circle UserAccountClosed failure: %w",
			err,
		)
	}
	return document.Attempts, nil
}

func (projection *MongoUserAccountClosedProjection) ClearUserAccountClosedFailure(
	ctx context.Context,
	messageID string,
) error {
	_, err := projection.failures.DeleteOne(
		ctx,
		bson.M{"_id": irreversibleCircleDigest(messageID)},
	)
	if err != nil {
		return fmt.Errorf(
			"delete circle UserAccountClosed failure: %w",
			err,
		)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) IsUserAccountClosedDeadLettered(
	ctx context.Context,
	messageID string,
) (bool, error) {
	var document struct {
		DeadLetteredAt *time.Time `bson:"deadLetteredAt"`
	}
	err := projection.failures.FindOne(
		ctx,
		bson.M{"_id": irreversibleCircleDigest(messageID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf(
			"read circle UserAccountClosed dead-letter state: %w",
			err,
		)
	}
	return document.DeadLetteredAt != nil &&
		!document.DeadLetteredAt.IsZero(), nil
}

func (projection *MongoUserAccountClosedProjection) MarkUserAccountClosedDeadLettered(
	ctx context.Context,
	messageID string,
) error {
	now := projection.now().UTC()
	result, err := projection.failures.UpdateOne(
		ctx,
		bson.M{"_id": irreversibleCircleDigest(messageID)},
		bson.M{
			"$set": bson.M{
				"deadLetteredAt": now,
				"lastFailedAt":   now,
			},
			// Terminal DLQ recovery must be explicit; the normal retry TTL
			// must not make an unacknowledged source PEL consumable again.
			"$unset": bson.M{"expiresAt": ""},
		},
	)
	if err != nil {
		return fmt.Errorf(
			"mark circle UserAccountClosed dead-letter state: %w",
			err,
		)
	}
	if result.MatchedCount != 1 {
		return errors.New("circle UserAccountClosed failure state is missing")
	}
	return nil
}

func closedCircleAnonymousID(subject string) string {
	sum := sha256.Sum256([]byte(
		"circle-closed-anonymous\x00" + strings.TrimSpace(subject),
	))
	return closedAccountAnonymousPrefix + hex.EncodeToString(sum[:16])
}

func irreversibleCircleDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}

func sortedStringSet(values map[string]struct{}) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		if value = strings.TrimSpace(value); value != "" {
			result = append(result, value)
		}
	}
	sort.Strings(result)
	return result
}
