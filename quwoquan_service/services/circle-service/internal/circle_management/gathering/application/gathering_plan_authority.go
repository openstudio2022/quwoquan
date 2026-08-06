package gathering

import (
	"context"
	"strings"

	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

// GatheringPlanAuthoritySlice is the Gathering owner's live delegated
// decision. It contains no Host/member/lifecycle copy that GatheringPlan could
// persist as a second activity root.
type GatheringPlanAuthoritySlice struct {
	GatheringID         string
	Exists              bool
	CollaborationOpen   bool
	CurrentHost         bool
	ActiveParticipation bool
}

type GatheringPlanAuthorityReader struct {
	store ports.AggregateStore
}

func NewGatheringPlanAuthorityReader(store ports.AggregateStore) *GatheringPlanAuthorityReader {
	if store == nil {
		panic("Gathering Plan authority Reader requires Gathering AggregateStore")
	}
	return &GatheringPlanAuthorityReader{store: store}
}

func (reader *GatheringPlanAuthorityReader) ReadGatheringPlanAuthority(
	ctx context.Context,
	gatheringID string,
	actorPersonaID string,
) (GatheringPlanAuthoritySlice, error) {
	gatheringID = strings.TrimSpace(gatheringID)
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	if gatheringID == "" || actorPersonaID == "" {
		return GatheringPlanAuthoritySlice{}, model.ErrInvalidArgument
	}
	gathering, found, err := reader.store.Load(ctx, gatheringID)
	if err != nil {
		return GatheringPlanAuthoritySlice{}, err
	}
	if !found {
		return GatheringPlanAuthoritySlice{GatheringID: gatheringID}, nil
	}
	slice := GatheringPlanAuthoritySlice{
		GatheringID:       gatheringID,
		Exists:            true,
		CollaborationOpen: gathering.LifecycleStatus == model.GatheringLifecycleStatusPublished,
		CurrentHost:       model.HasActiveOrganizerAuthority(gathering, actorPersonaID),
	}
	for _, participation := range gathering.Participations {
		if strings.TrimSpace(participation.PersonaID) == actorPersonaID &&
			participation.State == model.ParticipationStateActive {
			slice.ActiveParticipation = true
			break
		}
	}
	return slice, nil
}
