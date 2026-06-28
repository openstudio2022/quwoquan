package post

import (
	"context"
	"fmt"
	rterr "quwoquan_service/runtime/errors"
	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/services/content-service/internal/application/identity"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"strings"
	"time"
)

func (s *PostService) InitMediaUpload(ctx context.Context, userID, mediaType, assetScope, sourceKind string) map[string]any {
	now := time.Now().UTC()
	if userID == "" {
		userID = identity.AnonymousFallbackSubAccountID
	}
	mediaID := fmt.Sprintf("media_%d", now.UnixNano())
	sessionID := fmt.Sprintf("upload_%d", now.UnixNano())
	assetScope = defaultString(strings.TrimSpace(assetScope), "draft")
	mediaType = defaultString(strings.TrimSpace(mediaType), "image")
	objectKey := mediaObjectKey(assetScope, userID, sessionID, mediaID, mediaType)
	uploadURL := mediaURL(s.mediaUploadBase, "upload/"+objectKey)
	if s.mediaStore != nil {
		if session, err := s.mediaStore.InitUpload(ctx, runtimemedia.InitUploadOpts{
			Category:    runtimemedia.CategoryPost,
			OwnerID:     userID,
			FileName:    "original." + mediaFileExt(mediaType),
			ContentType: mediaMimeType(mediaType),
			FileSize:    1,
		}); err == nil && session != nil {
			sessionID = session.SessionID
			objectKey = session.OSSKey
			uploadURL = session.PresignURL
		}
	}
	asset := postmodel.MediaAsset{
		ID:               mediaID,
		OwnerId:          userID,
		AssetScope:       assetScope,
		Type:             mediaType,
		OriginUrl:        mediaURL(s.mediaUploadBase, objectKey),
		ObjectKey:        objectKey,
		Sha256:           "",
		SourceKind:       defaultString(strings.TrimSpace(sourceKind), "user_upload"),
		MimeType:         mediaMimeType(mediaType),
		Status:           "pending",
		CoverStrategy:    "first_frame",
		ModerationStatus: "pending",
		CreatedAt:        now,
		UpdatedAt:        now,
	}
	s.mu.Lock()
	s.mediaAssets[mediaID] = asset
	s.uploadSession[sessionID] = mediaID
	s.mu.Unlock()
	return map[string]any{
		"sessionId":          sessionID,
		"mediaId":            mediaID,
		"uploadUrl":          uploadURL,
		"presignUrl":         uploadURL,
		"objectKey":          objectKey,
		"temporaryObjectKey": objectKey,
		"uploaderId":         userID,
		"assetScope":         asset.AssetScope,
	}
}

func (s *PostService) CompleteMediaUpload(ctx context.Context, sessionID string) (*postmodel.MediaAsset, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	mediaID := s.uploadSession[strings.TrimSpace(sessionID)]
	if mediaID == "" {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"上传会话不存在",
			"upload session not found",
		)
	}
	asset, ok := s.mediaAssets[mediaID]
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"媒体不存在",
			"media not found",
		)
	}
	asset.Status = "ready"
	if asset.ObjectKey == "" {
		asset.ObjectKey = mediaObjectKey(asset.AssetScope, asset.OwnerId, sessionID, mediaID, asset.Type)
	}
	asset.CdnUrl = mediaURL(s.mediaCDNBase, asset.ObjectKey)
	asset.ThumbnailUrl = asset.CdnUrl + "?variant=thumb"
	if s.mediaStore != nil {
		if mediaAsset, err := s.mediaStore.CompleteUpload(ctx, strings.TrimSpace(sessionID), runtimemedia.CompleteUploadOpts{
			DurationMs:     asset.DurationMs,
			Width:          int(asset.Width),
			Height:         int(asset.Height),
			Metadata:       map[string]any{"contentMediaId": mediaID},
			DeclaredSha256: asset.Sha256,
		}); err == nil && mediaAsset != nil {
			asset.ObjectKey = mediaAsset.OSSKey
			asset.CdnUrl = mediaAsset.CDNURL
			asset.OriginUrl = mediaAsset.CDNURL
			asset.Sha256 = strings.TrimSpace(mediaAsset.Sha256)
			if strings.TrimSpace(mediaAsset.AssetID) != "" {
				asset.SourceUrl = mediaAsset.AssetID
			}
			if mediaAsset.FileSize > 0 {
				asset.FileSizeBytes = mediaAsset.FileSize
			}
		}
	}
	if asset.Type == "video" {
		asset.DurationMs = 15000
		asset.Width = 1080
		asset.Height = 1920
		asset.FileSizeBytes = 5 * 1024 * 1024
	} else {
		asset.Width = 1080
		asset.Height = 1080
		asset.FileSizeBytes = 500 * 1024
		asset.DominantColor = "#1A1A1A"
		asset.Lqip = map[string]any{"kind": "color", "value": asset.DominantColor, "w": 16, "h": 16}
		asset.ContentProfile = map[string]any{"hasAlpha": false, "contentClass": "photo", "edgeDensityScore": 0.24, "flatColorScore": 0.18, "textLikeScore": 0.03}
		asset.DerivativePolicyVersion = fmt.Sprintf("%d", time.Now().UTC().Unix())
		asset.Derivatives = map[string]any{"job": map[string]any{"jobId": "img_derivative_" + mediaID, "status": "ready", "retryable": true}, "variants": []map[string]any{{"displayUse": "feedCard", "qualityTier": "standard", "format": "webp", "url": asset.CdnUrl + "?use=feedCard&tier=standard&fmt=webp"}}}
		asset.AccessPolicy = map[string]any{"originalAllowed": true, "allowOriginalView": true, "allowOriginalSave": true, "originalTtlSeconds": 300, "originalSizeBytes": asset.FileSizeBytes, "originalSha256": asset.Sha256}
		asset.OriginalAccess = map[string]any{"available": true, "requiresExplicitAction": true, "sizeBytes": asset.FileSizeBytes, "format": asset.MimeType, "ttlSeconds": 300}
	}
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[mediaID] = asset
	return &asset, nil
}

