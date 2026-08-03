package accountclosure

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
	accountclosureapp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/application"
)

const (
	contentAccountRestrictionStateCollection     = "content_user_account_restrictions"
	contentAccountRestrictionInboxCollection     = "content_user_account_restriction_inbox"
	contentAccountRestrictionWatermarkCollection = "content_user_account_restriction_watermarks"
)

type contentAccountRestrictionInboxDocument struct {
	ID             string    `bson:"_id"`
	EventDigest    string    `bson:"eventDigest"`
	AccountDigest  string    `bson:"accountDigest"`
	AccountVersion int64     `bson:"accountVersion"`
	Stale          bool      `bson:"stale"`
	Affected       int64     `bson:"affected"`
	AppliedAt      time.Time `bson:"appliedAt"`
}

type contentAccountRestrictionWatermarkDocument struct {
	ID             string `bson:"_id"`
	AccountVersion int64  `bson:"accountVersion"`
	EventDigest    string `bson:"eventDigest"`
	Terminal       bool   `bson:"terminal"`
}

// MongoAccountRestrictionProjection owns only Content's reversible local read
// model. The collection and subject-field mapping is fixed in this adapter;
// lifecycle status and irreversible tombstones remain closure-owned.
type MongoAccountRestrictionProjection struct {
	db             *mongo.Database
	states         *mongo.Collection
	inbox          *mongo.Collection
	watermarks     *mongo.Collection
	posts          *mongo.Collection
	comments       *mongo.Collection
	closedSubjects PersistentSubjectClosureLookup
	now            func() time.Time
}

var _ accountclosureapp.AccountRestrictionProjection = (*MongoAccountRestrictionProjection)(nil)

func NewAccountRestrictionProjection(
	db *mongo.Database,
	closedSubjects PersistentSubjectClosureLookup,
) (*MongoAccountRestrictionProjection, error) {
	if db == nil || closedSubjects == nil {
		return nil, errors.New(
			"content account restriction projection requires MongoDB and closed-subject authority",
		)
	}
	return &MongoAccountRestrictionProjection{
		db:             db,
		states:         db.Collection(contentAccountRestrictionStateCollection),
		inbox:          db.Collection(contentAccountRestrictionInboxCollection),
		watermarks:     db.Collection(contentAccountRestrictionWatermarkCollection),
		posts:          db.Collection("posts"),
		comments:       db.Collection("comments"),
		closedSubjects: closedSubjects,
		now:            time.Now,
	}, nil
}

func (projection *MongoAccountRestrictionProjection) EnsureIndexes(
	ctx context.Context,
) error {
	if projection == nil || projection.db == nil {
		return errors.New("content account restriction projection is not configured")
	}
	if _, err := projection.states.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "subjects", Value: 1}, {Key: "restricted", Value: 1}},
			Options: options.Index().
				SetName("idx_content_account_restriction_subject_state"),
		},
		{
			Keys: bson.D{{Key: "accountVersion", Value: -1}},
			Options: options.Index().
				SetName("idx_content_account_restriction_version"),
		},
	}); err != nil {
		return fmt.Errorf("ensure content account restriction state indexes: %w", err)
	}
	if _, err := projection.inbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "accountDigest", Value: 1},
				{Key: "accountVersion", Value: 1},
			},
			Options: options.Index().
				SetName("uq_content_account_restriction_account_version").
				SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "appliedAt", Value: -1}},
			Options: options.Index().
				SetName("idx_content_account_restriction_applied"),
		},
	}); err != nil {
		return fmt.Errorf("ensure content account restriction inbox indexes: %w", err)
	}
	if _, err := projection.watermarks.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "terminal", Value: 1}, {Key: "accountVersion", Value: -1}},
		Options: options.Index().
			SetName("idx_content_account_restriction_terminal_version"),
	}); err != nil {
		return fmt.Errorf("ensure content account restriction watermark index: %w", err)
	}
	return nil
}

