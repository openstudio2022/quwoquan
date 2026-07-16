package persistence

import (
	"context"
	"fmt"
	"strings"

	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type commentMediaAssetReader interface {
	FindMediaAssetsByIDs(context.Context, []string) (map[string]mediaapp.MediaAssetSlice, error)
}

type CommentAttachmentReader struct {
	assets  commentMediaAssetReader
	objects mediaapp.MediaObjectGateway
}

func NewCommentAttachmentReader(assets commentMediaAssetReader, objects mediaapp.MediaObjectGateway) *CommentAttachmentReader {
	if assets == nil || objects == nil {
		panic("CommentAttachmentReader requires MediaAsset reader and object gateway")
	}
	return &CommentAttachmentReader{assets: assets, objects: objects}
}

func (r *CommentAttachmentReader) ValidateCommentAttachments(ctx context.Context, actorID string, mediaIDs []string) error {
	actorID = strings.TrimSpace(actorID)
	assets, err := r.assets.FindMediaAssetsByIDs(ctx, mediaIDs)
	if err != nil {
		return fmt.Errorf("read Comment attachment ownership: %w", err)
	}
	for _, rawID := range mediaIDs {
		mediaID := strings.TrimSpace(rawID)
		if mediaID == "" {
			return contentgenerated.AppErrorFromInvalidArgument("empty Comment attachment id")
		}
		asset, found := assets[mediaID]
		if !found {
			return contentgenerated.AppErrorFromInvalidArgument(fmt.Sprintf("Comment attachment %s is unavailable", mediaID))
		}
		if asset.ProcessingStatus != mediamodel.ProcessingStatusReady {
			return contentgenerated.AppErrorFromInvalidArgument(fmt.Sprintf("Comment attachment %s is not ready", mediaID))
		}
		if strings.TrimSpace(asset.OwnerID) != actorID {
			return contentgenerated.AppErrorFromCommentForbiddenDelete(fmt.Sprintf("Comment attachment %s is not owned by actor", mediaID))
		}
	}
	return nil
}

func (r *CommentAttachmentReader) ReadCommentAttachments(ctx context.Context, mediaIDs []string) (map[string]commentmodel.AttachmentProjection, error) {
	assets, err := r.assets.FindMediaAssetsByIDs(ctx, mediaIDs)
	if err != nil {
		return nil, fmt.Errorf("read Comment attachments: %w", err)
	}
	projections := make(map[string]commentmodel.AttachmentProjection, len(mediaIDs))
	for _, rawID := range mediaIDs {
		mediaID := strings.TrimSpace(rawID)
		if mediaID == "" {
			continue
		}
		asset, found := assets[mediaID]
		if !found || asset.ProcessingStatus != mediamodel.ProcessingStatusReady {
			projections[mediaID] = commentmodel.AttachmentProjection{MediaID: mediaID}
			continue
		}
		deliveryURL, err := r.objects.DeliveryURL(ctx, asset.ObjectKey)
		if err != nil {
			return nil, fmt.Errorf("sign Comment attachment %s: %w", mediaID, err)
		}
		projections[mediaID] = commentmodel.AttachmentProjection{
			MediaID: mediaID, MediaType: asset.ContentType, URL: deliveryURL, Available: deliveryURL != "",
		}
	}
	return projections, nil
}

var _ commentports.AttachmentReader = (*CommentAttachmentReader)(nil)
