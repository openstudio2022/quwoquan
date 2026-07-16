package platformmedia

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimemedia "quwoquan_service/runtime/media"
)

var (
	ErrUploadSessionNotFound      = errors.New("media upload session not found")
	ErrUploadSessionExpired       = errors.New("media upload session expired")
	ErrUploadSessionStateConflict = errors.New("media upload session state conflict")
	ErrMediaAssetNotFound         = errors.New("media asset not found")
	ErrMediaDigestConflict        = errors.New("media digest conflicts with an existing asset")
)

type MongoSessionStore struct {
	collection *mongo.Collection
}

var _ runtimemedia.SessionStore = (*MongoSessionStore)(nil)

func NewMongoSessionStore(db *mongo.Database, collectionName string) *MongoSessionStore {
	return &MongoSessionStore{collection: db.Collection(strings.TrimSpace(collectionName))}
}

func (s *MongoSessionStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().
				SetName("ttl_media_upload_session_expires_at").
				SetExpireAfterSeconds(0),
		},
		{
			Keys: bson.D{
				{Key: "ownerId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_media_upload_owner_status_created"),
		},
	})
	if err != nil {
		return fmt.Errorf("ensure media upload session indexes: %w", err)
	}
	return nil
}

func (s *MongoSessionStore) Create(ctx context.Context, session *runtimemedia.UploadSession) error {
	if session == nil || strings.TrimSpace(session.SessionID) == "" {
		return errors.New("media upload session is required")
	}
	if session.ExpiresAt.IsZero() {
		return errors.New("media upload session expiresAt is required")
	}
	if strings.TrimSpace(session.Status) != "pending" {
		return errors.New("media upload session must start pending")
	}
	if _, err := s.collection.InsertOne(ctx, session); err != nil {
		return fmt.Errorf("create media upload session %s: %w", session.SessionID, err)
	}
	return nil
}

func (s *MongoSessionStore) FindByID(
	ctx context.Context,
	sessionID string,
) (*runtimemedia.UploadSession, error) {
	trimmedID := strings.TrimSpace(sessionID)
	if trimmedID == "" {
		return nil, fmt.Errorf("%w: empty id", ErrUploadSessionNotFound)
	}
	var session runtimemedia.UploadSession
	if err := s.collection.FindOne(ctx, bson.M{"_id": trimmedID}).Decode(&session); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf("%w: %s", ErrUploadSessionNotFound, trimmedID)
		}
		return nil, fmt.Errorf("find media upload session %s: %w", trimmedID, err)
	}
	if !session.ExpiresAt.IsZero() && !session.ExpiresAt.After(time.Now().UTC()) {
		return nil, fmt.Errorf("%w: %s", ErrUploadSessionExpired, trimmedID)
	}
	return &session, nil
}

func (s *MongoSessionStore) UpdateStatus(
	ctx context.Context,
	sessionID string,
	status string,
) error {
	trimmedID := strings.TrimSpace(sessionID)
	nextStatus := strings.ToLower(strings.TrimSpace(status))
	if trimmedID == "" {
		return fmt.Errorf("%w: empty id", ErrUploadSessionNotFound)
	}
	if nextStatus != "completed" && nextStatus != "aborted" {
		return fmt.Errorf("unsupported media upload status %q", status)
	}
	result, err := s.collection.UpdateOne(
		ctx,
		bson.M{
			"_id":       trimmedID,
			"status":    "pending",
			"expiresAt": bson.M{"$gt": time.Now().UTC()},
		},
		bson.M{"$set": bson.M{"status": nextStatus}},
	)
	if err != nil {
		return fmt.Errorf("compare-and-set media upload session %s: %w", trimmedID, err)
	}
	if result.MatchedCount != 1 {
		return fmt.Errorf(
			"%w: session=%s expected=pending next=%s",
			ErrUploadSessionStateConflict,
			trimmedID,
			nextStatus,
		)
	}
	return nil
}

type MongoAssetStore struct {
	collection *mongo.Collection
}

