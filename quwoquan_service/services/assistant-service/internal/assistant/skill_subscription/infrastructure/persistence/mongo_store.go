package persistence

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	skillgenerated "quwoquan_service/services/assistant-service/generated/assistant/skill_subscription"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

// MongoStore is the authoritative SkillSubscription repository. It remains
// object-local so no AssistantSession repository can mutate subscription state.
type MongoStore struct {
	coll     *mongo.Collection
	receipts *mongo.Collection
	outbox   *mongo.Collection
}

func NewMongoStore(db *mongo.Database) *MongoStore {
	return &MongoStore{
		coll:     db.Collection("skill_subscriptions"),
		receipts: db.Collection("skill_subscription_command_receipts"),
		outbox:   db.Collection("skill_subscription_outbox"),
	}
}

type commandReceiptDocument struct {
	ID            string                       `bson:"_id"`
	OwnerID       string                       `bson:"ownerId"`
	CommandID     string                       `bson:"commandId"`
	CommandKind   string                       `bson:"commandKind"`
	CommandDigest string                       `bson:"commandDigest"`
	Result        skillmodel.SkillSubscription `bson:"result"`
	CreatedAt     time.Time                    `bson:"createdAt"`
}

type outboxDocument struct {
	ID               string                       `bson:"_id"`
	EventType        string                       `bson:"eventType"`
	SubscriptionID   string                       `bson:"subscriptionId"`
	AggregateVersion int64                        `bson:"aggregateVersion"`
	Payload          skillmodel.SkillSubscription `bson:"payload"`
	OccurredAt       time.Time                    `bson:"occurredAt"`
	PublishedAt      *time.Time                   `bson:"publishedAt,omitempty"`
	ClaimOwner       string                       `bson:"claimOwner,omitempty"`
	ClaimUntil       *time.Time                   `bson:"claimUntil,omitempty"`
	NextAttemptAt    *time.Time                   `bson:"nextAttemptAt,omitempty"`
	AttemptCount     int                          `bson:"attemptCount,omitempty"`
	LastErrorCode    string                       `bson:"lastErrorCode,omitempty"`
}

func (s *MongoStore) EnsureIndexes(ctx context.Context) error {
	indexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "owner.ownerId", Value: 1}, {Key: "status", Value: 1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_skill_subscriptions_owner_status")},
		{Keys: bson.D{{Key: "owner.ownerId", Value: 1}, {Key: "skillId", Value: 1}, {Key: "updatedAt", Value: -1}, {Key: "_id", Value: 1}}, Options: options.Index().SetName("idx_skill_subscriptions_owner_skill")},
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_skill_subscriptions_status_updated")},
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "deliveryState.nextAttemptAt", Value: 1}, {Key: "updatedAt", Value: 1}, {Key: "_id", Value: 1}}, Options: options.Index().SetName("idx_skill_subscriptions_delivery")},
	}
	if _, err := s.coll.Indexes().CreateMany(ctx, indexes); err != nil {
		return fmt.Errorf("create skill subscription indexes: %w", err)
	}
	if _, err := s.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "ownerId", Value: 1}, {Key: "commandId", Value: 1}},
		Options: options.Index().SetName("uq_skill_subscription_command_receipt").SetUnique(true),
	}); err != nil {
		return fmt.Errorf("create skill subscription receipt index: %w", err)
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "subscriptionId", Value: 1}, {Key: "aggregateVersion", Value: 1}, {Key: "eventType", Value: 1}},
			Options: options.Index().SetName("uq_skill_subscription_outbox_version").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "publishedAt", Value: 1},
				{Key: "nextAttemptAt", Value: 1},
				{Key: "claimUntil", Value: 1},
				{Key: "occurredAt", Value: 1},
			},
			Options: options.Index().SetName("idx_skill_subscription_outbox_pending"),
		},
		{
			Keys: bson.D{
				{Key: "payload.owner.ownerId", Value: 1},
				{Key: "payload.skillId", Value: 1},
				{Key: "occurredAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_skill_subscription_outbox_activity"),
		},
	}); err != nil {
		return fmt.Errorf("create skill subscription outbox indexes: %w", err)
	}
	return nil
}

