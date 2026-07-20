package moderation

import "context"

type Facades struct {
	PostModerationCaseCommandFacet
	PostModerationCaseQueryFacet
	PublicationEligibilityQueryFacet
}

type PostModerationCaseCommandFacet interface {
	OpenPostModerationCase(
		context.Context,
		OpenPostModerationCaseCommand,
	) (PostModerationCaseCommandResult, error)
	ReviewPostModerationCase(
		context.Context,
		ReviewPostModerationCaseCommand,
	) (PostModerationCaseCommandResult, error)
	DecidePostModerationCase(
		context.Context,
		DecidePostModerationCaseCommand,
	) (PostModerationCaseCommandResult, error)
	SupersedePostModerationCase(
		context.Context,
		SupersedePostModerationCaseCommand,
	) (PostModerationCaseCommandResult, error)
}

type PublicationEligibilityQueryFacet interface {
	PublicationEligibilityApplicationReader
}

type PostModerationCaseQueryFacet interface {
	GetCurrentPostModerationCase(
		context.Context,
		GetCurrentPostModerationCaseQuery,
	) (PostModerationCaseOpsSlice, error)
}

func BindFacades(service *ModerationService) *Facades {
	if service == nil {
		return nil
	}
	return &Facades{
		PostModerationCaseCommandFacet:   service,
		PostModerationCaseQueryFacet:     service,
		PublicationEligibilityQueryFacet: service,
	}
}
