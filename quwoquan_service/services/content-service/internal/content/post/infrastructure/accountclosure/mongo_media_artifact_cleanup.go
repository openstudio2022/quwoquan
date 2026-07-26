package accountclosure

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/mediaobjectfence"
)

// MediaArtifactClosureRow is the projected media_assets row used to stage
// closed-account artifact cleanup work.
type MediaArtifactClosureRow struct {
	ID                           string                               `bson:"_id"`
	ObjectKey                    string                               `bson:"objectKey"`
	ImageNormalizedObjectKey     string                               `bson:"imageNormalizedObjectKey"`
	ImagePublicSliceKey          string                               `bson:"imagePublicSliceKey"`
	VideoPublicSliceKey          string                               `bson:"videoPublicSliceKey"`
	CoverPublicSliceKey          string                               `bson:"coverPublicSliceKey"`
	PreviewTrackManifestSliceKey string                               `bson:"previewTrackManifestSliceKey"`
	ImageDescriptorRevisions     []mediamodel.ImageDescriptorRevision `bson:"imageDescriptorRevisions"`
}

// MediaArtifactWorkDocument is the durable cleanup work unit for one asset.
type MediaArtifactWorkDocument struct {
	ID                string     `bson:"_id"`
	EventID           string     `bson:"eventId"`
	PublicSliceKeys   []string   `bson:"publicSliceKeys"`
	PublicPrefixes    []string   `bson:"publicPrefixes"`
	PrivateObjectKeys []string   `bson:"privateObjectKeys"`
	PrivatePrefixes   []string   `bson:"privatePrefixes"`
	DoneAt            *time.Time `bson:"doneAt,omitempty"`
	ExpireAt          *time.Time `bson:"expireAt,omitempty"`
}

