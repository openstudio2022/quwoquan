package accountclosure

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	InboxCollection                  = "user_account_closed_inbox"
	FailureCollection                = "user_account_closed_failures"
	SearchWorkCollection             = "user_account_closed_search_work"
	ClosedSubjectCollection          = "closed_account_subjects"
	ClosedSubjectTombstoneCollection = "closed_account_subject_tombstones"

	failureRetention = 30 * 24 * time.Hour
)

type inboxDocument struct {
	ID             string     `bson:"_id"`
	EventDigest    string     `bson:"eventDigest"`
	AccountVersion int64      `bson:"accountVersion"`
	MongoAppliedAt *time.Time `bson:"mongoAppliedAt,omitempty"`
	CompletedAt    *time.Time `bson:"completedAt,omitempty"`
}

type failureDocument struct {
	ID       string `bson:"_id"`
	Attempts int64  `bson:"attempts"`
}

type CleanupState struct {
	Completed      bool
	MongoApplied   bool
	AlreadyApplied bool
}

type MongoStore struct {
	db                *mongo.Database
	inbox             *mongo.Collection
	failures          *mongo.Collection
	searchWork        *mongo.Collection
	closedSubjects    *mongo.Collection
	subjectTombstones *mongo.Collection
	subjectDigestor   SubjectDigestor
}

func NewMongoStore(
	db *mongo.Database,
	subjectDigestor SubjectDigestor,
) (*MongoStore, error) {
	if db == nil || subjectDigestor == nil {
		return nil, errors.New(
			"UserAccountClosed Mongo store requires database and subject digestor",
		)
	}
	return &MongoStore{
		db:                db,
		inbox:             db.Collection(InboxCollection),
		failures:          db.Collection(FailureCollection),
		searchWork:        db.Collection(SearchWorkCollection),
		closedSubjects:    db.Collection(ClosedSubjectCollection),
		subjectTombstones: db.Collection(ClosedSubjectTombstoneCollection),
		subjectDigestor:   subjectDigestor,
	}, nil
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.inbox.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{
				{Key: "completedAt", Value: -1},
			},
			Options: options.Index().
				SetName("idx_user_account_closed_completed"),
		},
	); err != nil {
		return fmt.Errorf(
			"create UserAccountClosed inbox indexes: %w",
			err,
		)
	}
	if _, err := store.failures.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "expireAt", Value: 1}},
			Options: options.Index().
				SetName("idx_user_account_closed_failure_expire").
				SetExpireAfterSeconds(0),
		},
	); err != nil {
		return fmt.Errorf(
			"create UserAccountClosed failure indexes: %w",
			err,
		)
	}
	if _, err := store.searchWork.Indexes().CreateMany(
		ctx,
		[]mongo.IndexModel{
			{
				Keys: bson.D{
					{Key: "eventId", Value: 1},
					{Key: "doneAt", Value: 1},
					{Key: "_id", Value: 1},
				},
				Options: options.Index().
					SetName("idx_user_account_closed_search_work"),
			},
			{
				Keys: bson.D{{Key: "expireAt", Value: 1}},
				Options: options.Index().
					SetName("idx_user_account_closed_search_work_expire").
					SetExpireAfterSeconds(0),
			},
		},
	); err != nil {
		return fmt.Errorf(
			"create UserAccountClosed search-work indexes: %w",
			err,
		)
	}
	if _, err := store.closedSubjects.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "eventDigest", Value: 1}},
			Options: options.Index().
				SetName("idx_closed_account_event_digest").
				SetUnique(true),
		},
	); err != nil {
		return fmt.Errorf(
			"create closed-account subject indexes: %w",
			err,
		)
	}
	if _, err := store.subjectTombstones.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "closedAt", Value: -1}},
			Options: options.Index().
				SetName("idx_closed_account_subject_closed_at"),
		},
	); err != nil {
		return fmt.Errorf(
			"create closed-account subject tombstone indexes: %w",
			err,
		)
	}
	return nil
}

func (store *MongoStore) RegisterClosedSubjects(
	ctx context.Context,
	event UserAccountClosedEvent,
) error {
	if err := event.Validate(); err != nil {
		return err
	}
	now := time.Now().UTC()
	models := make([]mongo.WriteModel, 0, len(event.SubjectIDs()))
	for _, subjectID := range event.SubjectIDs() {
		digest, err := store.subjectDigestor.DigestSubject(subjectID)
		if err != nil {
			return err
		}
		models = append(models, mongo.NewUpdateOneModel().
			SetFilter(bson.M{"_id": digest}).
			SetUpdate(bson.M{"$setOnInsert": bson.M{
				"eventDigest":    event.Digest(),
				"accountVersion": event.AccountVersion,
				"closedAt":       event.Payload.UpdatedAt.UTC(),
				"recordedAt":     now,
			}}).
			SetUpsert(true))
	}
	if len(models) == 0 {
		return nil
	}
	if _, err := store.subjectTombstones.BulkWrite(
		ctx,
		models,
		options.BulkWrite().SetOrdered(false),
	); err != nil {
		return fmt.Errorf(
			"register closed-account subject tombstones: %w",
			err,
		)
	}
	return nil
}

