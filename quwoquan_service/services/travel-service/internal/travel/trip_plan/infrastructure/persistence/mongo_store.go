package persistence

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	revisionports "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/ports"
)

const (
	planCollection     = "trip_plans"
	receiptCollection  = "trip_plan_command_receipts"
	outboxCollection   = "trip_plan_outbox"
	sequenceCollection = "trip_plan_outbox_sequences"
)

type MongoStore struct {
	plans     *mongo.Collection
	receipts  *mongo.Collection
	outbox    *mongo.Collection
	sequences *mongo.Collection
	revisions revisionports.TransactionAppender
}

func NewMongoStore(database *mongo.Database, revisions revisionports.TransactionAppender) *MongoStore {
	if database == nil || revisions == nil {
		panic("TripPlan MongoStore requires database and TripPlanRevision appender")
	}
	return &MongoStore{
		plans: database.Collection(planCollection), revisions: revisions,
		receipts: database.Collection(receiptCollection), outbox: database.Collection(outboxCollection),
		sequences: database.Collection(sequenceCollection),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.plans.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "organizerPersonaId", Value: 1}, {Key: "status", Value: 1}, {Key: "updatedAt", Value: -1}, {Key: "_id", Value: -1}},
		Options: options.Index().SetName("idx_trip_plan_organizer_status"),
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_trip_plan_command_receipts").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "publishedAt", Value: 1}, {Key: "leaseExpiresAt", Value: 1}, {Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_trip_plan_outbox_pending")},
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("uq_trip_plan_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("uq_trip_plan_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoStore) GetPlan(ctx context.Context, tripID string) (model.Plan, error) {
	var plan model.Plan
	err := store.plans.FindOne(ctx, bson.M{"_id": strings.TrimSpace(tripID)}).Decode(&plan)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Plan{}, ports.ErrNotFound
	}
	return plan, err
}

type planListCursor struct {
	UpdatedAt time.Time `json:"updatedAt"`
	TripID    string    `json:"tripId"`
}

func (store *MongoStore) ListPlans(ctx context.Context, query ports.ListQuery) (ports.PlanPage, error) {
	ownerPersonaID := strings.TrimSpace(query.OrganizerPersonaID)
	if ownerPersonaID == "" || query.Limit < 1 || query.Limit > 50 {
		return ports.PlanPage{}, model.ErrInvalidInput
	}
	filter := bson.M{"organizerPersonaId": ownerPersonaID}
	if query.Status != "" {
		filter["status"] = query.Status
	}
	if rawCursor := strings.TrimSpace(query.Cursor); rawCursor != "" {
		cursor, err := decodePlanListCursor(rawCursor)
		if err != nil {
			return ports.PlanPage{}, model.ErrInvalidInput
		}
		filter["$or"] = []bson.M{
			{"updatedAt": bson.M{"$lt": cursor.UpdatedAt.UTC()}},
			{"updatedAt": cursor.UpdatedAt.UTC(), "_id": bson.M{"$lt": cursor.TripID}},
		}
	}
	cursor, err := store.plans.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(query.Limit+1)),
	)
	if err != nil {
		return ports.PlanPage{}, err
	}
	defer cursor.Close(ctx)
	plans := make([]model.Plan, 0, query.Limit+1)
	if err := cursor.All(ctx, &plans); err != nil {
		return ports.PlanPage{}, err
	}
	nextCursor := ""
	if len(plans) > query.Limit {
		plans = plans[:query.Limit]
		last := plans[len(plans)-1]
		nextCursor, err = encodePlanListCursor(planListCursor{
			UpdatedAt: last.UpdatedAt.UTC(),
			TripID:    last.TripID,
		})
		if err != nil {
			return ports.PlanPage{}, err
		}
	}
	return ports.PlanPage{Plans: plans, NextCursor: nextCursor}, nil
}

func encodePlanListCursor(cursor planListCursor) (string, error) {
	if cursor.UpdatedAt.IsZero() || strings.TrimSpace(cursor.TripID) == "" {
		return "", model.ErrInvalidInput
	}
	raw, err := json.Marshal(cursor)
	if err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(raw), nil
}

func decodePlanListCursor(value string) (planListCursor, error) {
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(value))
	if err != nil {
		return planListCursor{}, err
	}
	var cursor planListCursor
	if err := json.Unmarshal(raw, &cursor); err != nil {
		return planListCursor{}, err
	}
	if cursor.UpdatedAt.IsZero() || strings.TrimSpace(cursor.TripID) == "" {
		return planListCursor{}, model.ErrInvalidInput
	}
	return cursor, nil
}

