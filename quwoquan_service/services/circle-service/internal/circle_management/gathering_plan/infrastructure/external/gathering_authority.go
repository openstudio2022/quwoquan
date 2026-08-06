package external

import (
	"context"

	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	planports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

type GatheringAuthoritySource interface {
	ReadGatheringPlanAuthority(context.Context, string, string) (gatheringapp.GatheringPlanAuthoritySlice, error)
}

type GatheringAuthorityReader struct {
	source GatheringAuthoritySource
}

func NewGatheringAuthorityReader(source GatheringAuthoritySource) *GatheringAuthorityReader {
	if source == nil {
		panic("GatheringPlan delegated authority requires Gathering owner source")
	}
	return &GatheringAuthorityReader{source: source}
}

func (reader *GatheringAuthorityReader) ReadGatheringAuthority(
	ctx context.Context,
	gatheringID string,
	actorPersonaID string,
) (planports.GatheringAuthority, error) {
	source, err := reader.source.ReadGatheringPlanAuthority(ctx, gatheringID, actorPersonaID)
	if err != nil {
		return planports.GatheringAuthority{}, err
	}
	return planports.GatheringAuthority{
		GatheringID: source.GatheringID, Exists: source.Exists,
		CollaborationOpen: source.CollaborationOpen, CurrentHost: source.CurrentHost,
		ActiveParticipation: source.ActiveParticipation,
	}, nil
}

var _ planports.GatheringAuthorityReader = (*GatheringAuthorityReader)(nil)
