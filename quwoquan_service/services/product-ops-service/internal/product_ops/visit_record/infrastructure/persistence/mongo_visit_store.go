package persistence

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/application"
)

// MongoVisitStore owns VisitRecord state and actor-scoped command receipts.
// Both collections are committed in one MongoDB transaction; EventRecord and
// its batch ledger never participate in VisitRecord writes.
type MongoVisitStore struct {
	visits   *mongo.Collection
	receipts *mongo.Collection
}

func NewMongoVisitStore(db *mongo.Database) *MongoVisitStore {
	return &MongoVisitStore{
		visits:   db.Collection("visit_records"),
		receipts: db.Collection("visit_record_command_receipts"),
	}
}

func (s *MongoVisitStore) EnsureIndexes(ctx context.Context) error {
	if err := s.migrateCanonicalVisitTime(ctx); err != nil {
		return err
	}
	for _, legacyIndex := range []string{
		"idx_visit_target",
		"idx_visit_session",
		"ttl_visit_timestamp",
	} {
		if err := dropVisitIndexIfExists(ctx, s.visits, legacyIndex); err != nil {
			return fmt.Errorf("drop legacy visit index %s: %w", legacyIndex, err)
		}
	}
	if _, err := s.visits.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "targetType", Value: 1},
				{Key: "targetKey", Value: 1},
			},
			Options: options.Index().SetName("uq_visit_user_target").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "targetType", Value: 1},
				{Key: "targetKey", Value: 1},
				{Key: "occurredAt", Value: -1},
			},
			Options: options.Index().SetName("idx_visit_target_occurred_at"),
		},
		{
			Keys:    bson.D{{Key: "occurredAt", Value: 1}},
			Options: options.Index().SetName("ttl_visit_occurred_at").SetExpireAfterSeconds(180 * 24 * 60 * 60),
		},
	}); err != nil {
		return fmt.Errorf("create visit indexes: %w", err)
	}
	if _, err := s.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("idx_visit_receipts_expire").SetExpireAfterSeconds(0),
	}); err != nil {
		return fmt.Errorf("create visit receipt indexes: %w", err)
	}
	return nil
}

// migrateCanonicalVisitTime performs the one-time cutover before legacy TTL
// indexes are removed. Runtime reads never fall back to retired fields.
func (s *MongoVisitStore) migrateCanonicalVisitTime(ctx context.Context) error {
	_, err := s.visits.UpdateMany(
		ctx,
		bson.D{{Key: "occurredAt", Value: bson.D{{Key: "$exists", Value: false}}}},
		mongo.Pipeline{bson.D{{Key: "$set", Value: bson.D{{
			Key: "occurredAt",
			Value: bson.D{{
				Key:   "$ifNull",
				Value: bson.A{"$timestamp", "$$NOW"},
			}},
		}}}}},
	)
	if err != nil {
		return fmt.Errorf("migrate canonical visit time: %w", err)
	}
	_, err = s.visits.UpdateMany(ctx, bson.D{}, bson.D{{Key: "$unset", Value: bson.D{
		{Key: "lastSeenAt", Value: ""},
		{Key: "timestamp", Value: ""},
		{Key: "sessionId", Value: ""},
		{Key: "source", Value: ""},
	}}})
	if err != nil {
		return fmt.Errorf("remove legacy visit fields: %w", err)
	}
	return nil
}

func dropVisitIndexIfExists(
	ctx context.Context,
	collection *mongo.Collection,
	name string,
) error {
	if err := collection.Indexes().DropOne(ctx, name); err != nil {
		var commandError mongo.CommandError
		if errors.As(err, &commandError) &&
			(commandError.Code == 26 || commandError.Code == 27) {
			return nil
		}
		return err
	}
	return nil
}

type commandReceiptDocument struct {
	ID            string                  `bson:"_id"`
	CommandDigest string                  `bson:"commandDigest"`
	Result        application.VisitRecord `bson:"result"`
	CreatedAt     time.Time               `bson:"createdAt"`
	ExpiresAt     time.Time               `bson:"expiresAt"`
}