func (s *MongoStore) GetSkillSubscriptionCommandResult(
	ctx context.Context,
	ownerID string,
	commandID string,
	commandKind string,
	commandDigest string,
) (skillmodel.SkillSubscription, bool, error) {
	receipt, found, err := s.readReceipt(ctx, ownerID, commandID)
	if err != nil || !found {
		return skillmodel.SkillSubscription{}, false, err
	}
	if receipt.CommandKind != strings.TrimSpace(commandKind) ||
		receipt.CommandDigest != strings.TrimSpace(commandDigest) {
		return skillmodel.SkillSubscription{}, false, skillmodel.ErrIdempotencyConflict
	}
	return receipt.Result, true, nil
}

func (s *MongoStore) CreateSkillSubscription(
	ctx context.Context,
	commandID string,
	commandDigest string,
	subscription skillmodel.SkillSubscription,
) (skillmodel.SkillSubscription, bool, error) {
	commandID = strings.TrimSpace(commandID)
	commandDigest = strings.TrimSpace(commandDigest)
	if commandID == "" || commandDigest == "" {
		return skillmodel.SkillSubscription{}, false, skillmodel.ErrIdempotencyConflict
	}
	subscription.Version = 1
	session, err := s.coll.Database().Client().StartSession()
	if err != nil {
		return skillmodel.SkillSubscription{}, false, unavailable("start create transaction", err)
	}
	defer session.EndSession(ctx)
	stored := skillmodel.SkillSubscription{}
	replayed := false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		receipt, found, readErr := s.readReceipt(txCtx, subscription.Owner.OwnerID, commandID)
		if readErr != nil {
			return nil, readErr
		}
		if found {
			if receipt.CommandKind != "create" || receipt.CommandDigest != commandDigest {
				return nil, skillmodel.ErrIdempotencyConflict
			}
			stored = receipt.Result
			replayed = true
			return nil, nil
		}
		if _, insertErr := s.coll.InsertOne(txCtx, subscription); insertErr != nil {
			return nil, insertErr
		}
		stored = subscription
		if insertErr := s.insertReceipt(txCtx, commandID, commandDigest, "create", stored); insertErr != nil {
			return nil, insertErr
		}
		return nil, s.insertOutbox(txCtx, skillmodel.EventCreated, stored, stored.CreatedAt)
	})
	if err != nil {
		if errors.Is(err, skillmodel.ErrIdempotencyConflict) {
			return skillmodel.SkillSubscription{}, false, err
		}
		return skillmodel.SkillSubscription{}, false, unavailable("commit create transaction", err)
	}
	return stored, replayed, nil
}

func (s *MongoStore) GetSkillSubscription(ctx context.Context, userID, subscriptionID string) (skillmodel.SkillSubscription, error) {
	var item skillmodel.SkillSubscription
	err := s.coll.FindOne(ctx, bson.M{"_id": subscriptionID, "owner.ownerId": userID}).Decode(&item)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return skillmodel.SkillSubscription{}, skillmodel.ErrNotFound
	}
	if err != nil {
		return skillmodel.SkillSubscription{}, unavailable("get subscription", err)
	}
	return item, nil
}

func (s *MongoStore) ListSkillSubscriptions(ctx context.Context, userID, status string, limit int) ([]skillmodel.SkillSubscription, error) {
	filter := bson.M{}
	if userID != "" {
		filter["owner.ownerId"] = userID
	}
	if status != "" {
		filter["status"] = status
	} else {
		filter["status"] = bson.M{"$ne": skillmodel.SkillSubscriptionStatusArchived}
	}
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	cur, err := s.coll.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "updatedAt", Value: -1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, skillgenerated.AppErrorFromSubscriptionStorageUnavailable("read skill subscription: " + err.Error())
	}
	defer cur.Close(ctx)
	items := []skillmodel.SkillSubscription{}
	if err := cur.All(ctx, &items); err != nil {
		return nil, skillgenerated.AppErrorFromSubscriptionStorageUnavailable("decode skill subscription: " + err.Error())
	}
	return items, nil
}

