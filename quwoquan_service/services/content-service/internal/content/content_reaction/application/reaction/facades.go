package reaction

import "context"

// Facades 是未来 transport/composition 可见的 ContentReaction 对象入口。
type Facades struct {
	ContentReactionCommandFacet
	ContentReactionQueryFacet
}

type ContentReactionCommandFacet interface {
	LikePost(context.Context, LikePostCommand) (ContentReactionCommandResult, error)
	UnlikePost(context.Context, UnlikePostCommand) (ContentReactionCommandResult, error)
	ReactToComment(context.Context, ReactToCommentCommand) (CommentReactionCommandResult, error)
}

type ContentReactionQueryFacet interface {
	GetContentReactionState(
		context.Context,
		GetContentReactionStateQuery,
	) (ContentReactionStateSlice, error)
}

func BindFacades(service *Service) *Facades {
	if service == nil {
		return nil
	}
	return &Facades{
		ContentReactionCommandFacet: service,
		ContentReactionQueryFacet:   service,
	}
}
