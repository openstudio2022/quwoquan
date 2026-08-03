package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/accountrestriction"
	jobapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	deliverydomain "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

type MongoAccountLifecycle struct {
	jobs       *mongo.Collection
	recipients *mongo.Collection
	receipts   *mongo.Collection
	outbox     *mongo.Collection
}

var _ jobapplication.AccountLifecycle = (*MongoAccountLifecycle)(nil)

func NewMongoAccountLifecycle(db *mongo.Database) *MongoAccountLifecycle {
	if db == nil {
		panic("NotificationDeliveryJob account lifecycle requires MongoDB")
	}
	return &MongoAccountLifecycle{
		jobs:       db.Collection(notificationDeliveryJobCollection),
		recipients: db.Collection("notification_delivery_job_recipients"),
		receipts:   db.Collection(notificationDeliveryJobReceiptCollection),
		outbox:     db.Collection(notificationDeliveryJobOutboxCollection),
	}
}

func (lifecycle *MongoAccountLifecycle) EnsureIndexes(ctx context.Context) error {
	if lifecycle == nil || lifecycle.jobs == nil || lifecycle.recipients == nil {
		return errors.New("NotificationDeliveryJob account lifecycle is not configured")
	}
	if _, err := lifecycle.jobs.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "recipientIds", Value: 1}},
			Options: options.Index().SetName("idx_notification_delivery_jobs_recipient_cleanup"),
		},
		{
			Keys:    bson.D{{Key: "targetPersonaId", Value: 1}},
			Options: options.Index().SetName("idx_notification_delivery_jobs_persona_cleanup"),
		},
	}); err != nil {
		return fmt.Errorf("ensure NotificationDeliveryJob account indexes: %w", err)
	}
	if _, err := lifecycle.recipients.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "recipientId", Value: 1}},
		Options: options.Index().SetName("idx_notification_delivery_recipients_cleanup"),
	}); err != nil {
		return fmt.Errorf("ensure NotificationDeliveryJob recipient account index: %w", err)
	}
	return nil
}

func (lifecycle *MongoAccountLifecycle) ApplyRestriction(
	ctx context.Context,
	event accountrestriction.Event,
) (int64, error) {
	baseSet := bson.M{
		"accountRestricted":           event.Restricted(),
		"accountRestrictionVersion":   event.AccountVersion,
		"accountRestrictionUpdatedAt": event.OccurredAt.UTC(),
	}
	jobSet := bson.M{}
	for key, value := range baseSet {
		jobSet[key] = value
	}
	if event.Restricted() {
		jobSet["restrictionSuppressed"] = true
	}
	jobResult, err := lifecycle.jobs.UpdateMany(
		ctx,
		bson.M{"$or": bson.A{
			bson.M{"recipientIds": bson.M{"$in": event.SubjectIDs()}},
			bson.M{"targetPersonaId": bson.M{"$in": event.SubjectIDs()}},
		}},
		bson.M{"$set": jobSet},
	)
	if err != nil {
		return 0, fmt.Errorf("project account restriction to NotificationDeliveryJob: %w", err)
	}
	recipientResult, err := lifecycle.recipients.UpdateMany(
		ctx,
		bson.M{"recipientId": bson.M{"$in": event.SubjectIDs()}},
		bson.M{"$set": baseSet},
	)
	if err != nil {
		return 0, fmt.Errorf("project account restriction to NotificationDeliveryJob recipients: %w", err)
	}
	return jobResult.ModifiedCount + recipientResult.ModifiedCount, nil
}