func (store *MongoStore) IsSubjectClosed(
	ctx context.Context,
	subjectID string,
) (bool, error) {
	digest, err := store.subjectDigestor.DigestSubject(subjectID)
	if err != nil {
		return false, err
	}
	count, err := store.subjectTombstones.CountDocuments(
		ctx,
		bson.M{"_id": digest},
		options.Count().SetLimit(1),
	)
	if err != nil {
		return false, fmt.Errorf("read closed-account subject tombstone: %w", err)
	}
	return count != 0, nil
}

func (store *MongoStore) ReserveCleanup(
	ctx context.Context,
	event UserAccountClosedEvent,
) (CleanupState, error) {
	if err := event.Validate(); err != nil {
		return CleanupState{}, err
	}
	_, err := store.inbox.UpdateOne(
		ctx,
		bson.M{"_id": event.EventID},
		bson.M{"$setOnInsert": bson.M{
			"eventDigest":    event.Digest(),
			"accountVersion": event.AccountVersion,
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return CleanupState{}, fmt.Errorf(
			"reserve UserAccountClosed inbox state: %w",
			err,
		)
	}
	state, _, err := store.loadState(ctx, event)
	return state, err
}

func (store *MongoStore) PrepareCleanup(
	ctx context.Context,
	event UserAccountClosedEvent,
) (CleanupState, error) {
	if err := event.Validate(); err != nil {
		return CleanupState{}, err
	}
	state, found, err := store.loadState(ctx, event)
	if err != nil {
		return CleanupState{}, err
	}
	if found && (state.Completed || state.MongoApplied) {
		state.AlreadyApplied = true
		return state, nil
	}

	session, err := store.db.Client().StartSession()
	if err != nil {
		return CleanupState{}, fmt.Errorf(
			"start UserAccountClosed Mongo session: %w",
			err,
		)
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(
		ctx,
		func(txCtx context.Context) (any, error) {
			txState, txFound, loadErr := store.loadState(txCtx, event)
			if loadErr != nil {
				return nil, loadErr
			}
			if txFound &&
				(txState.Completed || txState.MongoApplied) {
				return nil, nil
			}
			if cleanupErr := store.applyContentCleanup(
				txCtx,
				event,
			); cleanupErr != nil {
				return nil, cleanupErr
			}
			now := time.Now().UTC()
			_, updateErr := store.inbox.UpdateOne(
				txCtx,
				bson.M{"_id": event.EventID},
				bson.M{
					"$set": bson.M{
						"eventDigest":    event.Digest(),
						"accountVersion": event.AccountVersion,
						"mongoAppliedAt": now,
					},
				},
				options.UpdateOne().SetUpsert(true),
			)
			return nil, updateErr
		},
	)
	if err != nil {
		return CleanupState{}, fmt.Errorf(
			"apply UserAccountClosed Mongo cleanup: %w",
			err,
		)
	}
	state, _, err = store.loadState(ctx, event)
	state.AlreadyApplied = false
	return state, err
}

func (store *MongoStore) PendingSearchDocuments(
	ctx context.Context,
	eventID string,
	limit int64,
) ([]SearchDocumentID, error) {
	if limit <= 0 {
		limit = 200
	}
	cursor, err := store.searchWork.Find(
		ctx,
		bson.M{
			"eventId": eventID,
			"doneAt":  bson.M{"$exists": false},
		},
		options.Find().
			SetProjection(bson.M{
				"objectType": 1,
				"objectId":   1,
			}).
			SetSort(bson.D{{Key: "_id", Value: 1}}).
			SetLimit(limit),
	)
	if err != nil {
		return nil, fmt.Errorf(
			"read UserAccountClosed search work: %w",
			err,
		)
	}
	defer cursor.Close(ctx)
	var documents []struct {
		ObjectType string `bson:"objectType"`
		ObjectID   string `bson:"objectId"`
	}
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, fmt.Errorf(
			"decode UserAccountClosed search work: %w",
			err,
		)
	}
	identities := make([]SearchDocumentID, 0, len(documents))
	for _, document := range documents {
		identity := SearchDocumentID{
			ObjectType: document.ObjectType,
			ObjectID:   document.ObjectID,
		}
		if err := identity.Validate(); err != nil {
			return nil, fmt.Errorf(
				"decode UserAccountClosed search identity: %w",
				err,
			)
		}
		identities = append(identities, identity)
	}
	return identities, nil
}

func (store *MongoStore) MarkSearchDocumentDone(
	ctx context.Context,
	eventID string,
	document SearchDocumentID,
) error {
	if err := document.Validate(); err != nil {
		return err
	}
	now := time.Now().UTC()
	result, err := store.searchWork.UpdateOne(
		ctx,
		bson.M{
			"_id":     searchWorkID(eventID, document.CanonicalID()),
			"eventId": eventID,
		},
		bson.M{"$set": bson.M{
			"doneAt":   now,
			"expireAt": now.Add(failureRetention),
		}},
	)
	if err != nil {
		return fmt.Errorf(
			"complete UserAccountClosed search work: %w",
			err,
		)
	}
	if result.MatchedCount != 1 {
		return errors.New("UserAccountClosed search work is missing")
	}
	return nil
}

func (store *MongoStore) MarkCompleted(
	ctx context.Context,
	event UserAccountClosedEvent,
) error {
	pending, err := store.searchWork.CountDocuments(
		ctx,
		bson.M{
			"eventId": event.EventID,
			"doneAt":  bson.M{"$exists": false},
		},
		options.Count().SetLimit(1),
	)
	if err != nil {
		return fmt.Errorf(
			"count UserAccountClosed search work: %w",
			err,
		)
	}
	if pending != 0 {
		return errors.New(
			"UserAccountClosed search work is not complete",
		)
	}
	now := time.Now().UTC()
	result, err := store.inbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         event.EventID,
			"eventDigest": event.Digest(),
		},
		bson.M{"$set": bson.M{"completedAt": now}},
	)
	if err != nil {
		return fmt.Errorf(
			"mark UserAccountClosed complete: %w",
			err,
		)
	}
	if result.MatchedCount != 1 {
		return errors.New(
			"UserAccountClosed inbox state is missing",
		)
	}
	return nil
}

