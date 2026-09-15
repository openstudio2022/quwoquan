package collection

import (
	"context"
	"errors"
	rterr "quwoquan_service/runtime/errors"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// PublishedPostQuery 是 Post Facade 已公开的查询契约，不能接入私有 persistence。
type PublishedPostQuery interface {
	GetPost(context.Context, postports.PostDetailQuery) (postports.PostDetailSlice, error)
}
type CanonicalPostReader struct{ Query PublishedPostQuery }

func (r CanonicalPostReader) ReadVisible(ctx context.Context, id, viewer string) (Member, bool, error) {
	if r.Query == nil {
		return Member{}, false, errors.New("Post query not configured")
	}
	slice, err := r.Query.GetPost(ctx, postports.NewPostDetailQuery(postports.NewPostID(id), postports.NewViewerContext(postports.NewPersonaID(viewer))))
	if err != nil {
		var appErr *rterr.AppError
		if errors.As(err, &appErr) && (appErr.HTTPStatus == 404 || appErr.HTTPStatus == 410 || appErr.HTTPStatus == 403) {
			return Member{}, false, nil
		}
		return Member{}, false, err
	}
	if string(slice.Status) != "published" {
		return Member{}, false, nil
	}
	return Member{PostID: id, ContentType: string(slice.ContentType), Title: slice.Title}, true, nil
}
