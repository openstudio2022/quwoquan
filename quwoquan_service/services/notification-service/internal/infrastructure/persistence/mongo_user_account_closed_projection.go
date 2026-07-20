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

	"quwoquan_service/services/notification-service/internal/application"
)

const (
	UserAccountClosedInboxCollection   = "notification_user_account_closed_inbox"
	UserAccountClosedFailureCollection = "notification_user_account_closed_failures"

	userAccountClosedFailureRetention = 7 * 24 * time.Hour
)

type userAccountClosedInboxDocument struct {
	ID                       string    `bson:"_id"`
	EventDigest              string    `bson:"eventDigest"`
	DeletedAppMessages       int64     `bson:"deletedAppMessages"`
	DeletedDeliveryJobs      int64     `bson:"deletedDeliveryJobs"`
	DeletedRecipientRecords  int64     `bson:"deletedRecipientRecords"`
	AnonymizedAuditDocuments int64     `bson:"anonymizedAuditDocuments"`
	AppliedAt                time.Time `bson:"appliedAt"`
}

type userAccountClosedFailureDocument struct {
	Attempts int64 `bson:"attempts"`
}

type userAccountClosedCleanupResult struct {
	DeletedAppMessages       int64
	DeletedDeliveryJobs      int64
	DeletedRecipientRecords  int64
	AnonymizedAuditDocuments int64
}

// MongoUserAccountClosedProjection 只清理 notification-service 自有 Mongo
// 投影。事件 inbox 与全部业务变更在同一事务提交，不访问 User 数据库。
type MongoUserAccountClosedProjection struct {
	db               *mongo.Database
	appMessages      *mongo.Collection
	deliveryJobs     *mongo.Collection
	recipients       *mongo.Collection
	commandReceipts  *mongo.Collection
	deliveryOutbox   *mongo.Collection
	providerAttempts *mongo.Collection
	inbox            *mongo.Collection
	failures         *mongo.Collection
}

var _ application.UserAccountClosedProjection = (*MongoUserAccountClosedProjection)(nil)

func NewMongoUserAccountClosedProjection(
	db *mongo.Database,
) (*MongoUserAccountClosedProjection, error) {
	if db == nil {
		return nil, errors.New(
			"notification UserAccountClosed projection requires MongoDB",
		)
	}
	return &MongoUserAccountClosedProjection{
		db:               db,
		appMessages:      db.Collection("app_messages"),
		deliveryJobs:     db.Collection(notificationDeliveryJobCollection),
		recipients:       db.Collection("notification_delivery_job_recipients"),
		commandReceipts:  db.Collection(notificationDeliveryJobReceiptCollection),
		deliveryOutbox:   db.Collection(notificationDeliveryJobOutboxCollection),
		providerAttempts: db.Collection("external_provider_attempt_ledger"),
		inbox:            db.Collection(UserAccountClosedInboxCollection),
		failures:         db.Collection(UserAccountClosedFailureCollection),
	}, nil
}