func (s *PostService) BindMediaAssetsToPost(_ context.Context, postID string, assetIDs []string) (map[string]any, error) {
	postID = strings.TrimSpace(postID)
	if postID == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "postId 不能为空", "missing postId")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	bound := []string{}
	for _, rawID := range assetIDs {
		assetID := strings.TrimSpace(rawID)
		if assetID == "" {
			continue
		}
		asset, ok := s.mediaAssets[assetID]
		if !ok {
			return nil, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"),
				"素材不存在",
				"media asset not found",
			)
		}
		if asset.Status != "" && asset.Status != "ready" {
			return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "素材尚未就绪", "media asset not ready")
		}
		asset.PostId = postID
		asset.AssetScope = "published"
		asset.UpdatedAt = time.Now().UTC()
		s.mediaAssets[assetID] = asset
		bound = append(bound, assetID)
	}
	return map[string]any{
		"postId":        postID,
		"boundAssetIds": bound,
		"boundCount":    len(bound),
	}, nil
}

func (s *PostService) BindMediaAssetsToComment(ctx context.Context, commentID, userID string, assetIDs []string) (map[string]any, error) {
	commentID = strings.TrimSpace(commentID)
	if commentID == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "commentId 不能为空", "missing commentId")
	}
	userID = strings.TrimSpace(userID)

	comment, found := s.commentStore.FindByID(ctx, commentID)
	if !found || strings.TrimSpace(comment.Status) == "deleted" {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_not_found"),
			"评论不存在",
			"comment not found",
		)
	}
	authorID := strings.TrimSpace(comment.AuthorId)
	if userID != "" && authorID != "" && authorID != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "comment_forbidden_update"),
			"无权更新此评论附件",
			"comment author mismatch",
		)
	}
	boundIDs, attachments, err := s.prepareCommentAttachments(comment.PostId, authorID, assetIDs)
	if err != nil {
		return nil, err
	}
	if _, err := s.commentStore.SetAttachments(ctx, commentID, boundIDs, attachments); err != nil {
		return nil, rterr.NewUnavailable(
			rterr.ModuleContent, "附件绑定失败，请稍后重试", "comment set attachments failed: "+err.Error(),
		)
	}
	return map[string]any{
		"commentId":     commentID,
		"boundAssetIds": boundIDs,
		"boundCount":    len(boundIDs),
		"attachments":   attachments,
	}, nil
}

func (s *PostService) AbortMediaUpload(_ context.Context, sessionID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.uploadSession, strings.TrimSpace(sessionID))
	return nil
}

func (s *PostService) GetMediaAsset(mediaID string) (*postmodel.MediaAsset, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	asset, ok := s.mediaAssets[strings.TrimSpace(mediaID)]
	if !ok {
		return nil, false
	}
	cp := asset
	return &cp, true
}

func (s *PostService) SelectAutoVideoCover(_ context.Context, mediaID string) (*postmodel.MediaAsset, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	asset, ok := s.mediaAssets[strings.TrimSpace(mediaID)]
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"媒体不存在",
			"media not found",
		)
	}
	asset.CoverStrategy = "first_frame"
	asset.ManualCoverAssetId = ""
	asset.CoverFrameTimeMs = 0
	if strings.TrimSpace(asset.ThumbnailUrl) == "" {
		asset.ThumbnailUrl = deriveVideoThumbnailURL(mediaAssetDisplayURL(asset), 0)
	}
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[asset.ID] = asset
	cp := asset
	return &cp, nil
}

func (s *PostService) SelectManualVideoCover(_ context.Context, mediaID, coverAssetID string, coverFrameTimeMs int64) (*postmodel.MediaAsset, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	asset, ok := s.mediaAssets[strings.TrimSpace(mediaID)]
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"媒体不存在",
			"media not found",
		)
	}
	asset.CoverStrategy = "manual"
	asset.ManualCoverAssetId = strings.TrimSpace(coverAssetID)
	asset.CoverFrameTimeMs = coverFrameTimeMs
	if asset.CoverFrameTimeMs < 0 {
		asset.CoverFrameTimeMs = 0
	}
	if asset.ManualCoverAssetId != "" {
		coverAsset, coverOK := s.mediaAssets[asset.ManualCoverAssetId]
		if !coverOK {
			return nil, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"),
				"封面素材不存在",
				"manual cover asset not found",
			)
		}
		asset.ThumbnailUrl = mediaAssetDisplayURL(coverAsset)
	} else {
		asset.ThumbnailUrl = deriveVideoThumbnailURL(mediaAssetDisplayURL(asset), asset.CoverFrameTimeMs)
	}
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[asset.ID] = asset
	cp := asset
	return &cp, nil
}

func mediaAssetDisplayURL(asset postmodel.MediaAsset) string {
	for _, candidate := range []string{
		asset.ThumbnailUrl,
		asset.CdnUrl,
		asset.OriginUrl,
		asset.SourceUrl,
	} {
		if trimmed := strings.TrimSpace(candidate); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