func (lifecycle *MongoAccountLifecycle) CloseAccount(
	ctx context.Context,
	closure jobapplication.AccountClosure,
) (jobapplication.AccountClosureResult, error) {
	subjects := accountrestriction.NormalizeSubjects(closure.SubjectIDs)
	jobClauses := bson.A{
		bson.M{"recipientIds": bson.M{"$in": subjects}},
		bson.M{"destinationRef": bson.M{"$in": subjects}},
		bson.M{"targetPersonaId": bson.M{"$in": subjects}},
	}
	if len(closure.NotificationIDs) > 0 {
		jobClauses = append(
			jobClauses,
			bson.M{"aggregateId": bson.M{"$in": closure.NotificationIDs}},
			bson.M{"notificationId": bson.M{"$in": closure.NotificationIDs}},
		)
	}
	jobIDs, err := lifecycle.collectJobIDs(ctx, bson.M{"$or": jobClauses})
	if err != nil {
		return jobapplication.AccountClosureResult{}, err
	}
	anonymized, err := lifecycle.anonymizeAudit(
		ctx,
		closure.EventID,
		subjects,
		jobIDs,
		closure.NotificationIDs,
	)
	if err != nil {
		return jobapplication.AccountClosureResult{}, err
	}
	var deletedJobs int64
	if len(jobIDs) > 0 {
		result, deleteErr := lifecycle.jobs.DeleteMany(
			ctx,
			bson.M{"_id": bson.M{"$in": jobIDs}},
		)
		if deleteErr != nil {
			return jobapplication.AccountClosureResult{}, fmt.Errorf(
				"delete closed-account NotificationDeliveryJob: %w",
				deleteErr,
			)
		}
		deletedJobs = result.DeletedCount
	}
	recipientClauses := bson.A{bson.M{"recipientId": bson.M{"$in": subjects}}}
	if len(jobIDs) > 0 {
		recipientClauses = append(
			recipientClauses,
			bson.M{"notificationId": bson.M{"$in": jobIDs}},
		)
	}
	recipientResult, err := lifecycle.recipients.DeleteMany(
		ctx,
		bson.M{"$or": recipientClauses},
	)
	if err != nil {
		return jobapplication.AccountClosureResult{}, fmt.Errorf(
			"delete closed-account NotificationDeliveryJob recipients: %w",
			err,
		)
	}
	return jobapplication.AccountClosureResult{
		DeletedJobs:             deletedJobs,
		DeletedRecipientRecords: recipientResult.DeletedCount,
		AnonymizedAuditRecords:  anonymized,
	}, nil
}

func (lifecycle *MongoAccountLifecycle) collectJobIDs(
	ctx context.Context,
	filter bson.M,
) ([]string, error) {
	cursor, err := lifecycle.jobs.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{"_id": 1}),
	)
	if err != nil {
		return nil, fmt.Errorf("scan NotificationDeliveryJob account closure: %w", err)
	}
	defer cursor.Close(ctx)
	var documents []struct {
		ID string `bson:"_id"`
	}
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, fmt.Errorf("decode NotificationDeliveryJob account closure ids: %w", err)
	}
	ids := make([]string, 0, len(documents))
	for _, document := range documents {
		if id := strings.TrimSpace(document.ID); id != "" {
			ids = append(ids, id)
		}
	}
	return ids, nil
}

type closedAccountDeliveryJobEventDocument struct {
	ID               string            `bson:"_id"`
	AggregateID      string            `bson:"aggregateId"`
	AggregateVersion int64             `bson:"aggregateVersion"`
	EventType        string            `bson:"eventType"`
	Payload          map[string]string `bson:"payload"`
	Status           string            `bson:"status"`
}

type closedAccountDeliveryJobReceiptDocument struct {
	ID            string                                              `bson:"_id"`
	CommandDigest string                                              `bson:"commandDigest"`
	Result        deliverydomain.RecoverNotificationDeliveryJobResult `bson:"result"`
}