func (s *MongoStore) ListSkillSubscriptionsBySkill(
	ctx context.Context,
	ownerID string,
	skillID string,
	createdBefore time.Time,
	limit int,
) ([]skillmodel.SkillSubscription, error) {
	ownerID = strings.TrimSpace(ownerID)
	skillID = strings.TrimSpace(skillID)
	createdBefore = createdBefore.UTC()
	if ownerID == "" || skillID == "" || createdBefore.IsZero() {
		return nil, skillmodel.ErrInvalidArgument
	}
	if limit <= 0 || limit > 1001 {
		limit = 1001
	}
	cursor, err := s.coll.Find(
		ctx,
		bson.M{
			"owner.ownerId": ownerID,
			"skillId":       skillID,
			"status":        bson.M{"$ne": skillmodel.SkillSubscriptionStatusArchived},
			"createdAt":     bson.M{"$lte": createdBefore},
		},
		options.Find().
			SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, unavailable("list subscriptions by skill", err)
	}
	defer cursor.Close(ctx)
	items := []skillmodel.SkillSubscription{}
	if err := cursor.All(ctx, &items); err != nil {
		return nil, unavailable("decode subscriptions by skill", err)
	}
	return items, nil
}

func (s *MongoStore) ListSkillSubscriptionActivities(
	ctx context.Context,
	ownerID string,
	skillID string,
	limit int,
) ([]skillmodel.ActivityEvent, error) {
	ownerID = strings.TrimSpace(ownerID)
	skillID = strings.TrimSpace(skillID)
	if ownerID == "" || skillID == "" {
		return nil, skillmodel.ErrInvalidArgument
	}
	if limit <= 0 || limit > 100 {
		limit = 100
	}
	cursor, err := s.outbox.Find(
		ctx,
		bson.M{
			"payload.owner.ownerId": ownerID,
			"payload.skillId":       skillID,
		},
		options.Find().
			SetSort(bson.D{{Key: "occurredAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, unavailable("list subscription activity", err)
	}
	defer cursor.Close(ctx)
	documents := []outboxDocument{}
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, unavailable("decode subscription activity", err)
	}
	events := make([]skillmodel.ActivityEvent, 0, len(documents))
	for _, document := range documents {
		if document.Payload.Owner.OwnerID != ownerID || document.Payload.SkillID != skillID {
			return nil, unavailable(
				"validate subscription activity",
				errors.New("stored subscription event violates owner boundary"),
			)
		}
		events = append(events, skillmodel.ActivityEvent{
			EventID:        document.ID,
			EventType:      document.EventType,
			SubscriptionID: document.SubscriptionID,
			OwnerID:        ownerID,
			SkillID:        skillID,
			Status:         document.Payload.Status,
			Version:        document.AggregateVersion,
			FailureCode:    document.Payload.DeliveryState.LastErrorCode,
			OccurredAt:     document.OccurredAt.UTC(),
		})
	}
	return events, nil
}

func (s *MongoStore) ListActiveSkillSubscriptionsForDelivery(
	ctx context.Context,
	dueAt time.Time,
	limit int,
) ([]skillmodel.SkillSubscription, error) {
	if limit <= 0 || limit > 1000 {
		limit = 1000
	}
	cursor, err := s.coll.Find(
		ctx,
		bson.M{
			"status": skillmodel.SkillSubscriptionStatusActive,
			"$or": []bson.M{
				{"deliveryState.nextAttemptAt": bson.M{"$exists": false}},
				{"deliveryState.nextAttemptAt": nil},
				{"deliveryState.nextAttemptAt": bson.M{"$lte": dueAt.UTC()}},
			},
		},
		options.Find().
			SetSort(bson.D{
				{Key: "deliveryState.nextAttemptAt", Value: 1},
				{Key: "updatedAt", Value: 1},
				{Key: "_id", Value: 1},
			}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, skillgenerated.AppErrorFromSubscriptionStorageUnavailable(err.Error())
	}
	defer cursor.Close(ctx)
	items := []skillmodel.SkillSubscription{}
	if err := cursor.All(ctx, &items); err != nil {
		return nil, skillgenerated.AppErrorFromSubscriptionStorageUnavailable(err.Error())
	}
	return items, nil
}

// UpdateSkillSubscriptionStatus 是收敛的 set 语义：目标状态已满足时 no-op
// 返回存量（不推进 updatedAt、不制造伪变更）。
func (s *MongoStore) UpdateSkillSubscriptionStatus(
	ctx context.Context,
	userID string,
	subscriptionID string,
	status string,
	nextAttemptAt *time.Time,
	updatedAt time.Time,
	commandID string,
	commandDigest string,
) (skillmodel.SkillSubscription, bool, error) {
	userID = strings.TrimSpace(userID)
	subscriptionID = strings.TrimSpace(subscriptionID)
	status = strings.TrimSpace(status)
	commandID = strings.TrimSpace(commandID)
	commandDigest = strings.TrimSpace(commandDigest)
	if commandID == "" || commandDigest == "" {
		return skillmodel.SkillSubscription{}, false, skillmodel.ErrIdempotencyConflict
	}
	session, err := s.coll.Database().Client().StartSession()
	if err != nil {
		return skillmodel.SkillSubscription{}, false, unavailable("start status transaction", err)
	}
	defer session.EndSession(ctx)
	stored := skillmodel.SkillSubscription{}
	replayed := false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		receipt, found, readErr := s.readReceipt(txCtx, userID, commandID)
		if readErr != nil {
			return nil, readErr
		}
		if found {
			if receipt.CommandKind != "update_status" || receipt.CommandDigest != commandDigest {
				return nil, skillmodel.ErrIdempotencyConflict
			}
			stored = receipt.Result
			replayed = true
			return nil, nil
		}
		var current skillmodel.SkillSubscription
		if readErr := s.coll.FindOne(txCtx, bson.M{
			"_id": subscriptionID, "owner.ownerId": userID,
		}).Decode(&current); readErr != nil {
			if errors.Is(readErr, mongo.ErrNoDocuments) {
				return nil, skillmodel.ErrNotFound
			}
			return nil, readErr
		}
		if transitionErr := skillmodel.ValidateTransition(current.Status, status); transitionErr != nil {
			return nil, transitionErr
		}
		stored = current
		if current.Status != status {
			set := bson.M{"status": status, "updatedAt": updatedAt.UTC()}
			unset := bson.M{}
			if status != skillmodel.SkillSubscriptionStatusActive {
				set["deliveryState.consecutiveFailures"] = 0
				unset["deliveryState.pendingDeliveryId"] = ""
				unset["deliveryState.lastErrorCode"] = ""
				unset["deliveryState.nextAttemptAt"] = ""
			} else if nextAttemptAt != nil {
				set["deliveryState.nextAttemptAt"] = nextAttemptAt.UTC()
			}
			update := bson.M{"$set": set, "$inc": bson.M{"version": 1}}
			if len(unset) != 0 {
				update["$unset"] = unset
			}
			updateResult := s.coll.FindOneAndUpdate(
				txCtx,
				bson.M{"_id": subscriptionID, "owner.ownerId": userID, "version": current.Version},
				update,
				options.FindOneAndUpdate().SetReturnDocument(options.After),
			)
			var updated skillmodel.SkillSubscription
			if updateErr := updateResult.Decode(&updated); updateErr != nil {
				if errors.Is(updateErr, mongo.ErrNoDocuments) {
					return nil, skillmodel.ErrVersionConflict
				}
				return nil, updateErr
			}
			stored = updated
			if outboxErr := s.insertOutbox(txCtx, skillmodel.EventStatusChanged, stored, stored.UpdatedAt); outboxErr != nil {
				return nil, outboxErr
			}
		}
		return nil, s.insertReceipt(txCtx, commandID, commandDigest, "update_status", stored)
	})
	if err != nil {
		switch {
		case errors.Is(err, skillmodel.ErrIdempotencyConflict),
			errors.Is(err, skillmodel.ErrInvalidTransition),
			errors.Is(err, skillmodel.ErrVersionConflict):
			return skillmodel.SkillSubscription{}, false, err
		case errors.Is(err, skillmodel.ErrNotFound):
			return skillmodel.SkillSubscription{}, false, err
		default:
			return skillmodel.SkillSubscription{}, false, unavailable("commit status transaction", err)
		}
	}
	return stored, replayed, nil
}

func (s *MongoStore) BeginSkillSubscriptionDelivery(
	ctx context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	attemptedAt time.Time,
) (skillmodel.SkillSubscription, bool, error) {
	var item skillmodel.SkillSubscription
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{
			"_id":           subscriptionID,
			"owner.ownerId": userID,
			"status":        skillmodel.SkillSubscriptionStatusActive,
			"$or": []bson.M{
				{"deliveryState.pendingDeliveryId": bson.M{"$exists": false}},
				{"deliveryState.pendingDeliveryId": ""},
				{"deliveryState.pendingDeliveryId": deliveryID},
			},
		},
		bson.M{
			"$set": bson.M{
				"deliveryState.pendingDeliveryId": deliveryID,
				"deliveryState.lastAttemptAt":     attemptedAt.UTC(),
				"updatedAt":                       attemptedAt.UTC(),
			},
			"$inc": bson.M{"version": 1},
		},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&item)
	if err == nil {
		return item, true, nil
	}
	if errors.Is(err, mongo.ErrNoDocuments) {
		return skillmodel.SkillSubscription{}, false, nil
	}
	return skillmodel.SkillSubscription{}, false, skillgenerated.AppErrorFromSubscriptionStorageUnavailable(err.Error())
}