type receiptDocument struct {
	ID             string       `bson:"_id"`
	CommandDigest  string       `bson:"commandDigest"`
	TripID         string       `bson:"tripId"`
	Version        int64        `bson:"version"`
	RevisionID     string       `bson:"revisionId"`
	RevisionNumber int64        `bson:"revisionNumber"`
	Status         model.Status `bson:"status"`
	ExpiresAt      time.Time    `bson:"expiresAt"`
}

func (document receiptDocument) receipt() ports.CommandReceipt {
	return ports.CommandReceipt{
		IdempotencyKey: document.ID,
		CommandDigest:  document.CommandDigest,
		ExpiresAt:      document.ExpiresAt,
		Result: ports.CommandResult{
			TripID: document.TripID, Version: document.Version,
			CurrentRevisionID: document.RevisionID, CurrentRevisionNumber: document.RevisionNumber,
			Status: document.Status,
		},
	}
}

func (store *MongoStore) FindReceipt(ctx context.Context, key string) (ports.CommandReceipt, bool, error) {
	var document receiptDocument
	err := store.receipts.FindOne(ctx, bson.M{"_id": strings.TrimSpace(key)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.CommandReceipt{}, false, nil
	}
	if err != nil {
		return ports.CommandReceipt{}, false, err
	}
	return document.receipt(), true, nil
}

func (store *MongoStore) Commit(ctx context.Context, commit ports.Commit) error {
	if err := validateCommit(commit); err != nil {
		return err
	}
	if receipt, found, err := store.FindReceipt(ctx, commit.Receipt.IdempotencyKey); err != nil {
		return err
	} else if found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return nil
	}
	session, err := store.plans.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if receipt, found, findErr := store.FindReceipt(txCtx, commit.Receipt.IdempotencyKey); findErr != nil {
			return nil, findErr
		} else if found {
			if receipt.CommandDigest != commit.Receipt.CommandDigest {
				return nil, ports.ErrIdempotencyConflict
			}
			return nil, nil
		}
		if err := store.persistPlan(txCtx, commit); err != nil {
			return nil, err
		}
		if appendErr := store.revisions.AppendInTripPlanTransaction(txCtx, commit.Revision); appendErr != nil {
			if errors.Is(appendErr, revisionports.ErrConflict) {
				return nil, ports.ErrCommitConflict
			}
			return nil, appendErr
		}
		if err := store.appendOutbox(txCtx, commit); err != nil {
			return nil, err
		}
		receipt := receiptDocument{
			ID: commit.Receipt.IdempotencyKey, CommandDigest: commit.Receipt.CommandDigest,
			TripID: commit.Plan.TripID, Version: commit.Plan.Version,
			RevisionID: commit.Plan.CurrentRevisionID, RevisionNumber: commit.Plan.CurrentRevisionNumber,
			Status: commit.Plan.Status, ExpiresAt: commit.Receipt.ExpiresAt.UTC(),
		}
		if _, insertErr := store.receipts.InsertOne(txCtx, receipt); insertErr != nil {
			if mongo.IsDuplicateKeyError(insertErr) {
				return nil, ports.ErrIdempotencyConflict
			}
			return nil, insertErr
		}
		return nil, nil
	})
	return err
}

func (store *MongoStore) persistPlan(ctx context.Context, commit ports.Commit) error {
	if commit.ExpectedPlanVersion == 0 {
		if _, err := store.plans.InsertOne(ctx, commit.Plan); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return ports.ErrCommitConflict
			}
			return err
		}
		return nil
	}
	result, err := store.plans.ReplaceOne(ctx, bson.M{
		"_id": commit.Plan.TripID, "version": commit.ExpectedPlanVersion,
		"currentRevisionNumber": commit.ExpectedRevisionNumber,
	}, commit.Plan)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return ports.ErrCommitConflict
	}
	return nil
}

func (store *MongoStore) appendOutbox(ctx context.Context, commit ports.Commit) error {
	if err := store.appendOutboxEvent(ctx, commit.Event); err != nil {
		return err
	}
	return store.appendOutboxEvent(ctx, commit.RevisionEvent)
}