func (lifecycle *MongoAccountLifecycle) anonymizeAudit(
	ctx context.Context,
	eventID string,
	subjects []string,
	jobIDs []string,
	notificationIDs []string,
) (int64, error) {
	sensitiveValues := make(map[string]struct{}, len(jobIDs)+len(notificationIDs)+len(subjects))
	for _, values := range [][]string{jobIDs, notificationIDs, subjects} {
		for _, value := range values {
			if normalized := strings.TrimSpace(value); normalized != "" {
				sensitiveValues[normalized] = struct{}{}
			}
		}
	}

	var anonymized int64
	outboxClauses := bson.A{}
	if len(jobIDs) > 0 {
		outboxClauses = append(
			outboxClauses,
			bson.M{"aggregateId": bson.M{"$in": jobIDs}},
			bson.M{"payload.jobId": bson.M{"$in": jobIDs}},
		)
	}
	if len(notificationIDs) > 0 {
		outboxClauses = append(
			outboxClauses,
			bson.M{"payload.notificationId": bson.M{"$in": notificationIDs}},
		)
	}
	if len(outboxClauses) > 0 {
		cursor, err := lifecycle.outbox.Find(ctx, bson.M{"$or": outboxClauses})
		if err != nil {
			return 0, fmt.Errorf("scan closed-account NotificationDeliveryJob outbox: %w", err)
		}
		var documents []closedAccountDeliveryJobEventDocument
		if err := cursor.All(ctx, &documents); err != nil {
			_ = cursor.Close(ctx)
			return 0, fmt.Errorf("decode closed-account NotificationDeliveryJob outbox: %w", err)
		}
		_ = cursor.Close(ctx)
		for _, document := range documents {
			document.AggregateID = closedAuditValue(eventID, document.AggregateID)
			for key, value := range document.Payload {
				normalized := strings.TrimSpace(value)
				if normalized == "" {
					continue
				}
				_, direct := sensitiveValues[normalized]
				if direct || isAuditIdentityField(key) {
					document.Payload[key] = closedAuditValue(eventID, normalized)
				}
			}
			if _, err := lifecycle.outbox.ReplaceOne(ctx, bson.M{"_id": document.ID}, document); err != nil {
				return 0, fmt.Errorf("anonymize NotificationDeliveryJob outbox: %w", err)
			}
			anonymized++
		}
	}

	receiptClauses := bson.A{}
	if len(jobIDs) > 0 {
		receiptClauses = append(receiptClauses, bson.M{"result.jobId": bson.M{"$in": jobIDs}})
	}
	if len(notificationIDs) > 0 {
		receiptClauses = append(
			receiptClauses,
			bson.M{"result.notificationId": bson.M{"$in": notificationIDs}},
		)
	}
	if len(receiptClauses) > 0 {
		cursor, err := lifecycle.receipts.Find(ctx, bson.M{"$or": receiptClauses})
		if err != nil {
			return 0, fmt.Errorf("scan closed-account NotificationDeliveryJob receipts: %w", err)
		}
		var documents []closedAccountDeliveryJobReceiptDocument
		if err := cursor.All(ctx, &documents); err != nil {
			_ = cursor.Close(ctx)
			return 0, fmt.Errorf("decode closed-account NotificationDeliveryJob receipts: %w", err)
		}
		_ = cursor.Close(ctx)
		for _, document := range documents {
			document.CommandDigest = closedAuditValue(eventID, document.CommandDigest)
			document.Result.JobID = closedAuditValue(eventID, document.Result.JobID)
			document.Result.NotificationID = closedAuditValue(eventID, document.Result.NotificationID)
			if _, err := lifecycle.receipts.ReplaceOne(ctx, bson.M{"_id": document.ID}, document); err != nil {
				return 0, fmt.Errorf("anonymize NotificationDeliveryJob receipt: %w", err)
			}
			anonymized++
		}
	}
	return anonymized, nil
}

func isAuditIdentityField(field string) bool {
	switch strings.ToLower(strings.TrimSpace(field)) {
	case "accountid", "aggregateid", "callid", "dedupekey", "deliverykey",
		"destinationref", "deviceid", "endpointref", "jobid", "notificationid",
		"personaid", "recipientid", "requestid", "targetpersonaid", "userid":
		return true
	default:
		return false
	}
}

func closedAuditValue(eventID string, value string) string {
	normalized := strings.TrimSpace(value)
	if normalized == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(
		"notification-user-account-closed-audit\n" +
			strings.TrimSpace(eventID) + "\n" + normalized,
	))
	return "closed:sha256:" + hex.EncodeToString(sum[:])
}