func (s *MongoVisitStore) CommitVisit(
	ctx context.Context,
	command application.CommitCommand,
) (application.CommandResult, error) {
	session, err := s.visits.Database().Client().StartSession()
	if err != nil {
		return application.CommandResult{}, fmt.Errorf("start visit transaction: %w", err)
	}
	defer session.EndSession(ctx)

	var result application.CommandResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		receipt, found, loadErr := s.loadReceipt(txCtx, command.ReceiptID)
		if loadErr != nil {
			return nil, loadErr
		}
		if found {
			if receipt.CommandDigest != command.CommandDigest {
				return nil, application.ErrIdempotencyConflict
			}
			result = application.CommandResult{
				VisitRecord: receipt.Result,
				Replayed:    true,
			}
			return nil, nil
		}

		now := time.Now().UTC()
		filter := bson.D{
			{Key: "userId", Value: command.Input.UserID},
			{Key: "targetType", Value: command.Input.TargetType},
			{Key: "targetKey", Value: command.Input.TargetKey},
		}
		update := bson.D{
			{Key: "$inc", Value: bson.D{{Key: "visitCount", Value: 1}}},
			{Key: "$set", Value: bson.D{{Key: "occurredAt", Value: now}}},
			{Key: "$unset", Value: bson.D{
				{Key: "lastSeenAt", Value: ""},
				{Key: "timestamp", Value: ""},
				{Key: "sessionId", Value: ""},
				{Key: "source", Value: ""},
			}},
			{Key: "$setOnInsert", Value: bson.D{
				{Key: "userId", Value: command.Input.UserID},
				{Key: "targetType", Value: command.Input.TargetType},
				{Key: "targetKey", Value: command.Input.TargetKey},
			}},
		}
		var record application.VisitRecord
		if err := s.visits.FindOneAndUpdate(
			txCtx,
			filter,
			update,
			options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
		).Decode(&record); err != nil {
			return nil, fmt.Errorf("record visit: %w", err)
		}
		if _, err := s.receipts.InsertOne(txCtx, commandReceiptDocument{
			ID:            command.ReceiptID,
			CommandDigest: command.CommandDigest,
			Result:        record,
			CreatedAt:     now,
			ExpiresAt:     command.ReceiptExpires.UTC(),
		}); err != nil {
			return nil, fmt.Errorf("store visit receipt: %w", err)
		}
		result = application.CommandResult{VisitRecord: record}
		return nil, nil
	})
	if err == nil {
		return result, nil
	}
	if errors.Is(err, application.ErrIdempotencyConflict) {
		return application.CommandResult{}, err
	}

	// Resolve an ambiguous commit or a concurrent duplicate strictly from the
	// durable receipt. This is confirmation, not a second write path.
	receipt, found, loadErr := s.loadReceipt(ctx, command.ReceiptID)
	if loadErr == nil && found {
		if receipt.CommandDigest != command.CommandDigest {
			return application.CommandResult{}, application.ErrIdempotencyConflict
		}
		return application.CommandResult{
			VisitRecord: receipt.Result,
			Replayed:    true,
		}, nil
	}
	return application.CommandResult{}, fmt.Errorf("commit visit: %w", err)
}

func (s *MongoVisitStore) loadReceipt(
	ctx context.Context,
	receiptID string,
) (commandReceiptDocument, bool, error) {
	var receipt commandReceiptDocument
	err := s.receipts.FindOne(ctx, bson.D{{Key: "_id", Value: receiptID}}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return commandReceiptDocument{}, false, nil
	}
	if err != nil {
		return commandReceiptDocument{}, false, err
	}
	return receipt, true, nil
}

// GetVisit is an object-local evidence reader used by real-store integration
// tests. Public queries use GetVisitStats and never expose actor identifiers.
func (s *MongoVisitStore) GetVisit(
	ctx context.Context,
	userID, targetType, targetKey string,
) (application.VisitRecord, bool, error) {
	var record application.VisitRecord
	err := s.visits.FindOne(ctx, bson.D{
		{Key: "userId", Value: strings.TrimSpace(userID)},
		{Key: "targetType", Value: strings.TrimSpace(targetType)},
		{Key: "targetKey", Value: strings.TrimSpace(targetKey)},
	}).Decode(&record)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return application.VisitRecord{}, false, nil
	}
	if err != nil {
		return application.VisitRecord{}, false, fmt.Errorf("get visit: %w", err)
	}
	return record, true, nil
}

func (s *MongoVisitStore) GetVisitStats(
	ctx context.Context,
	query application.VisitStatsQuery,
) (application.VisitStats, error) {
	filter := bson.D{}
	if value := strings.TrimSpace(query.TargetType); value != "" {
		filter = append(filter, bson.E{Key: "targetType", Value: value})
	}
	if value := strings.TrimSpace(query.TargetKey); value != "" {
		filter = append(filter, bson.E{Key: "targetKey", Value: value})
	}
	cursor, err := s.visits.Find(ctx, filter)
	if err != nil {
		return application.VisitStats{}, fmt.Errorf("find visit stats: %w", err)
	}
	defer cursor.Close(ctx)
	out := application.VisitStats{Items: []application.VisitRecord{}}
	for cursor.Next(ctx) {
		var item application.VisitRecord
		if err := cursor.Decode(&item); err != nil {
			return application.VisitStats{}, err
		}
		out.TotalVisits += item.VisitCount
		out.Items = append(out.Items, item)
	}
	if err := cursor.Err(); err != nil {
		return application.VisitStats{}, err
	}
	sort.Slice(out.Items, func(i, j int) bool {
		if out.Items[i].VisitCount == out.Items[j].VisitCount {
			return out.Items[i].OccurredAt.After(out.Items[j].OccurredAt)
		}
		return out.Items[i].VisitCount > out.Items[j].VisitCount
	})
	return out, nil
}

var _ application.Store = (*MongoVisitStore)(nil)
