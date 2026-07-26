// Package recentsearchstore 是 RecentSearchState 的 Mongo AggregateStore：
// state（version CAS）与 command receipt 在同一事务原子提交；
// receipt 集合带 TTL（24h 幂等窗口），语义幂等由聚合自身（语义键去重）承载。
package recentsearchstore

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/model"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/ports"
)

const (
	statesCollection   = "recent_search_states"
	receiptsCollection = "recent_search_receipts"
)

// Store 实现 ports.Store。
type Store struct {
	states   *mongo.Collection
	receipts *mongo.Collection
}

func NewStore(db *mongo.Database) *Store {
	return &Store{
		states:   db.Collection(statesCollection),
		receipts: db.Collection(receiptsCollection),
	}
}

// EnsureIndexes 建立 storage.yaml 声明的索引与 receipt TTL。
func (s *Store) EnsureIndexes(ctx context.Context) error {
	_, err := s.states.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "personaId", Value: 1}, {Key: "scope", Value: 1}},
			Options: options.Index().SetName("uq_recent_search_subject_scope").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "updatedAt", Value: -1}},
			Options: options.Index().SetName("idx_recent_search_updated"),
		},
		{
			Keys:    bson.D{{Key: "personaId", Value: 1}, {Key: "entries.entryId", Value: 1}},
			Options: options.Index().SetName("idx_recent_search_entry"),
		},
	})
	if err != nil {
		return err
	}
	_, err = s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "personaId", Value: 1}},
			Options: options.Index().SetName("idx_recent_search_receipts_persona"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_recent_search_receipts_expire").SetExpireAfterSeconds(0),
		},
	})
	return err
}

func (s *Store) Load(ctx context.Context, personaID, scope string) (model.State, bool, error) {
	var state model.State
	err := s.states.FindOne(ctx, bson.M{
		"personaId": strings.TrimSpace(personaID),
		"scope":     model.NormalizeScope(scope),
	}).Decode(&state)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.State{}, false, nil
	}
	if err != nil {
		return model.State{}, false, err
	}
	return state, true, nil
}

func (s *Store) ListByPersona(ctx context.Context, personaID string) ([]model.State, error) {
	cursor, err := s.states.Find(ctx, bson.M{"personaId": strings.TrimSpace(personaID)})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var states []model.State
	if err := cursor.All(ctx, &states); err != nil {
		return nil, err
	}
	return states, nil
}

func (s *Store) FindEntryOwner(ctx context.Context, personaID, entryID string) (model.State, bool, error) {
	var state model.State
	err := s.states.FindOne(ctx, bson.M{
		"personaId":       strings.TrimSpace(personaID),
		"entries.entryId": strings.TrimSpace(entryID),
	}).Decode(&state)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.State{}, false, nil
	}
	if err != nil {
		return model.State{}, false, err
	}
	return state, true, nil
}

func (s *Store) FindReceipt(ctx context.Context, receiptKey, commandDigest string) (ports.Receipt, bool, error) {
	var receipt ports.Receipt
	err := s.receipts.FindOne(ctx, bson.M{"_id": strings.TrimSpace(receiptKey)}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.Receipt{}, false, nil
	}
	if err != nil {
		return ports.Receipt{}, false, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.receipts.DeleteOne(ctx, bson.M{"_id": receipt.ReceiptKey}); err != nil {
			return ports.Receipt{}, false, err
		}
		return ports.Receipt{}, false, nil
	}
	if receipt.CommandDigest != strings.TrimSpace(commandDigest) {
		return ports.Receipt{}, false, ports.ErrIdempotencyConflict
	}
	receipt.Replayed = true
	return receipt, true, nil
}

func (s *Store) Commit(ctx context.Context, commit ports.Commit) error {
	if commit.State.Version != commit.ExpectedVersion+1 {
		return ports.ErrVersionConflict
	}
	session, err := s.states.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)

	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replayed, found, receiptErr := s.FindReceipt(
			txCtx, commit.Receipt.ReceiptKey, commit.Receipt.CommandDigest,
		); receiptErr != nil {
			return nil, receiptErr
		} else if found {
			_ = replayed
			return nil, nil
		}
		if commit.ExpectedVersion == 0 {
			if _, insertErr := s.states.InsertOne(txCtx, commit.State); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, ports.ErrVersionConflict
				}
				return nil, insertErr
			}
		} else {
			result, replaceErr := s.states.ReplaceOne(
				txCtx,
				bson.M{"_id": commit.State.ID, "version": commit.ExpectedVersion},
				commit.State,
			)
			if replaceErr != nil {
				return nil, replaceErr
			}
			if result.MatchedCount != 1 {
				return nil, ports.ErrVersionConflict
			}
		}
		if _, insertErr := s.receipts.InsertOne(txCtx, commit.Receipt); insertErr != nil {
			if mongo.IsDuplicateKeyError(insertErr) {
				return nil, ports.ErrIdempotencyConflict
			}
			return nil, insertErr
		}
		return nil, nil
	})
	return err
}

func (s *Store) RecordNoopReceipt(ctx context.Context, receipt ports.Receipt) (ports.Receipt, error) {
	if replayed, found, err := s.FindReceipt(
		ctx, receipt.ReceiptKey, receipt.CommandDigest,
	); err != nil {
		return ports.Receipt{}, err
	} else if found {
		return replayed, nil
	}
	if _, err := s.receipts.InsertOne(ctx, receipt); err != nil {
		if mongo.IsDuplicateKeyError(err) {
			replayed, found, findErr := s.FindReceipt(ctx, receipt.ReceiptKey, receipt.CommandDigest)
			if findErr != nil {
				return ports.Receipt{}, findErr
			}
			if found {
				return replayed, nil
			}
		}
		return ports.Receipt{}, err
	}
	return receipt, nil
}

var _ ports.Store = (*Store)(nil)
