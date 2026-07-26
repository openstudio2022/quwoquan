// Package mediareferencefence serializes creation of durable content
// references with owner-driven MediaAsset discard.
package mediareferencefence

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
)

const CollectionName = "media_asset_reference_fences"

var (
	ErrDeletionInProgress   = errors.New("media asset deletion is in progress")
	ErrReferenceUnavailable = errors.New("media asset is unavailable for reference")
)

type Reference struct {
	AssetID string
	OwnerID string
}

type Manager struct {
	fences *mongo.Collection
	assets *mongo.Collection
}

func New(db *mongo.Database) (*Manager, error) {
	if db == nil {
		return nil, errors.New("media reference fence database is required")
	}
	return &Manager{
		fences: db.Collection(CollectionName),
		assets: db.Collection("media_assets"),
	}, nil
}

// AllowReferences must run in the same Mongo transaction as the Post,
// Comment, or MediaAsset reference write. Touching the fence before checking
// the authoritative asset makes that transaction conflict with a concurrent
// discard instead of committing a reference to a deleted asset.
func (manager *Manager) AllowReferences(
	ctx context.Context,
	references []Reference,
) error {
	if manager == nil || manager.fences == nil || manager.assets == nil {
		return errors.New("media reference fence is not configured")
	}
	for _, reference := range normalizedReferences(references) {
		now := time.Now().UTC()
		result, err := manager.fences.UpdateOne(
			ctx,
			bson.M{
				"_id":   reference.AssetID,
				"state": bson.M{"$ne": "deleting"},
			},
			bson.M{
				"$setOnInsert": bson.M{
					"state":     "active",
					"createdAt": now,
				},
				"$set": bson.M{"updatedAt": now},
				"$inc": bson.M{"generation": int64(1)},
			},
			options.UpdateOne().SetUpsert(true),
		)
		if mongo.IsDuplicateKeyError(err) {
			return ErrDeletionInProgress
		}
		if err != nil {
			return fmt.Errorf("touch media reference fence: %w", err)
		}
		if result.MatchedCount+result.UpsertedCount != 1 {
			return ErrDeletionInProgress
		}
		count, err := manager.assets.CountDocuments(
			ctx,
			bson.M{
				"_id":              reference.AssetID,
				"ownerId":          reference.OwnerID,
				"processingStatus": "ready",
			},
			options.Count().SetLimit(1),
		)
		if err != nil {
			return fmt.Errorf("verify media reference target: %w", err)
		}
		if count != 1 {
			return ErrReferenceUnavailable
		}
	}
	return nil
}

// ClaimDeletion must run in the same transaction as the deleted aggregate,
// command receipt, and outbox fact. Returning an error rolls the fence claim
// back together with all other writes.
func (manager *Manager) ClaimDeletion(
	ctx context.Context,
	assetID string,
) error {
	if manager == nil || manager.fences == nil {
		return errors.New("media reference fence is not configured")
	}
	assetID = strings.TrimSpace(assetID)
	if assetID == "" {
		return errors.New("media asset id is required")
	}
	now := time.Now().UTC()
	result, err := manager.fences.UpdateOne(
		ctx,
		bson.M{
			"_id":   assetID,
			"state": bson.M{"$ne": "deleting"},
		},
		bson.M{
			"$setOnInsert": bson.M{"createdAt": now},
			"$set": bson.M{
				"state":     "deleting",
				"updatedAt": now,
			},
			"$inc": bson.M{"generation": int64(1)},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if mongo.IsDuplicateKeyError(err) {
		return ErrDeletionInProgress
	}
	if err != nil {
		return fmt.Errorf("claim media deletion fence: %w", err)
	}
	if result.MatchedCount+result.UpsertedCount != 1 {
		return ErrDeletionInProgress
	}
	return nil
}

func normalizedReferences(references []Reference) []Reference {
	byID := make(map[string]Reference, len(references))
	for _, reference := range references {
		assetID := strings.TrimSpace(reference.AssetID)
		ownerID := strings.TrimSpace(reference.OwnerID)
		if assetID == "" || ownerID == "" {
			continue
		}
		byID[assetID] = Reference{AssetID: assetID, OwnerID: ownerID}
	}
	assetIDs := make([]string, 0, len(byID))
	for assetID := range byID {
		assetIDs = append(assetIDs, assetID)
	}
	sort.Strings(assetIDs)
	result := make([]Reference, 0, len(assetIDs))
	for _, assetID := range assetIDs {
		result = append(result, byID[assetID])
	}
	return result
}