func (s *MongoStore) CompleteSkillSubscriptionDelivery(
	ctx context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	deliveredAt time.Time,
	nextAttemptAt time.Time,
) (skillmodel.SkillSubscription, error) {
	deliveredAt = deliveredAt.UTC()
	session, err := s.coll.Database().Client().StartSession()
	if err != nil {
		return skillmodel.SkillSubscription{}, unavailable("start delivery completion transaction", err)
	}
	defer session.EndSession(ctx)
	var item skillmodel.SkillSubscription
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		updateErr := s.coll.FindOneAndUpdate(
			txCtx,
			bson.M{
				"_id":                             subscriptionID,
				"owner.ownerId":                   userID,
				"deliveryState.pendingDeliveryId": deliveryID,
			},
			bson.M{
				"$set": bson.M{
					"deliveryState.lastAttemptAt":       deliveredAt,
					"deliveryState.lastDeliveredAt":     deliveredAt,
					"deliveryState.nextAttemptAt":       nextAttemptAt.UTC(),
					"deliveryState.consecutiveFailures": 0,
					"updatedAt":                         deliveredAt,
				},
				"$unset": bson.M{
					"deliveryState.pendingDeliveryId": "",
					"deliveryState.lastErrorCode":     "",
				},
				"$inc": bson.M{"version": 1},
			},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&item)
		if updateErr != nil {
			return nil, updateErr
		}
		return nil, s.insertOutbox(txCtx, skillmodel.EventTriggered, item, deliveredAt)
	})
	if err != nil {
		return skillmodel.SkillSubscription{}, unavailable("commit delivery completion transaction", err)
	}
	return item, nil
}

