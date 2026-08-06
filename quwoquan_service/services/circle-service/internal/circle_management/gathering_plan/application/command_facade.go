package gatheringplan

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

const receiptRetention = 7 * 24 * time.Hour

type CreateGatheringPlanCommand struct {
	GatheringID               string                      `json:"gatheringId"`
	Items                     []model.PlanItem            `json:"items"`
	AcknowledgementPolicy     model.AcknowledgementPolicy `json:"acknowledgementPolicy"`
	AffectedParticipationRefs []model.ParticipationRef    `json:"affectedParticipationRefs"`
}

type ProposeGatheringPlanCommand struct {
	PlanID                    string                      `json:"planId"`
	ExpectedPlanVersion       int64                       `json:"expectedPlanVersion"`
	BaseRevisionID            string                      `json:"baseRevisionId"`
	BaseRevisionNumber        int                         `json:"baseRevisionNumber"`
	BaseRevisionDigest        string                      `json:"baseRevisionDigest"`
	Items                     []model.PlanItem            `json:"items"`
	AcknowledgementPolicy     model.AcknowledgementPolicy `json:"acknowledgementPolicy"`
	AffectedParticipationRefs []model.ParticipationRef    `json:"affectedParticipationRefs"`
}

type CommitGatheringPlanProposalCommand struct {
	PlanID                     string `json:"planId"`
	ProposalID                 string `json:"proposalId"`
	ExpectedPlanVersion        int64  `json:"expectedPlanVersion"`
	ExpectedProposalDigest     string `json:"expectedProposalDigest"`
	ExpectedBaseRevisionDigest string `json:"expectedBaseRevisionDigest"`
}

type GatheringPlanCommandFacet struct {
	store     ports.AggregateStore
	authority ports.GatheringAuthorityReader
	now       func() time.Time
}

func NewGatheringPlanCommandFacet(store ports.AggregateStore, authority ports.GatheringAuthorityReader) *GatheringPlanCommandFacet {
	if store == nil || authority == nil {
		panic("GatheringPlan CommandFacet requires AggregateStore and delegated Gathering authority")
	}
	return &GatheringPlanCommandFacet{store: store, authority: authority, now: time.Now}
}

func (facet *GatheringPlanCommandFacet) CreateGatheringPlan(ctx context.Context, command CreateGatheringPlanCommand) (model.CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return model.CommandResult{}, err
	}
	command.GatheringID = strings.TrimSpace(command.GatheringID)
	planID := stablePlanID(command.GatheringID)
	digest, err := commandDigest(actorID, "CreateGatheringPlan", command)
	if err != nil {
		return model.CommandResult{}, model.ErrInvalid
	}
	now := facet.now().UTC()
	receipt, err := facet.store.Commit(ctx, ports.CommitRequest{
		PlanID: planID, ActorPersonaID: actorID,
		ReceiptKey: receiptKey(actorID, current.IdempotencyKey), CommandDigest: digest,
		ReceiptExpiresAt: now.Add(receiptRetention), EventType: "GatheringPlanCreated",
		Authorize: facet.authorize(command.GatheringID, actorID, authorityHost),
		Mutate: func(existing *model.GatheringPlan) (model.GatheringPlan, model.EventPayload, error) {
			if existing != nil {
				return model.GatheringPlan{}, model.EventPayload{}, model.ErrAlreadyExists
			}
			plan, createErr := model.Create(model.CreateInput{
				PlanID: planID, GatheringID: command.GatheringID, ActorPersonaID: actorID,
				Items: command.Items, AcknowledgementPolicy: command.AcknowledgementPolicy,
				AffectedParticipationRefs: command.AffectedParticipationRefs, OccurredAt: now,
			})
			if createErr != nil {
				return model.GatheringPlan{}, model.EventPayload{}, createErr
			}
			return plan, eventFromPlan(plan, actorID, nil, now), nil
		},
	})
	if err != nil {
		return model.CommandResult{}, err
	}
	return receipt.Result, nil
}

func (facet *GatheringPlanCommandFacet) ProposeGatheringPlan(ctx context.Context, command ProposeGatheringPlanCommand) (model.CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return model.CommandResult{}, err
	}
	command.PlanID = strings.TrimSpace(command.PlanID)
	plan, found, err := facet.store.Load(ctx, command.PlanID)
	if err != nil {
		return model.CommandResult{}, err
	}
	if !found {
		return model.CommandResult{}, model.ErrNotFound
	}
	digest, err := commandDigest(actorID, "ProposeGatheringPlan", command)
	if err != nil {
		return model.CommandResult{}, model.ErrInvalid
	}
	now := facet.now().UTC()
	proposalID := stableProposalID(command.PlanID, actorID, current.IdempotencyKey)
	receipt, err := facet.store.Commit(ctx, ports.CommitRequest{
		PlanID: command.PlanID, ActorPersonaID: actorID,
		ReceiptKey: receiptKey(actorID, current.IdempotencyKey), CommandDigest: digest,
		ReceiptExpiresAt: now.Add(receiptRetention), EventType: "GatheringPlanProposalRecorded",
		Authorize: facet.authorize(plan.GatheringID, actorID, authorityHostOrParticipant),
		Mutate: func(existing *model.GatheringPlan) (model.GatheringPlan, model.EventPayload, error) {
			if existing == nil {
				return model.GatheringPlan{}, model.EventPayload{}, model.ErrNotFound
			}
			next, proposal, proposeErr := model.RecordProposal(*existing, model.ProposeInput{
				ProposalID: proposalID, ActorPersonaID: actorID,
				ExpectedPlanVersion: command.ExpectedPlanVersion,
				BaseRevisionID:      command.BaseRevisionID, BaseRevisionNumber: command.BaseRevisionNumber,
				BaseRevisionDigest: command.BaseRevisionDigest, Items: command.Items,
				AcknowledgementPolicy:     command.AcknowledgementPolicy,
				AffectedParticipationRefs: command.AffectedParticipationRefs, OccurredAt: now,
			})
			if proposeErr != nil {
				return model.GatheringPlan{}, model.EventPayload{}, proposeErr
			}
			return next, eventFromPlan(next, actorID, &proposal, now), nil
		},
	})
	if err != nil {
		return model.CommandResult{}, err
	}
	return receipt.Result, nil
}

