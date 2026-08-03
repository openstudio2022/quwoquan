// Package mediaobjectfence serializes physical deletion of shared,
// content-addressed media objects with creation of new MediaAsset references.
package mediaobjectfence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

const CollectionName = "media_object_deletion_fences"

var ErrDeletionInProgress = errors.New("media object deletion is in progress")

type Manager struct {
	db     *mongo.Database
	assets *mongo.Collection
	fences *mongo.Collection
}

type fenceDocument struct {
	ID        string     `bson:"_id"`
	State     string     `bson:"state"`
	WorkID    string     `bson:"workId,omitempty"`
	UpdatedAt time.Time  `bson:"updatedAt"`
	DeletedAt *time.Time `bson:"deletedAt,omitempty"`
}

func New(db *mongo.Database) (*Manager, error) {
	if db == nil {
		return nil, errors.New("media object fence requires MongoDB")
	}
	return &Manager{
		db:     db,
		assets: db.Collection("media_assets"),
		fences: db.Collection(CollectionName),
	}, nil
}

// AllowReference runs inside the MediaAsset commit transaction. It records a
// new or renewed reference only when no closure worker owns a deletion fence.
// A client that raced a closure must retry from its durable upload command
// rather than commit a MediaAsset that points to an object being removed.
func (manager *Manager) AllowReference(
	ctx context.Context,
	objectKey string,
) error {
	if manager == nil || manager.fences == nil {
		return errors.New("media object fence is not configured")
	}
	objectKey = strings.Trim(strings.TrimSpace(objectKey), "/")
	if !mediamodel.IsContentAddressedObjectKey(objectKey) {
		return nil
	}
	now := time.Now().UTC()
	var current fenceDocument
	err := manager.fences.FindOne(
		ctx,
		bson.M{"_id": objectKey},
	).Decode(&current)
	if errors.Is(err, mongo.ErrNoDocuments) {
		_, err = manager.fences.UpdateOne(
			ctx,
			bson.M{"_id": objectKey},
			bson.M{"$setOnInsert": bson.M{
				"state":     "active",
				"updatedAt": now,
			}},
			options.UpdateOne().SetUpsert(true),
		)
		if err != nil {
			return fmt.Errorf("create media object reference fence: %w", err)
		}
		return nil
	}
	if err != nil {
		return fmt.Errorf("read media object reference fence: %w", err)
	}
	if current.State == "deleting" {
		return ErrDeletionInProgress
	}
	result, err := manager.fences.UpdateOne(
		ctx,
		bson.M{
			"_id":   objectKey,
			"state": bson.M{"$ne": "deleting"},
		},
		bson.M{
			"$set": bson.M{
				"state":     "active",
				"updatedAt": now,
			},
			"$unset": bson.M{
				"workId":    "",
				"deletedAt": "",
			},
		},
	)
	if err != nil {
		return fmt.Errorf("renew media object reference fence: %w", err)
	}
	if result.MatchedCount != 1 {
		return ErrDeletionInProgress
	}
	return nil
}

// ClaimUnreferencedDeletion turns an unreferenced CAS object into a deletion
// fence atomically with the final MediaAsset-reference check. It is safe to
// call repeatedly for the same work: a crashed worker retains its fence and
// may retry the idempotent object-store deletion.
func (manager *Manager) ClaimUnreferencedDeletion(
	ctx context.Context,
	objectKey string,
	workID string,
) (bool, error) {
	if manager == nil || manager.db == nil || manager.assets == nil ||
		manager.fences == nil {
		return false, errors.New("media object fence is not configured")
	}
	objectKey = strings.Trim(strings.TrimSpace(objectKey), "/")
	workID = strings.TrimSpace(workID)
	if !mediamodel.IsContentAddressedObjectKey(objectKey) || workID == "" {
		return false, errors.New("media object deletion fence input is invalid")
	}
	session, err := manager.db.Client().StartSession()
	if err != nil {
		return false, fmt.Errorf("start media object deletion fence transaction: %w", err)
	}
	defer session.EndSession(ctx)

	claimed := false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		references, countErr := manager.assets.CountDocuments(
			txCtx,
			bson.M{
				"processingStatus": bson.M{"$ne": "deleted"},
				"$or": bson.A{
					bson.M{"objectKey": objectKey},
					bson.M{"imageNormalizedObjectKey": objectKey},
					bson.M{
						"imageDescriptorRevisions.descriptor.imageNormalizedObjectKey": objectKey,
					},
				},
			},
			options.Count().SetLimit(1),
		)
		if countErr != nil {
			return nil, fmt.Errorf(
				"count media object references before deletion: %w",
				countErr,
			)
		}
		if references != 0 {
			claimed = false
			return nil, nil
		}

		now := time.Now().UTC()
		var current fenceDocument
		readErr := manager.fences.FindOne(
			txCtx,
			bson.M{"_id": objectKey},
		).Decode(&current)
		if errors.Is(readErr, mongo.ErrNoDocuments) {
			if _, insertErr := manager.fences.InsertOne(
				txCtx,
				fenceDocument{
					ID:        objectKey,
					State:     "deleting",
					WorkID:    workID,
					UpdatedAt: now,
				},
			); insertErr != nil {
				return nil, fmt.Errorf(
					"create media object deletion fence: %w",
					insertErr,
				)
			}
			claimed = true
			return nil, nil
		}
		if readErr != nil {
			return nil, fmt.Errorf("read media object deletion fence: %w", readErr)
		}
		switch current.State {
		case "deleted":
			claimed = false
			return nil, nil
		case "deleting":
			claimed = current.WorkID == workID
			return nil, nil
		}
		result, updateErr := manager.fences.UpdateOne(
			txCtx,
			bson.M{
				"_id":   objectKey,
				"state": current.State,
			},
			bson.M{
				"$set": bson.M{
					"state":     "deleting",
					"workId":    workID,
					"updatedAt": now,
				},
				"$unset": bson.M{"deletedAt": ""},
			},
		)
		if updateErr != nil {
			return nil, fmt.Errorf(
				"claim media object deletion fence: %w",
				updateErr,
			)
		}
		if result.MatchedCount != 1 {
			return nil, errors.New("media object deletion fence changed")
		}
		claimed = true
		return nil, nil
	})
	if err != nil {
		return false, err
	}
	return claimed, nil
}

// MarkWorkDeleted records only after the object-store deletion succeeded. A
// retry may safely repeat deletion while the fence remains deleting.
func (manager *Manager) MarkWorkDeleted(
	ctx context.Context,
	workID string,
) error {
	if manager == nil || manager.fences == nil {
		return errors.New("media object fence is not configured")
	}
	workID = strings.TrimSpace(workID)
	if workID == "" {
		return errors.New("media object deletion work ID is required")
	}
	now := time.Now().UTC()
	_, err := manager.fences.UpdateMany(
		ctx,
		bson.M{
			"workId": workID,
			"state":  "deleting",
		},
		bson.M{
			"$set": bson.M{
				"state":     "deleted",
				"updatedAt": now,
				"deletedAt": now,
			},
			"$unset": bson.M{"workId": ""},
		},
	)
	if err != nil {
		return fmt.Errorf("complete media object deletion fence: %w", err)
	}
	return nil
}
