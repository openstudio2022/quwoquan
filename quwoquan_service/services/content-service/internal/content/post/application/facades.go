package post

import (
	"context"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postsemantic "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
)

// Facades 是 transport 的对象应用入口。它只组合细粒度 Facade，不暴露
// PostService、generic data access 或基础设施实现。
type Facades struct {
	PostPublicationCommandFacade
	PostLifecycleCommandFacade
	PostModerationDecisionCommandFacet
	PostReadFacade
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
		PostPublicationCommandFacade:       service,
		PostLifecycleCommandFacade:         service,
		PostModerationDecisionCommandFacet: service,
		PostReadFacade:                     service,
		ContentUtilityQueryFacade:          service,
		SemanticGovernanceCommandFacade:    service,
	}
}
