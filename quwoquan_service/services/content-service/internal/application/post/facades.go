package post

import (
	"context"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postsemantic "quwoquan_service/services/content-service/internal/domain/post/semantic"
)

// Facades 是 transport 的对象应用入口。它只组合细粒度 Facade，不暴露
// PostService、generic data access 或基础设施实现。
type Facades struct {
	PostPublicationCommandFacade
	PostLifecycleCommandFacade
	PostReadFacade
	ProfileInteractionFacade
	ContentUtilityQueryFacade
	SemanticGovernanceCommandFacade
}

type PostPublicationCommandFacade interface {
	SubmitPostPublication(
		context.Context,
		SubmitPostPublicationCommand,
	) (PostPublicationReceipt, error)
}

type PostLifecycleCommandFacade interface {
	UpdatePostSettings(context.Context, string, string, map[string]any) (*postmodel.Post, error)
	PromotePostToWork(context.Context, string, string, map[string]any) (*postmodel.Post, error)
	DeletePost(context.Context, string, string) error
}

type PostReadFacade interface {
	GetPostOrTombstone(context.Context, string) (*postmodel.Post, bool, bool)
	SearchPosts(context.Context, SearchPostsRequest) ([]postmodel.PostSearchItemView, string, error)
	GetHelperRead(context.Context, string) (map[string]any, error)
}

type ProfileInteractionFacade interface {
	ListProfileInteractionActivities(context.Context, string, string, string, string, int) ([]postmodel.ProfileInteractionActivityView, string, bool, error)
	ListProfileShareInteractions(context.Context, string, string, string, int) ([]postmodel.ProfileInteractionActivityView, string, bool, error)
	MarkProfileShareInteractionState(context.Context, string, string, string) error
}

type ContentUtilityQueryFacade interface {
	GenerateArticleSummary(string, string) string
	GetAppConfig() map[string]any
	GetCounters(context.Context, string) (map[string]any, error)
}

type SemanticGovernanceCommandFacade interface {
	ApplySemanticMentionGovernanceEvent(context.Context, postsemantic.GovernanceEvent) (SemanticMentionReprojectionReport, error)
}

// BindFacades 将对象应用实现显式绑定到 transport 所需的细粒度入口。
func BindFacades(service *PostService) *Facades {
	if service == nil {
		return nil
	}
	return &Facades{
		PostPublicationCommandFacade:    service,
		PostLifecycleCommandFacade:      service,
		PostReadFacade:                  service,
		ProfileInteractionFacade:        service,
		ContentUtilityQueryFacade:       service,
		SemanticGovernanceCommandFacade: service,
	}
}