func (projection *MongoAccountRestrictionProjection) Apply(
	ctx context.Context,
	event accountrestriction.Event,
) (accountclosureapp.UserAccountRestrictionProjectionResult, error) {
	if projection == nil || projection.db == nil || projection.closedSubjects == nil {
		return accountclosureapp.UserAccountRestrictionProjectionResult{}, errors.New(
			"content account restriction projection is not configured",
		)
	}
	if err := event.Validate(); err != nil {
		return accountclosureapp.UserAccountRestrictionProjectionResult{}, err
	}
	// Historical closure tombstones remain authoritative. This read is a
	// fail-closed migration guard; current closure also writes the transactionally
	// serialized terminal watermark below.
	for _, subjectID := range event.SubjectIDs() {
		closed, err := projection.closedSubjects.IsSubjectClosed(ctx, subjectID)
		if err != nil {
			return accountclosureapp.UserAccountRestrictionProjectionResult{}, fmt.Errorf(
				"verify content account restriction subject is not closed: %w",
				err,
			)
		}
		if closed {
			return accountclosureapp.UserAccountRestrictionProjectionResult{
				Replayed: true,
				Stale:    true,
				Terminal: true,
			}, nil
		}
	}
	if replay, found, err := projection.loadInbox(ctx, event); err != nil {
		return accountclosureapp.UserAccountRestrictionProjectionResult{}, err
	} else if found {
		return replay, nil
	}

	session, err := projection.db.Client().StartSession()
	if err != nil {
		return accountclosureapp.UserAccountRestrictionProjectionResult{}, fmt.Errorf(
			"start content account restriction transaction: %w",
			err,
		)
	}
	defer session.EndSession(ctx)
	result := accountclosureapp.UserAccountRestrictionProjectionResult{}
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
			result = accountclosureapp.UserAccountRestrictionProjectionResult{
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
			return nil, accountclosureapp.ErrUserAccountRestrictionProjectionConflict
		}
		if found && watermark.AccountVersion > event.AccountVersion {
			result = accountclosureapp.UserAccountRestrictionProjectionResult{
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
		accountDigest := contentAccountRestrictionDigest(event.AccountID)
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
			return nil, fmt.Errorf("persist content account restriction state: %w", updateErr)
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
			return nil, fmt.Errorf("persist content account restriction watermark: %w", updateErr)
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
			return accountclosureapp.UserAccountRestrictionProjectionResult{}, loadErr
		}
		return accountclosureapp.UserAccountRestrictionProjectionResult{},
			accountclosureapp.ErrUserAccountRestrictionProjectionConflict
	}
	if errors.Is(err, accountclosureapp.ErrUserAccountRestrictionProjectionConflict) {
		return accountclosureapp.UserAccountRestrictionProjectionResult{}, err
	}
	return accountclosureapp.UserAccountRestrictionProjectionResult{}, fmt.Errorf(
		"apply content account restriction projection: %w",
		err,
	)
}

func (projection *MongoAccountRestrictionProjection) RestrictedSubjects(
	ctx context.Context,
	subjects []string,
) (map[string]bool, error) {
	subjects = accountrestriction.NormalizeSubjects(subjects)
	result := make(map[string]bool, len(subjects))
	if len(subjects) == 0 {
		return result, nil
	}
	if projection == nil || projection.states == nil {
		return nil, errors.New("content account restriction projection is not configured")
	}
	cursor, err := projection.states.Find(
		ctx,
		bson.M{"restricted": true, "subjects": bson.M{"$in": subjects}},
		options.Find().SetProjection(bson.M{"subjects": 1}),
	)
	if err != nil {
		return nil, fmt.Errorf("read content account restrictions: %w", err)
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
			return nil, fmt.Errorf("decode content account restriction: %w", err)
		}
		for _, subject := range document.Subjects {
			if _, exists := wanted[subject]; exists {
				result[subject] = true
			}
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate content account restrictions: %w", err)
	}
	return result, nil
}

func (projection *MongoAccountRestrictionProjection) applyOwnedMutations(
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
	}{
		{"post", projection.posts},
		{"comment", projection.comments},
	}
	var affected int64
	for _, target := range targets {
		result, err := target.collection.UpdateMany(
			ctx,
			bson.M{"authorId": bson.M{"$in": event.SubjectIDs()}},
			update,
		)
		if err != nil {
			return 0, fmt.Errorf("project content restriction to %s: %w", target.name, err)
		}
		affected += result.ModifiedCount
	}
	return affected, nil
}

