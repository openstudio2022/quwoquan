package releaseimport

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// UpsertReleaseMediaAssetProjections 把 release media authority 投影进
// media_assets，使 data release 资产可经 ReserveOriginalImageAccessGrant
// 走原图短签授权（DEC-031 research 私有交付的消费面）。授权链其余环节
// （post 可见性经 posts.mediaAssetIds、objectKey 短签）均以此投影为前提。
// 幂等 upsert：同 assetId 重复导入收敛到同一文档。
func UpsertReleaseMediaAssetProjections(
	ctx context.Context,
	coll *mongo.Collection,
	assets map[string]ReleaseMediaAsset,
	ownerID string,
	releaseID string,
	now time.Time,
) (int, error) {
	if coll == nil {
		return 0, fmt.Errorf("media asset projection collection is required")
	}
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" {
		return 0, fmt.Errorf("media asset projection ownerId is required")
	}
	assetIDs := make([]string, 0, len(assets))
	for assetID := range assets {
		assetIDs = append(assetIDs, assetID)
	}
	sort.Strings(assetIDs)
	upserted := 0
	for _, assetID := range assetIDs {
		asset := assets[assetID]
		objectKey := strings.TrimSpace(asset.PrivateObjectKey)
		if objectKey == "" {
			objectKey = strings.TrimSpace(asset.PublicSliceKey)
		}
		if objectKey == "" {
			return upserted, fmt.Errorf(
				"media asset %s has no delivery key for projection",
				assetID,
			)
		}
		update := bson.M{
			"$set": bson.M{
				"ownerId": ownerID,
				// media_assets 对 sourceSessionId 有唯一索引（UGC 每资产一个
				// 上传会话）；release 投影用确定性会话标识满足唯一约束。
				"sourceSessionId":  "data-release/" + assetID,
				"objectKey":        objectKey,
				"sha256":           strings.TrimSpace(asset.SHA256),
				"mediaType":        strings.TrimSpace(asset.Kind),
				"mimeType":         strings.TrimSpace(asset.ContentType),
				"fileSize":         asset.Bytes,
				"accessPolicy":     "referenced_post",
				"processingStatus": "ready",
				"sourceReleaseId":  releaseID,
				"updatedAt":        now,
			},
			"$setOnInsert": bson.M{
				"version":   int64(1),
				"createdAt": now,
			},
		}
		_, err := coll.UpdateOne(
			ctx,
			bson.M{"_id": assetID},
			update,
			options.UpdateOne().SetUpsert(true),
		)
		if err != nil {
			return upserted, fmt.Errorf(
				"upsert media asset projection %s: %w",
				assetID,
				err,
			)
		}
		upserted++
	}
	return upserted, nil
}
