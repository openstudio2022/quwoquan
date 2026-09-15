package persistence

import (
	"context"
	"errors"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	domain "quwoquan_service/services/content-service/internal/content/post_collection/domain"
	"time"
)

type document struct {
	ID           string            `bson:"_id"`
	Owner        string            `bson:"ownerPersonaId"`
	Name         string            `bson:"name"`
	CoverAssetID string            `bson:"coverAssetId"`
	Visibility   domain.Visibility `bson:"visibility"`
	PostIDs      []string          `bson:"postIds"`
	Version      int64             `bson:"version"`
	Status       domain.Status     `bson:"status"`
	UpdatedAt    time.Time         `bson:"updatedAt"`
}
type Store struct{ collection *mongo.Collection }

var _ domain.Store = (*Store)(nil)

func New(db *mongo.Database) (*Store, error) {
	if db == nil {
		return nil, domain.Unavailable
	}
	return &Store{db.Collection("post_collections")}, nil
}
func (s *Store) Find(ctx context.Context, id string) (domain.Collection, bool, error) {
	var d document
	err := s.collection.FindOne(ctx, bson.M{"_id": id}).Decode(&d)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return domain.Collection{}, false, nil
	}
	if err != nil {
		return domain.Collection{}, false, err
	}
	if d.Owner == "" || d.Version < 1 || (d.Status != domain.Active && d.Status != domain.Deleted) || (d.Visibility != domain.Public && d.Visibility != domain.Private) {
		return domain.Collection{}, false, domain.StorageRead
	}
	return domain.Collection{ID: d.ID, Owner: d.Owner, Name: d.Name, CoverAssetID: d.CoverAssetID, Visibility: d.Visibility, PostIDs: d.PostIDs, Version: d.Version, Status: d.Status, UpdatedAt: d.UpdatedAt}, true, nil
}
func (s *Store) CompareAndSwap(ctx context.Context, c domain.Collection, expected int64) (bool, error) {
	if c.Version != expected+1 || c.Owner == "" || c.ID == "" {
		return false, domain.Invalid
	}
	d := document{c.ID, c.Owner, c.Name, c.CoverAssetID, c.Visibility, c.PostIDs, c.Version, c.Status, c.UpdatedAt}
	if expected == 0 {
		_, err := s.collection.InsertOne(ctx, d)
		if mongo.IsDuplicateKeyError(err) {
			return false, nil
		}
		return err == nil, err
	}
	res, err := s.collection.ReplaceOne(ctx, bson.M{"_id": c.ID, "ownerPersonaId": c.Owner, "version": expected, "status": domain.Active}, d)
	if err != nil {
		return false, err
	}
	return res.MatchedCount == 1, nil
}
