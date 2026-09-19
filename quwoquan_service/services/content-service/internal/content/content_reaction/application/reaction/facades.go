package reaction

import "context"
import reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"

// Facades 是未来 transport/composition 可见的 ContentReaction 对象入口。
type Facades struct {
	ContentReactionCommandFacet
	ContentReactionQueryFacet
}

type ContentReactionCommandFacet interface {
	LikePost(context.Context, LikePostCommand) (ContentReactionCommandResult, error)
	UnlikePost(context.Context, UnlikePostCommand) (ContentReactionCommandResult, error)
	ReactToComment(context.Context, ReactToCommentCommand) (CommentReactionCommandResult, error)
	RecoverCommand(context.Context, RecoverContentReactionCommand) (ContentReactionCommandRecoveryResult, error)
	FinalizeExpiredCommand(context.Context, FinalizeExpiredContentReactionCommand) (ContentReactionCommandRecoveryResult, error)
}

type ContentReactionQueryFacet interface {
	GetContentReactionMutationBasis(context.Context, GetContentReactionMutationBasisQuery) (ContentReactionMutationBasisSlice, error)
	GetContentReactionPresentation(context.Context, reactiondomain.Identity) (ContentReactionPresentationSlice, error)
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
