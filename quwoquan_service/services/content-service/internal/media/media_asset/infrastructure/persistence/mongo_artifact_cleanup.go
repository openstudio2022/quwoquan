package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	mediaprocessing "quwoquan_service/services/content-service/internal/media/media_asset/application/processing"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

func (s *MongoMediaStore) PrepareMediaAssetArtifactCleanup(
	ctx context.Context,
	assetID string,
	eventID string,
) (mediaprocessing.ArtifactCleanupWork, bool, error) {
	assetID = strings.TrimSpace(assetID)
	eventID = strings.TrimSpace(eventID)
	if assetID == "" || eventID == "" {
		return mediaprocessing.ArtifactCleanupWork{}, false, errors.New(
			"media artifact cleanup requires asset and event ids",
		)
	}
	var document mediaAssetDocument
	err := s.assets.FindOne(
		ctx,
		bson.M{
			"_id":              assetID,
			"processingStatus": "deleted",
		},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return mediaprocessing.ArtifactCleanupWork{}, false, errors.New(
			"deleted MediaAsset cleanup source is missing",
		)
	}
	if err != nil {
		return mediaprocessing.ArtifactCleanupWork{}, false, fmt.Errorf(
			"load deleted MediaAsset cleanup source: %w",
			err,
		)
	}
	if document.ArtifactsDeletedAt != nil {
		return mediaprocessing.ArtifactCleanupWork{}, true, nil
	}
	historicalImageArtifacts := make(
		[]mediaprocessing.ImageArtifactSource,
		0,
		len(document.ImageDescriptorRevisions),
	)
	for _, revision := range document.ImageDescriptorRevisions {
		historicalImageArtifacts = append(
			historicalImageArtifacts,
			mediaprocessing.ImageArtifactSource{
				NormalizedObjectKey: revision.Descriptor.ImageNormalizedObjectKey,
				PublicSliceKey:      revision.Descriptor.ImagePublicSliceKey,
			},
		)
	}
	projected := mediaprocessing.PlanArtifactCleanup(
		eventID,
		mediaprocessing.ArtifactCleanupSource{
			AssetID:                      document.ID,
			ObjectKey:                    document.ObjectKey,
			ImageNormalizedObjectKey:     document.ImageNormalizedObjectKey,
			ImagePublicSliceKey:          document.ImagePublicSliceKey,
			VideoPublicSliceKey:          document.VideoPublicSliceKey,
			CoverPublicSliceKey:          document.CoverPublicSliceKey,
			PreviewTrackManifestSliceKey: document.PreviewTrackManifestSliceKey,
			HistoricalImageArtifacts:     historicalImageArtifacts,
		},
	)
	privateObjectKeys, err := s.reclaimableDiscardedMediaObjectKeys(
		ctx,
		projected.WorkID,
		projected.PrivateObjectKeys,
	)
	if err != nil {
		return mediaprocessing.ArtifactCleanupWork{}, false, err
	}
	return mediaprocessing.ArtifactCleanupWork{
		WorkID:            projected.WorkID,
		PublicSliceKeys:   projected.PublicSliceKeys,
		PublicPrefixes:    projected.PublicPrefixes,
		PrivateObjectKeys: privateObjectKeys,
		PrivatePrefixes:   projected.PrivatePrefixes,
	}, false, nil
}

func (s *MongoMediaStore) reclaimableDiscardedMediaObjectKeys(
	ctx context.Context,
	workID string,
	keys []string,
) ([]string, error) {
	if s.objectFences == nil {
		return nil, errors.New("media object deletion fence is not configured")
	}
	result := make([]string, 0, len(keys))
	seen := make(map[string]struct{}, len(keys))
	for _, rawKey := range keys {
		key := strings.Trim(strings.TrimSpace(rawKey), "/")
		if key == "" {
			continue
		}
		if _, duplicate := seen[key]; duplicate {
			continue
		}
		seen[key] = struct{}{}
		if mediamodel.IsContentAddressedObjectKey(key) {
			claimed, err := s.objectFences.ClaimUnreferencedDeletion(
				ctx,
				key,
				workID,
			)
			if err != nil {
				return nil, fmt.Errorf(
					"claim discarded MediaAsset CAS deletion: %w",
					err,
				)
			}
			if claimed {
				result = append(result, key)
			}
			continue
		}
		count, err := s.assets.CountDocuments(
			ctx,
			bson.M{
				"processingStatus": bson.M{"$ne": "deleted"},
				"$or": bson.A{
					bson.M{"objectKey": key},
					bson.M{"imageNormalizedObjectKey": key},
					bson.M{
						"imageDescriptorRevisions.descriptor.imageNormalizedObjectKey": key,
					},
				},
			},
			options.Count().SetLimit(1),
		)
		if err != nil {
			return nil, fmt.Errorf(
				"check discarded MediaAsset private object references: %w",
				err,
			)
		}
		if count == 0 {
			result = append(result, key)
		}
	}
	return result, nil
}

func (s *MongoMediaStore) MarkMediaAssetArtifactsDeleted(
	ctx context.Context,
	assetID string,
	workID string,
) error {
	if s.objectFences == nil {
		return errors.New("media object deletion fence is not configured")
	}
	if err := s.objectFences.MarkWorkDeleted(ctx, strings.TrimSpace(workID)); err != nil {
		return fmt.Errorf("complete discarded MediaAsset CAS fences: %w", err)
	}
	now := time.Now().UTC()
	result, err := s.assets.UpdateOne(
		ctx,
		bson.M{
			"_id":                strings.TrimSpace(assetID),
			"processingStatus":   "deleted",
			"artifactsDeletedAt": bson.M{"$exists": false},
		},
		bson.M{"$set": bson.M{
			"artifactsDeletedAt": now,
		}},
	)
	if err != nil {
		return fmt.Errorf("mark MediaAsset artifacts deleted: %w", err)
	}
	if result.MatchedCount == 1 {
		return nil
	}
	count, err := s.assets.CountDocuments(
		ctx,
		bson.M{
			"_id":                strings.TrimSpace(assetID),
			"processingStatus":   "deleted",
			"artifactsDeletedAt": bson.M{"$exists": true},
		},
		options.Count().SetLimit(1),
	)
	if err != nil {
		return fmt.Errorf("verify MediaAsset artifact cleanup receipt: %w", err)
	}
	if count != 1 {
		return errors.New("deleted MediaAsset cleanup source is missing")
	}
	return nil
}