func (s *MongoStore) RecordSkillSubscriptionDeliveryFailure(
	ctx context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	errorCode string,
	failedAt time.Time,
	nextAttemptAt time.Time,
) (skillmodel.SkillSubscription, error) {
	failedAt = failedAt.UTC()
	var item skillmodel.SkillSubscription
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{
			"_id":                             subscriptionID,
			"owner.ownerId":                   userID,
			"deliveryState.pendingDeliveryId": deliveryID,
		},
		bson.M{
			"$set": bson.M{
				"deliveryState.lastAttemptAt": failedAt,
				"deliveryState.lastErrorCode": errorCode,
				"deliveryState.nextAttemptAt": nextAttemptAt.UTC(),
				"updatedAt":                   failedAt,
			},
			"$inc": bson.M{
				"deliveryState.consecutiveFailures": 1,
				"version":                           1,
			},
		},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&item)
	if err != nil {
		return skillmodel.SkillSubscription{}, skillgenerated.AppErrorFromSubscriptionStorageUnavailable(err.Error())
	}
	return item, nil
}

func (s *MongoStore) ClearPendingSkillSubscriptionDelivery(
	ctx context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	clearedAt time.Time,
	nextAttemptAt time.Time,
) error {
	_, err := s.coll.UpdateOne(
		ctx,
		bson.M{
			"_id":                             subscriptionID,
			"owner.ownerId":                   userID,
			"deliveryState.pendingDeliveryId": deliveryID,
		},
		bson.M{
			"$set": bson.M{
				"deliveryState.consecutiveFailures": 0,
				"deliveryState.nextAttemptAt":       nextAttemptAt.UTC(),
				"updatedAt":                         clearedAt.UTC(),
			},
			"$unset": bson.M{
				"deliveryState.pendingDeliveryId": "",
				"deliveryState.lastErrorCode":     "",
			},
			"$inc": bson.M{"version": 1},
		},
	)
	if err != nil {
		return skillgenerated.AppErrorFromSubscriptionStorageUnavailable(err.Error())
	}
	return nil
}

