package persistence

import (
	"context"

	shareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type ShareablePostReader struct {
	reader postports.PostDetailReader
}

func NewShareablePostReader(reader postports.PostDetailReader) *ShareablePostReader {
	if reader == nil {
		panic("OutboundShareFact ShareablePostReader requires PostDetailReader")
	}
	return &ShareablePostReader{reader: reader}
}

func (r *ShareablePostReader) FindShareablePost(
	ctx context.Context,
	postID string,
) (shareapp.ShareablePostSlice, bool, error) {
	detail, found, err := r.reader.FindPostDetail(ctx, postports.NewPostID(postID))
	if err != nil || !found {
		return shareapp.ShareablePostSlice{}, found, err
	}
	return shareapp.ShareablePostSlice{
		PostID: string(detail.PostID),
		Status: string(detail.Status),
	}, true, nil
}