func (store *MongoStore) appendOutboxEvent(
	ctx context.Context,
	event ports.OutboxEvent,
) error {
	var sequence struct {
		Value int64 `bson:"value"`
	}
	if err := store.sequences.FindOneAndUpdate(
		ctx,
		bson.M{"_id": "TripPlan"},
		bson.M{"$inc": bson.M{"value": int64(1)}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&sequence); err != nil {
		return err
	}
	_, err := store.outbox.InsertOne(ctx, bson.M{
		"_id": event.EventID, "outboxSequence": sequence.Value,
		"eventType": event.EventType, "aggregateId": event.AggregateID,
		"aggregateVersion": event.AggregateVersion, "payloadJson": event.Payload,
		"occurredAt": event.OccurredAt.UTC(), "publishAttempts": 0,
	})
	if mongo.IsDuplicateKeyError(err) {
		return ports.ErrCommitConflict
	}
	return err
}

type outboxDocument struct {
	ID               string         `bson:"_id"`
	EventType        string         `bson:"eventType"`
	AggregateID      string         `bson:"aggregateId"`
	AggregateVersion int64          `bson:"aggregateVersion"`
	Payload          map[string]any `bson:"payloadJson"`
	OccurredAt       time.Time      `bson:"occurredAt"`
	ClaimedBy        string         `bson:"claimedBy"`
}

func (store *MongoStore) ClaimPendingOutbox(
	ctx context.Context,
	workerID string,
	now time.Time,
	lease time.Duration,
	limit int,
) ([]ports.ClaimedOutboxEvent, error) {
	workerID = strings.TrimSpace(workerID)
	if workerID == "" || now.IsZero() || lease <= 0 {
		return nil, model.ErrInvalidInput
	}
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	events := make([]ports.ClaimedOutboxEvent, 0, limit)
	for len(events) < limit {
		var document outboxDocument
		err := store.outbox.FindOneAndUpdate(
			ctx,
			bson.M{
				"publishedAt": bson.M{"$exists": false},
				"$or": []bson.M{
					{"leaseExpiresAt": bson.M{"$exists": false}},
					{"leaseExpiresAt": bson.M{"$lte": now.UTC()}},
				},
			},
			bson.M{
				"$set": bson.M{"claimedBy": workerID, "leaseExpiresAt": now.UTC().Add(lease)},
				"$inc": bson.M{"publishAttempts": 1},
			},
			options.FindOneAndUpdate().
				SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).
				SetReturnDocument(options.After),
		).Decode(&document)
		if errors.Is(err, mongo.ErrNoDocuments) {
			break
		}
		if err != nil {
			return nil, err
		}
		events = append(events, ports.ClaimedOutboxEvent{
			OutboxEvent: ports.OutboxEvent{
				EventID: document.ID, EventType: document.EventType,
				AggregateID: document.AggregateID, AggregateVersion: document.AggregateVersion,
				Payload: document.Payload, OccurredAt: document.OccurredAt,
			},
			ClaimedBy: document.ClaimedBy,
		})
	}
	return events, nil
}

func (store *MongoStore) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	workerID string,
	publishedAt time.Time,
) error {
	result, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id": strings.TrimSpace(eventID), "claimedBy": strings.TrimSpace(workerID),
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set":   bson.M{"publishedAt": publishedAt.UTC()},
			"$unset": bson.M{"claimedBy": "", "leaseExpiresAt": ""},
		},
	)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return ports.ErrCommitConflict
	}
	return nil
}

func (store *MongoStore) ReleaseOutboxClaims(
	ctx context.Context,
	workerID string,
	eventIDs []string,
) error {
	if len(eventIDs) == 0 {
		return nil
	}
	_, err := store.outbox.UpdateMany(
		ctx,
		bson.M{
			"_id": bson.M{"$in": eventIDs}, "claimedBy": strings.TrimSpace(workerID),
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{"$unset": bson.M{"claimedBy": "", "leaseExpiresAt": ""}},
	)
	return err
}

func validateCommit(commit ports.Commit) error {
	if strings.TrimSpace(commit.Plan.TripID) == "" || commit.Plan.Version <= 0 ||
		commit.Revision.Validate() != nil ||
		strings.TrimSpace(commit.Receipt.IdempotencyKey) == "" || strings.TrimSpace(commit.Receipt.CommandDigest) == "" ||
		commit.Receipt.ExpiresAt.IsZero() || strings.TrimSpace(commit.Event.EventID) == "" ||
		strings.TrimSpace(commit.Event.EventType) == "" || commit.Event.OccurredAt.IsZero() ||
		strings.TrimSpace(commit.RevisionEvent.EventID) == "" ||
		commit.RevisionEvent.EventType != "TripPlanRevisionAppended" ||
		commit.RevisionEvent.AggregateID != commit.Revision.RevisionID ||
		commit.RevisionEvent.AggregateVersion != commit.Revision.RevisionNumber ||
		commit.RevisionEvent.OccurredAt.IsZero() {
		return model.ErrInvalidInput
	}
	return nil
}

var _ ports.Store = (*MongoStore)(nil)
var _ ports.OutboxStore = (*MongoStore)(nil)
