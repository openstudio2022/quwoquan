package moderation

import "context"

type Facades struct {
	PostModerationCaseCommandFacet
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

func BindFacades(service *ModerationService) *Facades {
	if service == nil {
		return nil
	}
	return &Facades{
		PostModerationCaseCommandFacet:   service,
		PublicationEligibilityQueryFacet: service,
	}
}
