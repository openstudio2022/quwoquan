package persistence

import (
	"context"
	"errors"
	"fmt"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"quwoquan_service/services/search-service/internal/search/search_release_preparation/domain"
	"time"
)

type MongoStore struct{ states, receipts *mongo.Collection }

func NewMongoStore(db *mongo.Database) *MongoStore {
	return &MongoStore{db.Collection("search_release_preparations"), db.Collection("search_release_preparation_receipts")}
}
func (s *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.states.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "preparationId", Value: 1}}, Options: options.Index().SetUnique(true).SetName("uq_search_release_preparation_identity")},
		{Keys: bson.D{{Key: "binding.release.environment", Value: 1}, {Key: "binding.release.sourceOwner", Value: 1}, {Key: "binding.release.releaseId", Value: 1}, {Key: "binding.release.manifestDigest", Value: 1}, {Key: "binding.slice", Value: 1}, {Key: "binding.providerBindingGeneration", Value: 1}, {Key: "binding.schemaGeneration", Value: 1}}, Options: options.Index().SetUnique(true).SetName("uq_search_release_preparation_binding")},
		{Keys: bson.D{{Key: "preparationId", Value: 1}, {Key: "version", Value: 1}, {Key: "leaseUntil", Value: 1}}, Options: options.Index().SetName("idx_search_release_preparation_cas")},
	})
	if err != nil {
		return err
	}
	_, err = s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "receiptKey", Value: 1}}, Options: options.Index().SetUnique(true).SetName("uq_search_release_preparation_receipt")},
		{Keys: bson.D{{Key: "preparationId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_search_release_preparation_receipt_owner")},
	})
	return err
}
func storeError(err error) error {
	if errors.Is(err, mongo.ErrNoDocuments) {
		return domain.ErrNotFound
	}
	if mongo.IsDuplicateKeyError(err) {
		return domain.ErrConflict
	}
	return fmt.Errorf("%w: %v", domain.ErrUnavailable, err)
}
func (s *MongoStore) Load(ctx context.Context, id string) (domain.State, error) {
	var state domain.State
	if err := s.states.FindOne(ctx, bson.M{"preparationId": id}).Decode(&state); err != nil {
		return state, storeError(err)
	}
	if state.Binding.ID() != id || state.Binding.Validate(state.Binding.Release.Environment, state.Binding.ProviderBindingGeneration) != nil || state.Snapshot.Validate() != nil || state.Snapshot.Release() != state.Binding.Release || state.Binding.Slice != state.Snapshot.Kind+"_search" {
		return domain.State{}, domain.ErrConflict
	}
	return state, nil
}
func (s *MongoStore) Receipt(ctx context.Context, id, key, digest string) (domain.View, bool, error) {
	// 显式恢复先查本实例最近命令；真实使用preparationId/createdAt索引，仍需下方全局key判冲突。
	cursor, err := s.receipts.Find(ctx, bson.M{"preparationId": id}, options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(1))
	if err != nil {
		return domain.View{}, false, storeError(err)
	}
	var recent []struct {
		Key    string      `bson:"receiptKey"`
		Digest string      `bson:"commandDigest"`
		Result domain.View `bson:"result"`
	}
	err = cursor.All(ctx, &recent)
	_ = cursor.Close(ctx)
	if err != nil {
		return domain.View{}, false, storeError(err)
	}
	if len(recent) == 1 && recent[0].Key == key {
		if recent[0].Digest != digest || recent[0].Result.Binding.ID() != id || recent[0].Result.Binding.Validate(recent[0].Result.Binding.Release.Environment, recent[0].Result.Binding.ProviderBindingGeneration) != nil {
			return domain.View{}, false, domain.ErrConflict
		}
		return recent[0].Result, true, nil
	}
	var receipt struct {
		Digest string      `bson:"commandDigest"`
		Result domain.View `bson:"result"`
	}
	err = s.receipts.FindOne(ctx, bson.M{"receiptKey": key}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return domain.View{}, false, nil
	}
	if err != nil {
		return domain.View{}, false, storeError(err)
	}
	if receipt.Digest != digest || receipt.Result.Binding.ID() != id || receipt.Result.Binding.Validate(receipt.Result.Binding.Release.Environment, receipt.Result.Binding.ProviderBindingGeneration) != nil {
		return domain.View{}, false, domain.ErrConflict
	}
	return receipt.Result, true, nil
}
func (s *MongoStore) Create(ctx context.Context, state domain.State) error {
	_, err := s.states.InsertOne(ctx, state)
	if err != nil {
		return storeError(err)
	}
	return nil
}
func (s *MongoStore) Claim(ctx context.Context, state domain.State, expected int64, now time.Time) error {
	result, err := s.states.ReplaceOne(ctx, bson.M{"preparationId": state.PreparationID, "version": expected, "$or": bson.A{bson.M{"status": bson.M{"$in": bson.A{"accepted", "blocked"}}}, bson.M{"status": "running", "leaseUntil": bson.M{"$lte": now}}}}, state)
	if err != nil {
		return storeError(err)
	}
	if result.MatchedCount != 1 {
		return domain.ErrConflict
	}
	return nil
}
func (s *MongoStore) Commit(ctx context.Context, state domain.State, version int64, token, key, digest string, now time.Time) error {
	session, err := s.states.Database().Client().StartSession()
	if err != nil {
		return storeError(err)
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(tx context.Context) (any, error) {
		result, err := s.states.ReplaceOne(tx, bson.M{"preparationId": state.PreparationID, "version": version, "status": "running", "executionToken": token, "leaseUntil": bson.M{"$gt": now}}, state)
		if err != nil {
			return nil, err
		}
		if result.MatchedCount != 1 {
			return nil, domain.ErrConflict
		}
		_, err = s.receipts.InsertOne(tx, bson.M{"receiptKey": key, "preparationId": state.PreparationID, "commandDigest": digest, "result": state.View(), "createdAt": now})
		return nil, err
	})
	if errors.Is(err, domain.ErrConflict) {
		return err
	}
	if err != nil {
		return storeError(err)
	}
	return nil
}

// ListReceipts 提供流程诊断所需的真实命令历史读取，不承担自动重放或GC。
func (s *MongoStore) ListReceipts(ctx context.Context, id string, limit int64) ([]domain.View, error) {
	if limit < 1 || limit > 100 {
		return nil, domain.ErrInvalid
	}
	cursor, err := s.receipts.Find(ctx, bson.M{"preparationId": id}, options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(limit))
	if err != nil {
		return nil, storeError(err)
	}
	defer cursor.Close(ctx)
	var rows []struct {
		Result domain.View `bson:"result"`
	}
	if err = cursor.All(ctx, &rows); err != nil {
		return nil, storeError(err)
	}
	out := make([]domain.View, 0, len(rows))
	for _, r := range rows {
		out = append(out, r.Result)
	}
	return out, nil
}

var _ domain.Store = (*MongoStore)(nil)
