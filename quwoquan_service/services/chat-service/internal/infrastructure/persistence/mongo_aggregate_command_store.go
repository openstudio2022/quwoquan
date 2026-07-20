package persistence

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/chat-service/internal/application"
)

// ErrAggregateIdempotencyConflict 表示同一 Idempotency-Key 被复用于不同命令。
var ErrAggregateIdempotencyConflict = errors.New("idempotency key was reused with a different chat command")

// generateStateID 供 upsert-on-insert 场景生成 ConversationUserState 主键。
func generateStateID() string {
	raw := make([]byte, 12)
	_, _ = rand.Read(raw)
	return hex.EncodeToString(raw)
}

const aggregateOutboxSequenceCollection = "chat_aggregate_outbox_sequences"

// MongoAggregateCommandStore 是 Conversation / ConversationMembership /
// ConversationUserState 三聚合共享实现的命令回执 + 事务 outbox 存储；
// 每个聚合以自己的集合名实例化一份，state 写入由调用方在同一事务闭包完成。
type MongoAggregateCommandStore struct {
	db          *mongo.Database
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	sequences   *mongo.Collection
	sequenceKey string
}

var _ application.AggregateCommandStore = (*MongoAggregateCommandStore)(nil)
var _ application.AggregateOutboxSource = (*MongoAggregateCommandStore)(nil)

func NewMongoAggregateCommandStore(
	db *mongo.Database,
	receiptCollection string,
	outboxCollection string,
) *MongoAggregateCommandStore {
	return &MongoAggregateCommandStore{
		db:          db,
		receipts:    db.Collection(receiptCollection),
		outbox:      db.Collection(outboxCollection),
		sequences:   db.Collection(aggregateOutboxSequenceCollection),
		sequenceKey: outboxCollection,
	}
}

type aggregateCommandReceiptDocument struct {
	ID            string    `bson:"_id"`
	CommandName   string    `bson:"commandName"`
	CommandDigest string    `bson:"commandDigest"`
	AggregateID   string    `bson:"aggregateId"`
	ResultJSON    []byte    `bson:"resultJson"`
	CreatedAt     time.Time `bson:"createdAt"`
	ExpiresAt     time.Time `bson:"expiresAt"`
}

type aggregateOutboxDocument struct {
	ID             string         `bson:"_id"`
	OutboxSequence int64          `bson:"outboxSequence"`
	AggregateID    string         `bson:"aggregateId"`
	EventType      string         `bson:"eventType"`
	ConversationID string         `bson:"conversationId"`
	ActorID        string         `bson:"actorId"`
	Payload        map[string]any `bson:"payload"`
	Status         string         `bson:"status"`
	CreatedAt      time.Time      `bson:"createdAt"`
	DispatchedAt   *time.Time     `bson:"dispatchedAt,omitempty"`
}

func (s *MongoAggregateCommandStore) EnsureIndexes(ctx context.Context) error {
	// Mongo 多文档事务不能隐式创建集合：receipts/outbox/sequences 必须在
	// 启动期显式存在，命令事务内的首次写入才不会失败。
	for _, name := range []string{
		s.receipts.Name(), s.outbox.Name(), aggregateOutboxSequenceCollection,
	} {
		if err := ensureCollectionExists(ctx, s.db, name); err != nil {
			return err
		}
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_" + s.receipts.Name() + "_expire").SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return fmt.Errorf("ensure %s indexes: %w", s.receipts.Name(), err)
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("uq_" + s.outbox.Name() + "_sequence").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "createdAt", Value: 1}},
			Options: options.Index().SetName("idx_" + s.outbox.Name() + "_pending"),
		},
	}); err != nil {
		return fmt.Errorf("ensure %s indexes: %w", s.outbox.Name(), err)
	}
	return nil
}

func ensureCollectionExists(ctx context.Context, db *mongo.Database, name string) error {
	err := db.CreateCollection(ctx, name)
	if err == nil {
		return nil
	}
	var commandError mongo.CommandError
	if errors.As(err, &commandError) && commandError.Name == "NamespaceExists" {
		return nil
	}
	return fmt.Errorf("ensure collection %s: %w", name, err)
}

func (s *MongoAggregateCommandStore) FindAggregateCommandReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) ([]byte, bool, error) {
	var document aggregateCommandReceiptDocument
	err := s.receipts.FindOne(ctx, bson.M{"_id": strings.TrimSpace(idempotencyKey)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("find %s receipt: %w", s.receipts.Name(), err)
	}
	if !document.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.receipts.DeleteOne(ctx, bson.M{"_id": document.ID}); err != nil {
			return nil, false, err
		}
		return nil, false, nil
	}
	if document.CommandName != commandName || document.CommandDigest != commandDigest {
		return nil, false, ErrAggregateIdempotencyConflict
	}
	return document.ResultJSON, true, nil
}