func (facet *GatheringPlanCommandFacet) CommitGatheringPlanProposal(ctx context.Context, command CommitGatheringPlanProposalCommand) (model.CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return model.CommandResult{}, err
	}
	command.PlanID = strings.TrimSpace(command.PlanID)
	plan, found, err := facet.store.Load(ctx, command.PlanID)
	if err != nil {
		return model.CommandResult{}, err
	}
	if !found {
		return model.CommandResult{}, model.ErrNotFound
	}
	digest, err := commandDigest(actorID, "CommitGatheringPlanProposal", command)
	if err != nil {
		return model.CommandResult{}, model.ErrInvalid
	}
	now := facet.now().UTC()
	receipt, err := facet.store.Commit(ctx, ports.CommitRequest{
		PlanID: command.PlanID, ActorPersonaID: actorID,
		ReceiptKey: receiptKey(actorID, current.IdempotencyKey), CommandDigest: digest,
		ReceiptExpiresAt: now.Add(receiptRetention), EventType: "GatheringPlanRevisionCommitted",
		Authorize: facet.authorize(plan.GatheringID, actorID, authorityHost),
		Mutate: func(existing *model.GatheringPlan) (model.GatheringPlan, model.EventPayload, error) {
			if existing == nil {
				return model.GatheringPlan{}, model.EventPayload{}, model.ErrNotFound
			}
			next, proposal, _, commitErr := model.CommitProposal(*existing, model.CommitInput{
				ProposalID: command.ProposalID, ActorPersonaID: actorID,
				ExpectedPlanVersion:        command.ExpectedPlanVersion,
				ExpectedProposalDigest:     command.ExpectedProposalDigest,
				ExpectedBaseRevisionDigest: command.ExpectedBaseRevisionDigest,
				OccurredAt:                 now,
			})
			if commitErr != nil {
				return model.GatheringPlan{}, model.EventPayload{}, commitErr
			}
			return next, eventFromPlan(next, actorID, &proposal, now), nil
		},
	})
	if err != nil {
		return model.CommandResult{}, err
	}
	return receipt.Result, nil
}

type authorityRequirement int

const (
	authorityHost authorityRequirement = iota
	authorityHostOrParticipant
)

func (facet *GatheringPlanCommandFacet) authorize(gatheringID, actorID string, requirement authorityRequirement) func(context.Context) error {
	return func(ctx context.Context) error {
		authority, err := facet.authority.ReadGatheringAuthority(ctx, gatheringID, actorID)
		if err != nil {
			return err
		}
		if !authority.Exists || !authority.CollaborationOpen {
			return model.ErrGatheringUnavailable
		}
		if requirement == authorityHost && !authority.CurrentHost {
			return model.ErrPermissionDenied
		}
		if requirement == authorityHostOrParticipant && !authority.CurrentHost && !authority.ActiveParticipation {
			return model.ErrPermissionDenied
		}
		return nil
	}
}

func trustedCommandContext(ctx context.Context) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Validate(operation.ActorPersona) != nil || strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", model.ErrInvalid
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func commandDigest(actorID, operationName string, command any) (string, error) {
	payload, err := json.Marshal(struct {
		ActorID   string `json:"actorId"`
		Operation string `json:"operation"`
		Command   any    `json:"command"`
	}{strings.TrimSpace(actorID), operationName, command})
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func stablePlanID(gatheringID string) string {
	digest := sha256.Sum256([]byte("circle.gathering_plan\x00" + strings.TrimSpace(gatheringID)))
	return "gplan_" + hex.EncodeToString(digest[:16])
}

func stableProposalID(planID, actorID, idempotencyKey string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(planID) + "\x00" + strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return "gplanprop_" + hex.EncodeToString(digest[:16])
}

func receiptKey(actorID, idempotencyKey string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return "gplanreceipt_" + hex.EncodeToString(digest[:])
}

func eventFromPlan(plan model.GatheringPlan, actorID string, proposal *model.Proposal, occurredAt time.Time) model.EventPayload {
	event := model.EventPayload{
		PlanID: plan.ID, GatheringID: plan.GatheringID, AggregateVersion: plan.Version,
		ActorPersonaID: actorID, RevisionID: plan.CurrentRevisionID,
		RevisionNumber: plan.CurrentRevisionNumber, RevisionDigest: plan.CurrentRevisionDigest,
		OccurredAt: occurredAt.UTC(),
	}
	if proposal != nil {
		event.ProposalID = proposal.ProposalID
		event.ProposalDigest = proposal.ProposalDigest
	}
	return event
}
