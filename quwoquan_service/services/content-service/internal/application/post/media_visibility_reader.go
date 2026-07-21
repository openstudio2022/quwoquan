package post

import (
	"context"
	"errors"
	"strings"

	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

// MediaAssetVisibilityReader 是 MediaAsset 跨对象原图授权唯一允许使用的
// Post named reader。它只回答某 viewer 是否能读取至少一篇已发布引用 Post。
type MediaAssetVisibilityReader struct {
	posts  postports.MediaReferencedPostReader
	blocks postports.ViewerBlockReader
}

func NewMediaAssetVisibilityReader(
	posts postports.MediaReferencedPostReader,
	blocks postports.ViewerBlockReader,
) *MediaAssetVisibilityReader {
	return &MediaAssetVisibilityReader{posts: posts, blocks: blocks}
}

func (r *MediaAssetVisibilityReader) CanViewerAccessPublishedMedia(
	ctx context.Context,
	mediaAssetID string,
	viewerID string,
) (bool, error) {
	if r == nil || r.posts == nil || r.blocks == nil {
		return false, errors.New("Post media visibility reader is not configured")
	}
	mediaAssetID = strings.TrimSpace(mediaAssetID)
	viewerID = strings.TrimSpace(viewerID)
	if mediaAssetID == "" || viewerID == "" {
		return false, nil
	}

	candidates, err := r.posts.ListPostsReferencingMedia(ctx, mediaAssetID)
	if err != nil {
		return false, err
	}
	viewer := postports.NewViewerContext(postports.NewPersonaID(viewerID))
	for _, candidate := range candidates {
		if !strings.EqualFold(strings.TrimSpace(string(candidate.Status)), "published") {
			continue
		}
		if !viewer.IsOwner(candidate.AuthorPersonaID) {
			blocked, blockErr := r.blocks.IsBlockedBetween(
				ctx,
				viewer.PersonaID(),
				candidate.AuthorPersonaID,
			)
			if blockErr != nil {
				return false, blockErr
			}
			if blocked {
				continue
			}
		}
		if canViewerReadPostDetail(
			postports.PostDetailSlice{
				AuthorPersonaID:  candidate.AuthorPersonaID,
				Status:           candidate.Status,
				Visibility:       candidate.Visibility,
				ModerationStatus: candidate.ModerationStatus,
			},
			viewer,
		) {
			return true, nil
		}
	}
	return false, nil
}