func (projection *MongoUserAccountClosedProjection) EnsureIndexes(
	ctx context.Context,
) error {
	if projection == nil || projection.db == nil {
		return errors.New(
			"notification UserAccountClosed projection is not configured",
		)
	}
	if _, err := projection.inbox.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "appliedAt", Value: -1}},
			Options: options.Index().
				SetName("idx_notification_user_account_closed_applied"),
		},
	); err != nil {
		return fmt.Errorf(
			"ensure notification UserAccountClosed inbox index: %w",
			err,
		)
	}
	if _, err := projection.failures.Indexes().CreateMany(
		ctx,
		[]mongo.IndexModel{
			{
				Keys: bson.D{{Key: "eventDigest", Value: 1}},
				Options: options.Index().
					SetName("idx_notification_user_account_closed_failure_event"),
			},
			{
				Keys: bson.D{{Key: "expireAt", Value: 1}},
				Options: options.Index().
					SetName("ttl_notification_user_account_closed_failures").
					SetExpireAfterSeconds(0),
			},
		},
	); err != nil {
		return fmt.Errorf(
			"ensure notification UserAccountClosed failure indexes: %w",
			err,
		)
	}
	if _, err := projection.appMessages.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "destination.id", Value: 1}},
			Options: options.Index().
				SetName("idx_app_messages_destination_cleanup"),
		},
	); err != nil {
		return fmt.Errorf(
			"ensure notification account cleanup message index: %w",
			err,
		)
	}
	if _, err := projection.deliveryJobs.Indexes().CreateMany(
		ctx,
		[]mongo.IndexModel{
			{
				Keys: bson.D{{Key: "recipientIds", Value: 1}},
				Options: options.Index().
					SetName("idx_notification_delivery_jobs_recipient_cleanup"),
			},
			{
				Keys: bson.D{{Key: "targetPersonaId", Value: 1}},
				Options: options.Index().
					SetName("idx_notification_delivery_jobs_persona_cleanup"),
			},
		},
	); err != nil {
		return fmt.Errorf(
			"ensure notification account cleanup delivery indexes: %w",
			err,
		)
	}
	if _, err := projection.recipients.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "recipientId", Value: 1}},
			Options: options.Index().
				SetName("idx_notification_delivery_recipients_cleanup"),
		},
	); err != nil {
		return fmt.Errorf(
			"ensure notification account cleanup recipient index: %w",
			err,
		)
	}
	if _, err := projection.providerAttempts.Indexes().CreateOne(
		ctx,
		mongo.IndexModel{
			Keys: bson.D{{Key: "taskId", Value: 1}},
			Options: options.Index().
				SetName("idx_notification_provider_attempt_task_cleanup"),
		},
	); err != nil {
		return fmt.Errorf(
			"ensure notification account cleanup attempt index: %w",
			err,
		)
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) ApplyUserAccountClosed(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	if projection == nil || projection.db == nil {
		return application.UserAccountClosedProjectionResult{},
			errors.New(
				"notification UserAccountClosed projection is not configured",
			)
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedProjectionResult{}, err
	}
	if existing, found, err := projection.loadInbox(ctx, event.EventID); err != nil {
		return application.UserAccountClosedProjectionResult{}, err
	} else if found {
		return replayResultForUserAccountClosed(existing, event)
	}

	session, err := projection.db.Client().StartSession()
	if err != nil {
		return application.UserAccountClosedProjectionResult{},
			fmt.Errorf(
				"start notification UserAccountClosed transaction: %w",
				err,
			)
	}
	defer session.EndSession(ctx)

	result := application.UserAccountClosedProjectionResult{}
	_, err = session.WithTransaction(
		ctx,
		func(txCtx context.Context) (any, error) {
			existing, found, loadErr := projection.loadInbox(
				txCtx,
				event.EventID,
			)
			if loadErr != nil {
				return nil, loadErr
			}
			if found {
				replayed, replayErr := replayResultForUserAccountClosed(
					existing,
					event,
				)
				result = replayed
				return nil, replayErr
			}
			cleanup, cleanupErr := projection.cleanupClosedSubjects(
				txCtx,
				event,
			)
			if cleanupErr != nil {
				return nil, cleanupErr
			}
			_, insertErr := projection.inbox.InsertOne(
				txCtx,
				userAccountClosedInboxDocument{
					ID:                       event.EventID,
					EventDigest:              event.Digest(),
					DeletedAppMessages:       cleanup.DeletedAppMessages,
					DeletedDeliveryJobs:      cleanup.DeletedDeliveryJobs,
					DeletedRecipientRecords:  cleanup.DeletedRecipientRecords,
					AnonymizedAuditDocuments: cleanup.AnonymizedAuditDocuments,
					AppliedAt:                time.Now().UTC(),
				},
			)
			return nil, insertErr
		},
	)
	if err == nil {
		return result, nil
	}
	if mongo.IsDuplicateKeyError(err) {
		existing, found, loadErr := projection.loadInbox(
			ctx,
			event.EventID,
		)
		if loadErr != nil {
			return application.UserAccountClosedProjectionResult{}, loadErr
		}
		if found {
			return replayResultForUserAccountClosed(existing, event)
		}
	}
	return application.UserAccountClosedProjectionResult{},
		fmt.Errorf("apply notification UserAccountClosed cleanup: %w", err)
}

