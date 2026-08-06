package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

const (
	UserAccountClosedInboxCollection   = "integration_user_account_closed_inbox"
	UserAccountClosedFailureCollection = "integration_user_account_closed_failures"
	userAccountClosedFailureRetention  = 7 * 24 * time.Hour
)

type userAccountClosedInboxDocument struct {
	ID                     string    `bson:"_id"`
	EventDigest            string    `bson:"eventDigest"`
	DeletedRequests        int64     `bson:"deletedRequests"`
	DeletedTasks           int64     `bson:"deletedTasks"`
	DeletedAttempts        int64     `bson:"deletedAttempts"`
	DeletedResultOutboxes  int64     `bson:"deletedResultOutboxes"`
	DeletedRecoveryRecords int64     `bson:"deletedRecoveryRecords"`
	AppliedAt              time.Time `bson:"appliedAt"`
}

type MongoUserAccountClosedProjection struct {
	db               *mongo.Database
	requestOutboxes  *mongo.Collection
	tasks            *mongo.Collection
	resultOutboxes   *mongo.Collection
	recoveryReceipts *mongo.Collection
	inbox            *mongo.Collection
	failures         *mongo.Collection
	attempts         application.AttemptSubjectClosure
}

var _ application.UserAccountClosedProjectionStore = (*MongoUserAccountClosedProjection)(nil)

func NewMongoUserAccountClosedProjection(
	db *mongo.Database,
	attempts application.AttemptSubjectClosure,
) (*MongoUserAccountClosedProjection, error) {
	if db == nil || attempts == nil {
		return nil, errors.New(
			"integration UserAccountClosed projection requires MongoDB and attempt closure",
		)
	}
	return &MongoUserAccountClosedProjection{
		db:               db,
		requestOutboxes:  db.Collection("reliable_task_outbox"),
		tasks:            db.Collection("reliable_async_task"),
		resultOutboxes:   db.Collection("external_interaction_result_outbox"),
		recoveryReceipts: db.Collection("reliable_task_recovery_receipts"),
		inbox:            db.Collection(UserAccountClosedInboxCollection),
		failures:         db.Collection(UserAccountClosedFailureCollection),
		attempts:         attempts,
	}, nil
}

func (projection *MongoUserAccountClosedProjection) EnsureIndexes(ctx context.Context) error {
	if projection == nil || projection.db == nil {
		return errors.New("integration UserAccountClosed projection is not configured")
	}
	if _, err := projection.inbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "appliedAt", Value: -1}},
		Options: options.Index().SetName("idx_integration_account_closed_applied"),
	}); err != nil {
		return fmt.Errorf("ensure integration account closure inbox index: %w", err)
	}
	if _, err := projection.failures.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "eventDigest", Value: 1}},
			Options: options.Index().SetName("idx_integration_account_closed_failure_event"),
		},
		{
			Keys: bson.D{{Key: "expireAt", Value: 1}},
			Options: options.Index().
				SetName("ttl_integration_account_closed_failures").
				SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return fmt.Errorf("ensure integration account closure failure indexes: %w", err)
	}
	for _, collection := range []*mongo.Collection{
		projection.requestOutboxes,
		projection.tasks,
	} {
		if _, err := collection.Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys: bson.D{{Key: "payload.subjectDigest", Value: 1}},
			Options: options.Index().SetName(
				"idx_" + collection.Name() + "_subject_cleanup",
			),
		}); err != nil {
			return fmt.Errorf("ensure %s subject cleanup index: %w", collection.Name(), err)
		}
	}
	if _, err := projection.resultOutboxes.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "subjectDigest", Value: 1}},
		Options: options.Index().SetName("idx_ext_result_outbox_subject_cleanup"),
	}); err != nil {
		return fmt.Errorf("ensure result outbox subject cleanup index: %w", err)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) ApplyUserAccountClosed(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	if projection == nil || projection.db == nil || projection.attempts == nil {
		return application.UserAccountClosedProjectionResult{},
			errors.New("integration UserAccountClosed projection is not configured")
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedProjectionResult{}, err
	}
	if existing, found, err := projection.loadInbox(ctx, event.EventID); err != nil {
		return application.UserAccountClosedProjectionResult{}, err
	} else if found {
		return replayUserAccountClosed(existing, event)
	}

	session, err := projection.db.Client().StartSession()
	if err != nil {
		return application.UserAccountClosedProjectionResult{},
			fmt.Errorf("start integration account closure transaction: %w", err)
	}
	defer session.EndSession(ctx)

	result := application.UserAccountClosedProjectionResult{}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		existing, found, loadErr := projection.loadInbox(txCtx, event.EventID)
		if loadErr != nil {
			return nil, loadErr
		}
		if found {
			replayed, replayErr := replayUserAccountClosed(existing, event)
			result = replayed
			return nil, replayErr
		}
		cleanup, cleanupErr := projection.cleanup(txCtx, event)
		if cleanupErr != nil {
			return nil, cleanupErr
		}
		result = cleanup
		_, insertErr := projection.inbox.InsertOne(txCtx, userAccountClosedInboxDocument{
			ID:                     event.EventID,
			EventDigest:            event.Digest(),
			DeletedRequests:        cleanup.DeletedRequests,
			DeletedTasks:           cleanup.DeletedTasks,
			DeletedAttempts:        cleanup.DeletedAttempts,
			DeletedResultOutboxes:  cleanup.DeletedResultOutboxes,
			DeletedRecoveryRecords: cleanup.DeletedRecoveryRecords,
			AppliedAt:              time.Now().UTC(),
		})
		return nil, insertErr
	})
	if err == nil {
		return result, nil
	}
	if mongo.IsDuplicateKeyError(err) {
		if existing, found, loadErr := projection.loadInbox(ctx, event.EventID); loadErr != nil {
			return application.UserAccountClosedProjectionResult{}, loadErr
		} else if found {
			return replayUserAccountClosed(existing, event)
		}
	}
	return application.UserAccountClosedProjectionResult{},
		fmt.Errorf("apply integration UserAccountClosed cleanup: %w", err)
}

