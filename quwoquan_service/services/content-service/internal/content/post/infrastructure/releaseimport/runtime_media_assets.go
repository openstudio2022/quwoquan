package releaseimport

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
)

// InsertReleaseMediaAssetProjections 把一个 release 的 media authority create-once 写入
// 调用方提供的 candidate-scoped collection。ctx 必须是 Stage 的
// mongo.SessionContext（v2 以 context.Context 暴露），使 Post、outbox、媒体和
// verified candidate state 在同一事务中提交。幂等重放只接受相同 release 绑定。
func InsertReleaseMediaAssetProjections(
	ctx context.Context,
	coll *mongo.Collection,
	assets map[string]ReleaseMediaAsset,
	environment string,
	ownerID string,
	releaseID string,
	manifestDigest string,
	now time.Time,
) (int, error) {
	if coll == nil {
		return 0, fmt.Errorf("media asset projection collection is required")
	}
	environment = strings.TrimSpace(environment)
	ownerID = strings.TrimSpace(ownerID)
	releaseID = strings.TrimSpace(releaseID)
	manifestDigest = strings.TrimSpace(manifestDigest)
	if environment == "" || ownerID == "" || releaseID == "" || manifestDigest == "" {
		return 0, fmt.Errorf("media asset candidate projection binding is incomplete")
	}
	assetIDs := make([]string, 0, len(assets))
	for assetID := range assets {
		assetIDs = append(assetIDs, assetID)
	}
	sort.Strings(assetIDs)
	projected := 0
	for _, assetID := range assetIDs {
		asset := assets[assetID]
		objectKey := strings.TrimSpace(asset.PrivateObjectKey)
		if objectKey == "" {
			objectKey = strings.TrimSpace(asset.PublicSliceKey)
		}
		if objectKey == "" {
			return projected, fmt.Errorf(
				"media asset %s has no delivery key for projection",
				assetID,
			)
		}
		document := bson.M{
			"_id":         candidateMediaAssetDocumentID(environment, ownerID, releaseID, manifestDigest, assetID),
			"environment": environment, "sourceOwner": ownerID,
			"releaseId": releaseID, "manifestDigest": manifestDigest,
			"assetId": assetID, "ownerId": ownerID,
			"sourceSessionId": "data-release/" + assetID,
			"objectKey":       objectKey, "sha256": strings.TrimSpace(asset.SHA256),
			"mediaType": strings.TrimSpace(asset.Kind), "mimeType": strings.TrimSpace(asset.ContentType),
			"fileSize": asset.Bytes, "accessPolicy": "referenced_post",
			"processingStatus": "ready", "sourceReleaseId": releaseID,
			"version": int64(1), "createdAt": now, "updatedAt": now,
		}
		digest, err := canonicalDocumentDigest(document, "documentDigest")
		if err != nil {
			return projected, fmt.Errorf("digest media asset projection %s: %w", assetID, err)
		}
		document["documentDigest"] = digest
		_, err = coll.InsertOne(ctx, document)
		if err != nil {
			return projected, fmt.Errorf(
				"upsert media asset projection %s: %w",
				assetID,
				err,
			)
		}
		projected++
	}
	return projected, nil
}

func ValidateReleaseMediaAssetProjectionClosure(
	ctx context.Context,
	coll *mongo.Collection,
	assets map[string]ReleaseMediaAsset,
	environment string,
	ownerID string,
	releaseID string,
	manifestDigest string,
	createdAt time.Time,
) error {
	for assetID, asset := range assets {
		objectKey := strings.TrimSpace(asset.PrivateObjectKey)
		if objectKey == "" {
			objectKey = strings.TrimSpace(asset.PublicSliceKey)
		}
		expected := bson.M{
			"_id":         candidateMediaAssetDocumentID(environment, ownerID, releaseID, manifestDigest, assetID),
			"environment": environment, "sourceOwner": ownerID,
			"releaseId": releaseID, "manifestDigest": manifestDigest,
			"assetId": assetID, "ownerId": ownerID,
			"sourceSessionId": "data-release/" + assetID,
			"objectKey":       objectKey, "sha256": strings.TrimSpace(asset.SHA256),
			"mediaType": strings.TrimSpace(asset.Kind), "mimeType": strings.TrimSpace(asset.ContentType),
			"fileSize": asset.Bytes, "accessPolicy": "referenced_post",
			"processingStatus": "ready", "sourceReleaseId": releaseID,
			"version": int64(1), "createdAt": createdAt, "updatedAt": createdAt,
		}
		if err := verifyCandidateDocument(ctx, coll, expected); err != nil {
			return fmt.Errorf("verify candidate media %q: %w", assetID, err)
		}
	}
	count, err := coll.CountDocuments(ctx, bson.M{
		"environment": environment, "sourceOwner": ownerID,
		"releaseId": releaseID, "manifestDigest": manifestDigest,
	})
	if err != nil {
		return fmt.Errorf("count candidate media closure: %w", err)
	}
	if count != int64(len(assets)) {
		return fmt.Errorf("GATE_BLOCK: candidate media closure count drift")
	}
	return nil
}