func (store *MongoStore) RecordFailure(
	ctx context.Context,
	stream string,
	messageID string,
	eventID string,
	cause error,
) (int64, error) {
	now := time.Now().UTC()
	var document failureDocument
	err := store.failures.FindOneAndUpdate(
		ctx,
		bson.M{"_id": failureID(stream, messageID)},
		bson.M{
			"$inc": bson.M{"attempts": int64(1)},
			"$set": bson.M{
				"eventDigest":  irreversibleDigest(eventID),
				"errorDigest":  irreversibleDigest(cause.Error()),
				"lastFailedAt": now,
				"expireAt":     now.Add(failureRetention),
			},
			"$setOnInsert": bson.M{"createdAt": now},
		},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, fmt.Errorf(
			"persist UserAccountClosed failure: %w",
			err,
		)
	}
	return document.Attempts, nil
}

func (store *MongoStore) ClearFailure(
	ctx context.Context,
	stream string,
	messageID string,
) error {
	_, err := store.failures.DeleteOne(
		ctx,
		bson.M{"_id": failureID(stream, messageID)},
	)
	if err != nil {
		return fmt.Errorf(
			"delete UserAccountClosed failure state: %w",
			err,
		)
	}
	return nil
}

func (store *MongoStore) loadState(
	ctx context.Context,
	event UserAccountClosedEvent,
) (CleanupState, bool, error) {
	var document inboxDocument
	err := store.inbox.FindOne(
		ctx,
		bson.M{"_id": event.EventID},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return CleanupState{}, false, nil
	}
	if err != nil {
		return CleanupState{}, false, fmt.Errorf(
			"load UserAccountClosed inbox state: %w",
			err,
		)
	}
	if document.EventDigest != event.Digest() ||
		document.AccountVersion != event.AccountVersion {
		return CleanupState{}, true, errors.New(
			"UserAccountClosed eventId was reused with different data",
		)
	}
	return CleanupState{
		Completed:    document.CompletedAt != nil,
		MongoApplied: document.MongoAppliedAt != nil,
	}, true, nil
}

func failureID(stream string, messageID string) string {
	return irreversibleDigest(stream + "\x00" + messageID)
}

func searchWorkID(eventID string, canonicalID string) string {
	return irreversibleDigest(eventID + "\x00" + canonicalID)
}