func (projection *MongoUserAccountClosedProjection) cleanupClosedSubjects(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (userAccountClosedCleanupResult, error) {
	subjects := event.SubjectIDs()
	messageFilter := bson.M{"$or": bson.A{
		bson.M{"userId": bson.M{"$in": subjects}},
		bson.M{"destination.id": bson.M{"$in": subjects}},
	}}
	messageIDs, err := collectStringDocumentIDs(
		ctx,
		projection.appMessages,
		messageFilter,
	)
	if err != nil {
		return userAccountClosedCleanupResult{}, err
	}

	jobClauses := bson.A{
		bson.M{"recipientIds": bson.M{"$in": subjects}},
		bson.M{"destinationRef": bson.M{"$in": subjects}},
		bson.M{"targetPersonaId": bson.M{"$in": subjects}},
	}
	if len(messageIDs) > 0 {
		jobClauses = append(
			jobClauses,
			bson.M{"aggregateId": bson.M{"$in": messageIDs}},
			bson.M{"notificationId": bson.M{"$in": messageIDs}},
		)
	}
	jobFilter := bson.M{"$or": jobClauses}
	jobIDs, err := collectStringDocumentIDs(
		ctx,
		projection.deliveryJobs,
		jobFilter,
	)
	if err != nil {
		return userAccountClosedCleanupResult{}, err
	}

	anonymized, err := projection.anonymizeDeliveryAudit(
		ctx,
		event,
		jobIDs,
		messageIDs,
	)
	if err != nil {
		return userAccountClosedCleanupResult{}, err
	}
	messageResult, err := projection.appMessages.DeleteMany(
		ctx,
		messageFilter,
	)
	if err != nil {
		return userAccountClosedCleanupResult{},
			fmt.Errorf("delete closed-account app messages: %w", err)
	}
	var deletedJobs int64
	if len(jobIDs) > 0 {
		jobResult, deleteErr := projection.deliveryJobs.DeleteMany(
			ctx,
			bson.M{"_id": bson.M{"$in": jobIDs}},
		)
		if deleteErr != nil {
			return userAccountClosedCleanupResult{},
				fmt.Errorf(
					"delete closed-account notification delivery jobs: %w",
					deleteErr,
				)
		}
		deletedJobs = jobResult.DeletedCount
	}

	recipientClauses := bson.A{
		bson.M{"recipientId": bson.M{"$in": subjects}},
	}
	if len(jobIDs) > 0 {
		recipientClauses = append(
			recipientClauses,
			bson.M{"notificationId": bson.M{"$in": jobIDs}},
		)
	}
	recipientResult, err := projection.recipients.DeleteMany(
		ctx,
		bson.M{"$or": recipientClauses},
	)
	if err != nil {
		return userAccountClosedCleanupResult{},
			fmt.Errorf(
				"delete closed-account delivery recipient projection: %w",
				err,
			)
	}
	return userAccountClosedCleanupResult{
		DeletedAppMessages:       messageResult.DeletedCount,
		DeletedDeliveryJobs:      deletedJobs,
		DeletedRecipientRecords:  recipientResult.DeletedCount,
		AnonymizedAuditDocuments: anonymized,
	}, nil
}

func (projection *MongoUserAccountClosedProjection) loadInbox(
	ctx context.Context,
	eventID string,
) (userAccountClosedInboxDocument, bool, error) {
	var document userAccountClosedInboxDocument
	err := projection.inbox.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(eventID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return userAccountClosedInboxDocument{}, false, nil
	}
	if err != nil {
		return userAccountClosedInboxDocument{}, false,
			fmt.Errorf(
				"read notification UserAccountClosed inbox: %w",
				err,
			)
	}
	return document, true, nil
}

func replayResultForUserAccountClosed(
	document userAccountClosedInboxDocument,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedProjectionResult, error) {
	if document.EventDigest != event.Digest() {
		return application.UserAccountClosedProjectionResult{},
			application.ErrUserAccountClosedEventIDConflict
	}
	return application.UserAccountClosedProjectionResult{Replayed: true}, nil
}

func collectStringDocumentIDs(
	ctx context.Context,
	collection *mongo.Collection,
	filter bson.M,
) ([]string, error) {
	cursor, err := collection.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{"_id": 1}),
	)
	if err != nil {
		return nil, fmt.Errorf(
			"scan %s for account cleanup: %w",
			collection.Name(),
			err,
		)
	}
	defer cursor.Close(ctx)
	var documents []struct {
		ID string `bson:"_id"`
	}
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, fmt.Errorf(
			"decode %s account cleanup ids: %w",
			collection.Name(),
			err,
		)
	}
	ids := make([]string, 0, len(documents))
	for _, document := range documents {
		if strings.TrimSpace(document.ID) != "" {
			ids = append(ids, document.ID)
		}
	}
	return ids, nil
}