// CommitAggregateCommand 必须运行在调用方事务上下文内；state 写入与本次
// receipt/outbox 落盘属于同一个 Mongo 事务。
func (s *MongoAggregateCommandStore) CommitAggregateCommand(
	ctx context.Context,
	receipt application.AggregateCommandReceipt,
	events []application.AggregateOutboxEvent,
) error {
	if strings.TrimSpace(receipt.IdempotencyKey) == "" ||
		strings.TrimSpace(receipt.CommandName) == "" ||
		strings.TrimSpace(receipt.CommandDigest) == "" {
		return errors.New("aggregate command receipt is incomplete")
	}
	expiresAt := receipt.ExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	if _, err := s.receipts.InsertOne(ctx, aggregateCommandReceiptDocument{
		ID:            strings.TrimSpace(receipt.IdempotencyKey),
		CommandName:   receipt.CommandName,
		CommandDigest: receipt.CommandDigest,
		AggregateID:   receipt.AggregateID,
		ResultJSON:    receipt.ResultJSON,
		CreatedAt:     time.Now().UTC(),
		ExpiresAt:     expiresAt,
	}); err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return ErrAggregateIdempotencyConflict
		}
		return fmt.Errorf("insert %s receipt: %w", s.receipts.Name(), err)
	}
	return s.AppendAggregateOutboxEvents(ctx, events)
}

// AppendAggregateOutboxEvents 在调用方事务内追加事件，事件 ID 幂等。
func (s *MongoAggregateCommandStore) AppendAggregateOutboxEvents(
	ctx context.Context,
	events []application.AggregateOutboxEvent,
) error {
	for _, event := range events {
		sequence, err := s.nextOutboxSequence(ctx)
		if err != nil {
			return err
		}
		if _, err := s.outbox.InsertOne(ctx, aggregateOutboxDocument{
			ID:             event.EventID,
			OutboxSequence: sequence,
			AggregateID:    event.AggregateID,
			EventType:      event.EventType,
			ConversationID: event.ConversationID,
			ActorID:        event.ActorID,
			Payload:        event.Payload,
			Status:         "pending",
			CreatedAt:      time.Now().UTC(),
		}); err != nil {
			return fmt.Errorf("insert %s event: %w", s.outbox.Name(), err)
		}
	}
	return nil
}

func (s *MongoAggregateCommandStore) nextOutboxSequence(ctx context.Context) (int64, error) {
	var document struct {
		Seq int64 `bson:"seq"`
	}
	err := s.sequences.FindOneAndUpdate(
		ctx,
		bson.M{"_id": s.sequenceKey},
		bson.M{"$inc": bson.M{"seq": int64(1)}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, fmt.Errorf("advance %s outbox sequence: %w", s.sequenceKey, err)
	}
	return document.Seq, nil
}

func (s *MongoAggregateCommandStore) ReadAggregateOutboxAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]application.AggregateOutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	after := int64(0)
	if trimmed := strings.TrimSpace(checkpoint); trimmed != "" {
		parsed, err := strconv.ParseInt(trimmed, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("parse %s checkpoint %q: %w", s.outbox.Name(), checkpoint, err)
		}
		after = parsed
	}
	cursor, err := s.outbox.Find(
		ctx,
		bson.M{"outboxSequence": bson.M{"$gt": after}},
		options.Find().SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var documents []aggregateOutboxDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, err
	}
	events := make([]application.AggregateOutboxEvent, 0, len(documents))
	for _, document := range documents {
		events = append(events, application.AggregateOutboxEvent{
			EventID:        document.ID,
			EventType:      document.EventType,
			AggregateID:    document.AggregateID,
			ConversationID: document.ConversationID,
			ActorID:        document.ActorID,
			Payload:        document.Payload,
			Checkpoint:     strconv.FormatInt(document.OutboxSequence, 10),
		})
	}
	return events, nil
}

func (s *MongoAggregateCommandStore) MarkAggregateOutboxDispatched(
	ctx context.Context,
	eventID string,
	dispatchedAt time.Time,
) error {
	_, err := s.outbox.UpdateOne(
		ctx,
		bson.M{"_id": eventID},
		bson.M{"$set": bson.M{"status": "dispatched", "dispatchedAt": dispatchedAt.UTC()}},
	)
	return err
}

// MongoProjectionCheckpointStore 是 chat 域 relay/projector 共享的
// consumer 水位存储。
type MongoProjectionCheckpointStore struct {
	checkpoints *mongo.Collection
}

var _ application.ProjectionCheckpointStore = (*MongoProjectionCheckpointStore)(nil)

func NewMongoProjectionCheckpointStore(db *mongo.Database) *MongoProjectionCheckpointStore {
	return &MongoProjectionCheckpointStore{
		checkpoints: db.Collection("chat_projection_checkpoints"),
	}
}

func (s *MongoProjectionCheckpointStore) LoadProjectionCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	var document struct {
		Checkpoint string `bson:"checkpoint"`
	}
	err := s.checkpoints.FindOne(ctx, bson.M{"_id": strings.TrimSpace(consumer)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return document.Checkpoint, nil
}

func (s *MongoProjectionCheckpointStore) SaveProjectionCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	_, err := s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
		bson.M{"$set": bson.M{
			"checkpoint": checkpoint,
			"updatedAt":  time.Now().UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}