func collectMediaArtifactClosureRows(
	ctx context.Context,
	collection *mongo.Collection,
	subjectIDs []string,
) ([]MediaArtifactClosureRow, error) {
	cursor, err := collection.Find(
		ctx,
		bson.M{"ownerId": bson.M{"$in": subjectIDs}},
		options.Find().SetProjection(bson.M{
			"_id":                          1,
			"objectKey":                    1,
			"imageNormalizedObjectKey":     1,
			"imagePublicSliceKey":          1,
			"videoPublicSliceKey":          1,
			"coverPublicSliceKey":          1,
			"previewTrackManifestSliceKey": 1,
			"imageDescriptorRevisions":     1,
		}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []MediaArtifactClosureRow
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func (store *MongoStore) stageMediaArtifactCleanup(
	ctx context.Context,
	event UserAccountClosedEvent,
	rows []MediaArtifactClosureRow,
) error {
	if len(rows) == 0 {
		return nil
	}
	models := make([]mongo.WriteModel, 0, len(rows))
	for _, row := range rows {
		document := NewMediaArtifactWorkDocument(event.EventID, row)
		if len(document.PublicSliceKeys) == 0 &&
			len(document.PublicPrefixes) == 0 &&
			len(document.PrivateObjectKeys) == 0 &&
			len(document.PrivatePrefixes) == 0 {
			continue
		}
		models = append(
			models,
			mongo.NewUpdateOneModel().
				SetFilter(bson.M{"_id": document.ID}).
				SetUpdate(bson.M{"$setOnInsert": bson.M{
					"eventId":           document.EventID,
					"publicSliceKeys":   document.PublicSliceKeys,
					"publicPrefixes":    document.PublicPrefixes,
					"privateObjectKeys": document.PrivateObjectKeys,
					"privatePrefixes":   document.PrivatePrefixes,
				}}).
				SetUpsert(true),
		)
	}
	if len(models) == 0 {
		return nil
	}
	if _, err := store.mediaArtifactWork.BulkWrite(
		ctx,
		models,
		options.BulkWrite().SetOrdered(false),
	); err != nil {
		return fmt.Errorf("stage closed-account media artifact cleanup: %w", err)
	}
	return nil
}

// NewMediaArtifactWorkDocument captures all known public/private artifact keys
// and asset-scoped deletion prefixes for one closed-account media asset.
func NewMediaArtifactWorkDocument(
	eventID string,
	row MediaArtifactClosureRow,
) MediaArtifactWorkDocument {
	publicSliceKeys := []string{
		row.ImagePublicSliceKey,
		row.VideoPublicSliceKey,
		row.CoverPublicSliceKey,
		row.PreviewTrackManifestSliceKey,
	}
	privateObjectKeys := []string{
		row.ObjectKey,
		row.ImageNormalizedObjectKey,
	}
	for _, revision := range row.ImageDescriptorRevisions {
		publicSliceKeys = append(
			publicSliceKeys,
			revision.Descriptor.ImagePublicSliceKey,
		)
		privateObjectKeys = append(
			privateObjectKeys,
			revision.Descriptor.ImageNormalizedObjectKey,
		)
	}
	publicSliceKeys = uniqueStrings(publicSliceKeys)
	privateObjectKeys = uniqueStrings(privateObjectKeys)
	publicPrefixes := make([]string, 0, len(publicSliceKeys))
	privatePrefixes := make([]string, 0, len(privateObjectKeys))
	for _, key := range publicSliceKeys {
		if prefix := accountClosurePublicAssetPrefix(key); prefix != "" {
			publicPrefixes = append(publicPrefixes, prefix)
		}
	}
	for _, key := range privateObjectKeys {
		if prefix := accountClosurePrivateAssetPrefix(key); prefix != "" {
			privatePrefixes = append(privatePrefixes, prefix)
		}
	}
	return MediaArtifactWorkDocument{
		ID:                mediaArtifactWorkID(eventID, row.ID),
		EventID:           strings.TrimSpace(eventID),
		PublicSliceKeys:   publicSliceKeys,
		PublicPrefixes:    uniqueStrings(publicPrefixes),
		PrivateObjectKeys: privateObjectKeys,
		PrivatePrefixes:   uniqueStrings(privatePrefixes),
	}
}

func accountClosurePublicAssetPrefix(key string) string {
	key = strings.Trim(strings.TrimSpace(key), "/")
	const marker = "/s/asset/"
	index := strings.Index(key, marker)
	if index < 0 {
		return ""
	}
	assetStart := index + len(marker)
	assetEnd := strings.Index(key[assetStart:], "/")
	if assetEnd <= 0 {
		return ""
	}
	assetID := key[assetStart : assetStart+assetEnd]
	if assetID == "" || strings.ContainsAny(assetID, "\\?#") ||
		strings.Contains(assetID, "..") {
		return ""
	}
	return key[:assetStart+assetEnd+1]
}

func accountClosurePrivateAssetPrefix(key string) string {
	key = strings.Trim(strings.TrimSpace(key), "/")
	for _, root := range []string{
		"media/processed/image/",
		"media/processed/video/",
	} {
		if !strings.HasPrefix(key, root) {
			continue
		}
		remainder := strings.TrimPrefix(key, root)
		segmentEnd := strings.Index(remainder, "/")
		if segmentEnd <= 0 {
			return ""
		}
		assetID := remainder[:segmentEnd]
		if strings.ContainsAny(assetID, "\\?#") ||
			strings.Contains(assetID, "..") {
			return ""
		}
		return root + assetID + "/"
	}
	return ""
}

func (store *MongoStore) PendingMediaArtifactCleanup(
	ctx context.Context,
	eventID string,
	limit int64,
) ([]MediaArtifactCleanupWork, error) {
	if limit <= 0 {
		limit = 200
	}
	cursor, err := store.mediaArtifactWork.Find(
		ctx,
		bson.M{
			"eventId": eventID,
			"doneAt":  bson.M{"$exists": false},
		},
		options.Find().
			SetSort(bson.D{{Key: "_id", Value: 1}}).
			SetLimit(limit),
	)
	if err != nil {
		return nil, fmt.Errorf(
			"read UserAccountClosed media artifact work: %w",
			err,
		)
	}
	defer cursor.Close(ctx)
	var documents []MediaArtifactWorkDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, fmt.Errorf(
			"decode UserAccountClosed media artifact work: %w",
			err,
		)
	}
	workItems := make([]MediaArtifactCleanupWork, 0, len(documents))
	for _, document := range documents {
		unreferenced, err := store.reclaimableMediaObjectKeys(
			ctx,
			document.ID,
			document.PrivateObjectKeys,
		)
		if err != nil {
			return nil, err
		}
		workItems = append(workItems, MediaArtifactCleanupWork{
			ID:                document.ID,
			PublicSliceKeys:   uniqueStrings(document.PublicSliceKeys),
			PublicPrefixes:    uniqueStrings(document.PublicPrefixes),
			PrivateObjectKeys: unreferenced,
			PrivatePrefixes:   uniqueStrings(document.PrivatePrefixes),
		})
	}
	return workItems, nil
}

func (store *MongoStore) reclaimableMediaObjectKeys(
	ctx context.Context,
	workID string,
	keys []string,
) ([]string, error) {
	if store.objectFences == nil {
		return nil, errors.New("media object deletion fence is not configured")
	}
	result := make([]string, 0, len(keys))
	for _, key := range uniqueStrings(keys) {
		if mediaobjectfence.IsContentAddressedObjectKey(key) {
			claimed, claimErr := store.objectFences.ClaimUnreferencedDeletion(
				ctx,
				key,
				workID,
			)
			if claimErr != nil {
				return nil, fmt.Errorf(
					"claim closed-account CAS object deletion: %w",
					claimErr,
				)
			}
			if claimed {
				result = append(result, key)
			}
			continue
		}
		count, err := store.db.Collection("media_assets").CountDocuments(
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
				"check closed-account media object references: %w",
				err,
			)
		}
		if count == 0 {
			result = append(result, key)
		}
	}
	return result, nil
}

func (store *MongoStore) MarkMediaArtifactCleanupDone(
	ctx context.Context,
	eventID string,
	workID string,
) error {
	if store.objectFences == nil {
		return errors.New("media object deletion fence is not configured")
	}
	if err := store.objectFences.MarkWorkDeleted(ctx, workID); err != nil {
		return fmt.Errorf(
			"complete closed-account CAS object deletion fences: %w",
			err,
		)
	}
	now := time.Now().UTC()
	result, err := store.mediaArtifactWork.UpdateOne(
		ctx,
		bson.M{
			"_id":     strings.TrimSpace(workID),
			"eventId": strings.TrimSpace(eventID),
			"doneAt":  bson.M{"$exists": false},
		},
		bson.M{"$set": bson.M{
			"doneAt":   now,
			"expireAt": now.Add(failureRetention),
		}},
	)
	if err != nil {
		return fmt.Errorf(
			"complete UserAccountClosed media artifact work: %w",
			err,
		)
	}
	if result.MatchedCount != 1 {
		return errors.New("UserAccountClosed media artifact work is missing")
	}
	return nil
}

func mediaArtifactWorkID(eventID string, assetID string) string {
	return irreversibleDigest(
		strings.TrimSpace(eventID) + "\x00" + strings.TrimSpace(assetID),
	)
}
