package post

import (
	"context"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type BindMediaAssetsToPostResult struct {
	PostID        string   `json:"postId"`
	BoundAssetIDs []string `json:"boundAssetIds"`
	BoundCount    int      `json:"boundCount"`
}

type bindMediaAssetsToPostPayload struct {
	PostID   string   `json:"postId"`
	AssetIDs []string `json:"assetIds"`
}

func (s *PostService) BindMediaAssetsToPost(ctx context.Context, postID, ownerID string, assetIDs []string) (BindMediaAssetsToPostResult, error) {
	postID = strings.TrimSpace(postID)
	if postID == "" {
		return BindMediaAssetsToPostResult{}, rterr.NewInvalidArgument(rterr.ModuleContent, "postId 不能为空", "missing postId")
	}
	post, ok := s.store.FindByID(ctx, postID)
	if !ok {
		return BindMediaAssetsToPostResult{}, rterr.NewAppError(rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"), "内容不存在", "post not found")
	}
	if err := requireMediaOwner(post.AuthorId, ownerID); err != nil {
		return BindMediaAssetsToPostResult{}, err
	}
	if s.mediaAssetBindings == nil {
		return BindMediaAssetsToPostResult{}, rterr.NewUnavailable(rterr.ModuleContent, "媒体读取服务未配置", "MediaAsset binding reader is required")
	}
	assets, err := s.mediaAssetBindings.FindMediaAssetsForBinding(ctx, assetIDs)
	if err != nil {
		return BindMediaAssetsToPostResult{}, rterr.NewUnavailable(rterr.ModuleContent, "读取媒体素材失败", err.Error())
	}
	bound := make([]string, 0, len(assetIDs))
	seen := make(map[string]struct{}, len(assetIDs))
	for _, rawID := range assetIDs {
		assetID := strings.TrimSpace(rawID)
		if assetID == "" {
			return BindMediaAssetsToPostResult{}, rterr.NewInvalidArgument(rterr.ModuleContent, "素材 ID 不能为空", "empty media asset id")
		}
		if _, duplicate := seen[assetID]; duplicate {
			continue
		}
		seen[assetID] = struct{}{}
		asset, ok := assets[assetID]
		if !ok {
			return BindMediaAssetsToPostResult{}, rterr.NewAppError(rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"), "素材不存在", "media asset not found")
		}
		if err := requireMediaOwner(asset.OwnerID, ownerID); err != nil {
			return BindMediaAssetsToPostResult{}, err
		}
		if !asset.Ready {
			return BindMediaAssetsToPostResult{}, rterr.NewInvalidArgument(rterr.ModuleContent, "素材尚未就绪", "media asset not ready")
		}
		bound = append(bound, assetID)
	}
	if len(bound) == 0 {
		return BindMediaAssetsToPostResult{}, rterr.NewInvalidArgument(rterr.ModuleContent, "至少选择一个媒体素材", "at least one media asset is required")
	}
	now := time.Now().UTC()
	expectedVersion := post.Version
	post.MediaAssetIds = append([]string(nil), bound...)
	post.UpdatedAt = now
	post.ContentDigest = postContentDigest(post)
	if _, err = s.commitPostCommand(
		ctx, post, expectedVersion, "BindMediaAssetsToPost",
		bindMediaAssetsToPostPayload{PostID: postID, AssetIDs: bound},
		"PostMediaAssetsBound", bindMediaAssetsToPostPayload{PostID: postID, AssetIDs: bound}, now,
	); err != nil {
		return BindMediaAssetsToPostResult{}, err
	}
	return BindMediaAssetsToPostResult{PostID: postID, BoundAssetIDs: bound, BoundCount: len(bound)}, nil
}

func requireMediaOwner(resourceOwnerID, actorID string) error {
	resourceOwnerID = strings.TrimSpace(resourceOwnerID)
	actorID = strings.TrimSpace(actorID)
	if actorID == "" {
		return contentgenerated.AppErrorFromUnauthorized("media operation requires a verified actor")
	}
	if resourceOwnerID == "" || resourceOwnerID != actorID {
		return contentgenerated.AppErrorFromForbiddenEdit("media owner mismatch")
	}
	return nil
}