func (projection *MongoUserAccountClosedProjection) cleanup(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	subjects := event.SubjectIDs()
	digests := make([]string, 0, len(subjects))
	for _, subject := range subjects {
		digests = append(digests, reliabletask.ExternalInteractionSubjectDigest(
			map[string]string{"subjectId": subject},
		))
	}
	filter := externalInteractionSubjectFilter(subjects, digests)
	taskIDs, requestIDs, err := collectExternalInteractionLocators(
		ctx,
		projection.tasks,
		filter,
	)
	if err != nil {
		return application.UserAccountClosedProjectionResult{}, err
	}
	_, outboxRequestIDs, err := collectExternalInteractionLocators(
		ctx,
		projection.requestOutboxes,
		filter,
	)
	if err != nil {
		return application.UserAccountClosedProjectionResult{}, err
	}
	requestIDs = normalizedStrings(append(requestIDs, outboxRequestIDs...))

	deletedAttempts, err := projection.attempts.DeleteByPrivacyLocators(
		ctx,
		digests,
		taskIDs,
		requestIDs,
	)
	if err != nil {
		return application.UserAccountClosedProjectionResult{}, err
	}
	resultOutboxFilter := bson.M{"subjectDigest": bson.M{"$in": digests}}
	if len(requestIDs) > 0 {
		resultOutboxFilter = bson.M{"$or": bson.A{
			resultOutboxFilter,
			bson.M{"requestId": bson.M{"$in": requestIDs}},
		}}
	}
	resultOutboxes, err := projection.resultOutboxes.DeleteMany(ctx, resultOutboxFilter)
	if err != nil {
		return application.UserAccountClosedProjectionResult{},
			fmt.Errorf("delete closed-subject result outboxes: %w", err)
	}
	var recoveryCount int64
	if len(taskIDs) > 0 {
		recoveries, deleteErr := projection.recoveryReceipts.DeleteMany(
			ctx,
			bson.M{"taskId": bson.M{"$in": taskIDs}},
		)
		if deleteErr != nil {
			return application.UserAccountClosedProjectionResult{},
				fmt.Errorf("delete closed-subject recovery receipts: %w", deleteErr)
		}
		recoveryCount = recoveries.DeletedCount
	}
	tasks, err := projection.tasks.DeleteMany(ctx, filter)
	if err != nil {
		return application.UserAccountClosedProjectionResult{},
			fmt.Errorf("delete closed-subject external tasks: %w", err)
	}
	requests, err := projection.requestOutboxes.DeleteMany(ctx, filter)
	if err != nil {
		return application.UserAccountClosedProjectionResult{},
			fmt.Errorf("delete closed-subject external request outboxes: %w", err)
	}
	return application.UserAccountClosedProjectionResult{
		DeletedRequests:        requests.DeletedCount,
		DeletedTasks:           tasks.DeletedCount,
		DeletedAttempts:        deletedAttempts,
		DeletedResultOutboxes:  resultOutboxes.DeletedCount,
		DeletedRecoveryRecords: recoveryCount,
	}, nil
}

func externalInteractionSubjectFilter(subjects, digests []string) bson.M {
	clauses := bson.A{bson.M{"payload.subjectDigest": bson.M{"$in": digests}}}
	for _, key := range []string{
		"targetPersonaId", "personaId", "recipientId", "userId", "accountId", "subjectId",
	} {
		clauses = append(clauses, bson.M{"payload." + key: bson.M{"$in": subjects}})
	}
	return bson.M{"$or": clauses}
}

func collectExternalInteractionLocators(
	ctx context.Context,
	collection *mongo.Collection,
	filter bson.M,
) ([]string, []string, error) {
	cursor, err := collection.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{"_id": 1, "aggregateId": 1, "payload.requestId": 1}),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("scan %s account closure locators: %w", collection.Name(), err)
	}
	defer cursor.Close(ctx)
	var documents []struct {
		ID          string `bson:"_id"`
		AggregateID string `bson:"aggregateId"`
		Payload     struct {
			RequestID string `bson:"requestId"`
		} `bson:"payload"`
	}
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, nil, fmt.Errorf("decode %s account closure locators: %w", collection.Name(), err)
	}
	taskIDs := make([]string, 0, len(documents))
	requestIDs := make([]string, 0, len(documents)*2)
	for _, document := range documents {
		taskIDs = append(taskIDs, document.ID)
		requestIDs = append(requestIDs, document.Payload.RequestID, document.AggregateID)
	}
	return normalizedStrings(taskIDs), normalizedStrings(requestIDs), nil
}

func normalizedStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func (projection *MongoUserAccountClosedProjection) loadInbox(
	ctx context.Context,
	eventID string,
) (userAccountClosedInboxDocument, bool, error) {
	var document userAccountClosedInboxDocument
	err := projection.inbox.FindOne(ctx, bson.M{"_id": strings.TrimSpace(eventID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return userAccountClosedInboxDocument{}, false, nil
	}
	if err != nil {
		return userAccountClosedInboxDocument{}, false,
			fmt.Errorf("read integration account closure inbox: %w", err)
	}
	return document, true, nil
}

func replayUserAccountClosed(
	document userAccountClosedInboxDocument,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	if document.EventDigest != event.Digest() {
		return application.UserAccountClosedProjectionResult{},
			application.ErrUserAccountClosedEventIDConflict
	}
	return application.UserAccountClosedProjectionResult{Replayed: true}, nil
}