var _ runtimemedia.AssetStore = (*MongoAssetStore)(nil)

func NewMongoAssetStore(db *mongo.Database, collectionName string) *MongoAssetStore {
	return &MongoAssetStore{collection: db.Collection(strings.TrimSpace(collectionName))}
}

func (s *MongoAssetStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "sessionId", Value: 1}},
			Options: options.Index().SetName("uq_media_asset_session").SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "sha256", Value: 1}},
			Options: options.Index().
				SetName("uq_media_asset_sha256").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{"sha256": bson.M{"$type": "string", "$gt": ""}}),
		},
		{
			Keys: bson.D{
				{Key: "ownerId", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_media_asset_owner_created"),
		},
	})
	if err != nil {
		return fmt.Errorf("ensure media asset indexes: %w", err)
	}
	return nil
}

func (s *MongoAssetStore) Create(ctx context.Context, asset *runtimemedia.MediaAsset) error {
	if asset == nil ||
		strings.TrimSpace(asset.AssetID) == "" ||
		strings.TrimSpace(asset.SessionID) == "" ||
		strings.TrimSpace(asset.Sha256) == "" {
		return errors.New("media asset id, session id and sha256 are required")
	}
	if _, err := s.collection.InsertOne(ctx, asset); err != nil {
		if mongo.IsDuplicateKeyError(err) {
			var existing runtimemedia.MediaAsset
			findErr := s.collection.FindOne(ctx, bson.M{"$or": bson.A{
				bson.M{"sessionId": strings.TrimSpace(asset.SessionID)},
				bson.M{"sha256": strings.TrimSpace(asset.Sha256)},
			}}).Decode(&existing)
			if findErr == nil {
				if existing.Sha256 != asset.Sha256 {
					return fmt.Errorf(
						"%w: session=%s existing=%s incoming=%s",
						ErrMediaDigestConflict,
						asset.SessionID,
						existing.Sha256,
						asset.Sha256,
					)
				}
				*asset = existing
				return nil
			}
		}
		return fmt.Errorf("create media asset %s: %w", asset.AssetID, err)
	}
	return nil
}

func (s *MongoAssetStore) FindByID(
	ctx context.Context,
	assetID string,
) (*runtimemedia.MediaAsset, error) {
	trimmedID := strings.TrimSpace(assetID)
	if trimmedID == "" {
		return nil, fmt.Errorf("%w: empty id", ErrMediaAssetNotFound)
	}
	var asset runtimemedia.MediaAsset
	if err := s.collection.FindOne(ctx, bson.M{"_id": trimmedID}).Decode(&asset); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf("%w: %s", ErrMediaAssetNotFound, trimmedID)
		}
		return nil, fmt.Errorf("find media asset %s: %w", trimmedID, err)
	}
	return &asset, nil
}

func (s *MongoAssetStore) FindByIDs(
	ctx context.Context,
	assetIDs []string,
) (map[string]*runtimemedia.MediaAsset, error) {
	unique := make([]string, 0, len(assetIDs))
	seen := make(map[string]struct{}, len(assetIDs))
	for _, assetID := range assetIDs {
		assetID = strings.TrimSpace(assetID)
		if assetID == "" {
			continue
		}
		if _, found := seen[assetID]; found {
			continue
		}
		seen[assetID] = struct{}{}
		unique = append(unique, assetID)
	}
	assets := make(map[string]*runtimemedia.MediaAsset, len(unique))
	if len(unique) == 0 {
		return assets, nil
	}
	cursor, err := s.collection.Find(ctx, bson.M{"_id": bson.M{"$in": unique}})
	if err != nil {
		return nil, fmt.Errorf("find media assets: %w", err)
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var asset runtimemedia.MediaAsset
		if err := cursor.Decode(&asset); err != nil {
			return nil, fmt.Errorf("decode media asset: %w", err)
		}
		copy := asset
		assets[asset.AssetID] = &copy
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate media assets: %w", err)
	}
	return assets, nil
}