func (s *MongoStore) readReceipt(
	ctx context.Context,
	ownerID string,
	commandID string,
) (commandReceiptDocument, bool, error) {
	var receipt commandReceiptDocument
	err := s.receipts.FindOne(ctx, bson.M{
		"ownerId":   strings.TrimSpace(ownerID),
		"commandId": strings.TrimSpace(commandID),
	}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return commandReceiptDocument{}, false, nil
	}
	if err != nil {
		return commandReceiptDocument{}, false, unavailable("read command receipt", err)
	}
	return receipt, true, nil
}

func (s *MongoStore) insertReceipt(
	ctx context.Context,
	commandID string,
	commandDigest string,
	commandKind string,
	result skillmodel.SkillSubscription,
) error {
	ownerID := strings.TrimSpace(result.Owner.OwnerID)
	commandID = strings.TrimSpace(commandID)
	identity := sha256.Sum256([]byte(ownerID + "\x00" + commandID))
	_, err := s.receipts.InsertOne(ctx, commandReceiptDocument{
		ID:            fmt.Sprintf("sha256:%x", identity),
		OwnerID:       ownerID,
		CommandID:     commandID,
		CommandKind:   strings.TrimSpace(commandKind),
		CommandDigest: strings.TrimSpace(commandDigest),
		Result:        result,
		CreatedAt:     time.Now().UTC(),
	})
	return err
}

func (s *MongoStore) insertOutbox(
	ctx context.Context,
	eventType string,
	result skillmodel.SkillSubscription,
	occurredAt time.Time,
) error {
	eventType = strings.TrimSpace(eventType)
	_, err := s.outbox.InsertOne(ctx, outboxDocument{
		ID: fmt.Sprintf(
			"%s:%d:%s",
			result.SubscriptionID,
			result.Version,
			eventType,
		),
		EventType:        eventType,
		SubscriptionID:   result.SubscriptionID,
		AggregateVersion: result.Version,
		Payload:          result,
		OccurredAt:       occurredAt.UTC(),
	})
	return err
}

func unavailable(operation string, err error) error {
	return skillgenerated.AppErrorFromSubscriptionStorageUnavailable(strings.TrimSpace(operation) + ": " + err.Error())
}