func (projection *MongoAccountRestrictionProjection) loadWatermark(
	ctx context.Context,
	accountID string,
) (contentAccountRestrictionWatermarkDocument, bool, error) {
	var document contentAccountRestrictionWatermarkDocument
	err := projection.watermarks.FindOne(
		ctx,
		bson.M{"_id": contentAccountRestrictionDigest(accountID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return contentAccountRestrictionWatermarkDocument{}, false, nil
	}
	if err != nil {
		return contentAccountRestrictionWatermarkDocument{}, false,
			fmt.Errorf("load content account restriction watermark: %w", err)
	}
	return document, true, nil
}

func (projection *MongoAccountRestrictionProjection) loadInbox(
	ctx context.Context,
	event accountrestriction.Event,
) (accountclosureapp.UserAccountRestrictionProjectionResult, bool, error) {
	var document contentAccountRestrictionInboxDocument
	err := projection.inbox.FindOne(ctx, bson.M{"_id": event.EventID}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return accountclosureapp.UserAccountRestrictionProjectionResult{}, false, nil
	}
	if err != nil {
		return accountclosureapp.UserAccountRestrictionProjectionResult{}, false,
			fmt.Errorf("load content account restriction inbox: %w", err)
	}
	if document.EventDigest != event.Digest() ||
		document.AccountDigest != contentAccountRestrictionDigest(event.AccountID) ||
		document.AccountVersion != event.AccountVersion {
		return accountclosureapp.UserAccountRestrictionProjectionResult{}, false,
			accountclosureapp.ErrUserAccountRestrictionProjectionConflict
	}
	return accountclosureapp.UserAccountRestrictionProjectionResult{
		Replayed: true,
		Stale:    document.Stale,
		Affected: document.Affected,
	}, true, nil
}

func (projection *MongoAccountRestrictionProjection) insertInbox(
	ctx context.Context,
	event accountrestriction.Event,
	result accountclosureapp.UserAccountRestrictionProjectionResult,
) error {
	_, err := projection.inbox.InsertOne(ctx, contentAccountRestrictionInboxDocument{
		ID:             event.EventID,
		EventDigest:    event.Digest(),
		AccountDigest:  contentAccountRestrictionDigest(event.AccountID),
		AccountVersion: event.AccountVersion,
		Stale:          result.Stale,
		Affected:       result.Affected,
		AppliedAt:      projection.now().UTC(),
	})
	if err != nil {
		return fmt.Errorf("append content account restriction inbox: %w", err)
	}
	return nil
}

func finalizeContentAccountRestrictionClosure(
	ctx context.Context,
	db *mongo.Database,
	event UserAccountClosedEvent,
) error {
	if db == nil {
		return errors.New("content account restriction closure requires MongoDB")
	}
	now := time.Now().UTC()
	accountDigest := contentAccountRestrictionDigest(event.AccountID)
	if _, err := db.Collection(contentAccountRestrictionWatermarkCollection).UpdateOne(
		ctx,
		bson.M{"_id": accountDigest},
		bson.M{
			"$max": bson.M{
				"accountVersion": event.AccountVersion,
				"closedAt":       event.Payload.UpdatedAt.UTC(),
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
		return fmt.Errorf("persist content account restriction terminal watermark: %w", err)
	}
	accountID := strings.TrimSpace(event.AccountID)
	if _, err := db.Collection(contentAccountRestrictionStateCollection).DeleteMany(
		ctx,
		bson.M{"_id": bson.M{"$in": bson.A{accountDigest, accountID}}},
	); err != nil {
		return fmt.Errorf("delete content account restriction identity state: %w", err)
	}
	if _, err := db.Collection(contentAccountRestrictionInboxCollection).DeleteMany(
		ctx,
		bson.M{"$or": bson.A{
			bson.M{"accountDigest": accountDigest},
			bson.M{"accountId": accountID},
		}},
	); err != nil {
		return fmt.Errorf("delete content account restriction inbox: %w", err)
	}
	return nil
}

func contentAccountRestrictionDigest(accountID string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(accountID)))
	return hex.EncodeToString(digest[:])
}
