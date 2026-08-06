package gatheringplan

import (
	"context"
	"strings"

	"quwoquan_service/runtime/operation"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

type GatheringPlanQueryFacet struct {
	reader    ports.GatheringPlanReader
	authority ports.GatheringAuthorityReader
}

func NewGatheringPlanQueryFacet(reader ports.GatheringPlanReader, authority ports.GatheringAuthorityReader) *GatheringPlanQueryFacet {
	if reader == nil || authority == nil {
		panic("GatheringPlan QueryFacet requires named Reader and delegated Gathering authority")
	}
	return &GatheringPlanQueryFacet{reader: reader, authority: authority}
}

func (facet *GatheringPlanQueryFacet) GetGatheringPlan(ctx context.Context, gatheringID string) (model.GatheringPlan, error) {
	actorID, err := trustedQueryActor(ctx)
	if err != nil {
		return model.GatheringPlan{}, err
	}
	gatheringID = strings.TrimSpace(gatheringID)
	if err := facet.authorizeRead(ctx, gatheringID, actorID); err != nil {
		return model.GatheringPlan{}, err
	}
	plan, found, err := facet.reader.ReadByGathering(ctx, gatheringID)
	if err != nil {
		return model.GatheringPlan{}, err
	}
	if !found {
		return model.GatheringPlan{}, model.ErrNotFound
	}
	return plan, nil
}

func (facet *GatheringPlanQueryFacet) ListGatheringPlanRevisions(ctx context.Context, planID, cursor string, limit int) (model.RevisionPage, error) {
	actorID, err := trustedQueryActor(ctx)
	if err != nil {
		return model.RevisionPage{}, err
	}
	planID = strings.TrimSpace(planID)
	plan, found, err := facet.reader.ReadByID(ctx, planID)
	if err != nil {
		return model.RevisionPage{}, err
	}
	if !found {
		return model.RevisionPage{}, model.ErrNotFound
	}
	if err := facet.authorizeRead(ctx, plan.GatheringID, actorID); err != nil {
		return model.RevisionPage{}, err
	}
	return facet.reader.ListRevisions(ctx, planID, strings.TrimSpace(cursor), limit)
}

func (facet *GatheringPlanQueryFacet) authorizeRead(ctx context.Context, gatheringID, actorID string) error {
	authority, err := facet.authority.ReadGatheringAuthority(ctx, gatheringID, actorID)
	if err != nil {
		return err
	}
	if !authority.Exists {
		return model.ErrGatheringUnavailable
	}
	if !authority.CurrentHost && !authority.ActiveParticipation {
		return model.ErrPermissionDenied
	}
	return nil
}

func trustedQueryActor(ctx context.Context) (string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", model.ErrInvalid
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}
