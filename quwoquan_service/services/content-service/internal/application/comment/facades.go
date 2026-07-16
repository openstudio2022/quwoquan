package comment

import "context"

// Facades 是 transport 可见的 Comment application 表面；不包含 PostService
// 兼容方法，也不引用 infrastructure。
type Facades struct {
	CommentCommandFacade
	CommentQueryFacade
}

type CommentCommandFacade interface {
	CreateComment(context.Context, CreateCommentCommand) (CommentCommandResult, error)
	DeleteComment(context.Context, DeleteCommentCommand) (CommentCommandResult, error)
	PinComment(context.Context, ChangeCommentPinCommand) (CommentCommandResult, error)
	UnpinComment(context.Context, ChangeCommentPinCommand) (CommentCommandResult, error)
	BindAttachments(context.Context, BindCommentAttachmentsCommand) (CommentCommandResult, error)
}

type CommentQueryFacade interface {
	ListComments(context.Context, ListCommentsQuery) (CommentPageSlice, error)
	ListReplies(context.Context, ListCommentRepliesQuery) (ReplyPageSlice, error)
	ListByAuthor(context.Context, ListCommentsByAuthorQuery) (AuthorCommentPageSlice, error)
	ListReceivedByPostAuthor(context.Context, ListReceivedCommentsQuery) (ReceivedCommentPageSlice, error)
}

func BindFacades(service *CommentService) *Facades {
	if service == nil {
		return nil
	}
	return &Facades{
		CommentCommandFacade: service,
		CommentQueryFacade:   service,
	}
}
