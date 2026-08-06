package gatheringplan

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

const zeroDigest = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

type CreateInput struct {
	PlanID                    string
	GatheringID               string
	ActorPersonaID            string
	Items                     []PlanItem
	AcknowledgementPolicy     AcknowledgementPolicy
	AffectedParticipationRefs []ParticipationRef
	OccurredAt                time.Time
}

type ProposeInput struct {
	ProposalID                string
	ActorPersonaID            string
	ExpectedPlanVersion       int64
	BaseRevisionID            string
	BaseRevisionNumber        int
	BaseRevisionDigest        string
	Items                     []PlanItem
	AcknowledgementPolicy     AcknowledgementPolicy
	AffectedParticipationRefs []ParticipationRef
	OccurredAt                time.Time
}

type CommitInput struct {
	ProposalID                 string
	ActorPersonaID             string
	ExpectedPlanVersion        int64
	ExpectedProposalDigest     string
	ExpectedBaseRevisionDigest string
	OccurredAt                 time.Time
}

func Create(input CreateInput) (GatheringPlan, error) {
	input.PlanID = strings.TrimSpace(input.PlanID)
	input.GatheringID = strings.TrimSpace(input.GatheringID)
	input.ActorPersonaID = strings.TrimSpace(input.ActorPersonaID)
	now := canonicalTime(input.OccurredAt)
	if input.PlanID == "" || input.GatheringID == "" || input.ActorPersonaID == "" || now.IsZero() {
		return GatheringPlan{}, ErrInvalid
	}
	items, err := normalizeItems(input.GatheringID, input.Items)
	if err != nil {
		return GatheringPlan{}, err
	}
	policy, affected, err := normalizeAcknowledgement(input.GatheringID, input.AcknowledgementPolicy, input.AffectedParticipationRefs)
	if err != nil {
		return GatheringPlan{}, err
	}
	revision := Revision{
		RevisionNumber:            1,
		BaseRevisionNumber:        0,
		BaseRevisionDigest:        zeroDigest,
		CommittedByPersonaID:      input.ActorPersonaID,
		Items:                     items,
		AcknowledgementPolicy:     policy,
		AffectedParticipationRefs: affected,
		CommittedAt:               now,
	}
	revision.RevisionDigest, err = revisionContentDigest(revision)
	if err != nil {
		return GatheringPlan{}, err
	}
	revision.RevisionID = stableRevisionID(input.PlanID, revision.RevisionNumber, revision.RevisionDigest)
	plan := GatheringPlan{
		ID:                    input.PlanID,
		GatheringID:           input.GatheringID,
		Version:               1,
		CurrentRevisionID:     revision.RevisionID,
		CurrentRevisionNumber: revision.RevisionNumber,
		CurrentRevisionDigest: revision.RevisionDigest,
		Revisions:             []Revision{revision},
		Proposals:             []Proposal{},
		Acknowledgements:      pendingAcknowledgements(revision),
		CreatedAt:             now,
		UpdatedAt:             now,
	}
	if err := plan.Validate(); err != nil {
		return GatheringPlan{}, err
	}
	return plan, nil
}

func RecordProposal(current GatheringPlan, input ProposeInput) (GatheringPlan, Proposal, error) {
	if err := current.Validate(); err != nil {
		return GatheringPlan{}, Proposal{}, err
	}
	input.ProposalID = strings.TrimSpace(input.ProposalID)
	input.ActorPersonaID = strings.TrimSpace(input.ActorPersonaID)
	input.BaseRevisionID = strings.TrimSpace(input.BaseRevisionID)
	input.BaseRevisionDigest = strings.TrimSpace(input.BaseRevisionDigest)
	now := canonicalTime(input.OccurredAt)
	if input.ProposalID == "" || input.ActorPersonaID == "" || now.IsZero() {
		return GatheringPlan{}, Proposal{}, ErrInvalid
	}
	if current.Version != input.ExpectedPlanVersion {
		return GatheringPlan{}, Proposal{}, ErrVersionConflict
	}
	if current.CurrentRevisionID != input.BaseRevisionID ||
		current.CurrentRevisionNumber != input.BaseRevisionNumber ||
		current.CurrentRevisionDigest != input.BaseRevisionDigest {
		return GatheringPlan{}, Proposal{}, ErrRevisionConflict
	}
	for _, existing := range current.Proposals {
		if existing.ProposalID == input.ProposalID {
			return GatheringPlan{}, Proposal{}, ErrProposalConflict
		}
	}
	items, err := normalizeItems(current.GatheringID, input.Items)
	if err != nil {
		return GatheringPlan{}, Proposal{}, err
	}
	policy, affected, err := normalizeAcknowledgement(current.GatheringID, input.AcknowledgementPolicy, input.AffectedParticipationRefs)
	if err != nil {
		return GatheringPlan{}, Proposal{}, err
	}
	proposal := Proposal{
		ProposalID:                input.ProposalID,
		BasePlanVersion:           current.Version,
		BaseRevisionID:            current.CurrentRevisionID,
		BaseRevisionNumber:        current.CurrentRevisionNumber,
		BaseRevisionDigest:        current.CurrentRevisionDigest,
		ProposedByPersonaID:       input.ActorPersonaID,
		Items:                     items,
		AcknowledgementPolicy:     policy,
		AffectedParticipationRefs: affected,
		Status:                    ProposalStatusPending,
		ProposedAt:                now,
	}
	proposal.ProposalDigest, err = proposalContentDigest(proposal)
	if err != nil {
		return GatheringPlan{}, Proposal{}, err
	}
	next := clonePlan(current)
	next.Proposals = append(next.Proposals, proposal)
	next.Version++
	next.UpdatedAt = now
	if err := next.Validate(); err != nil {
		return GatheringPlan{}, Proposal{}, err
	}
	return next, cloneProposal(proposal), nil
}

func CommitProposal(current GatheringPlan, input CommitInput) (GatheringPlan, Proposal, Revision, error) {
	if err := current.Validate(); err != nil {
		return GatheringPlan{}, Proposal{}, Revision{}, err
	}
	input.ProposalID = strings.TrimSpace(input.ProposalID)
	input.ActorPersonaID = strings.TrimSpace(input.ActorPersonaID)
	input.ExpectedProposalDigest = strings.TrimSpace(input.ExpectedProposalDigest)
	input.ExpectedBaseRevisionDigest = strings.TrimSpace(input.ExpectedBaseRevisionDigest)
	now := canonicalTime(input.OccurredAt)
	if input.ProposalID == "" || input.ActorPersonaID == "" || now.IsZero() {
		return GatheringPlan{}, Proposal{}, Revision{}, ErrInvalid
	}
	if current.Version != input.ExpectedPlanVersion {
		return GatheringPlan{}, Proposal{}, Revision{}, ErrVersionConflict
	}
	proposalIndex := -1
	for index := range current.Proposals {
		if current.Proposals[index].ProposalID == input.ProposalID {
			proposalIndex = index
			break
		}
	}
	if proposalIndex < 0 {
		return GatheringPlan{}, Proposal{}, Revision{}, ErrProposalNotFound
	}
	proposal := cloneProposal(current.Proposals[proposalIndex])
	if proposal.Status != ProposalStatusPending || proposal.ProposalDigest != input.ExpectedProposalDigest {
		return GatheringPlan{}, Proposal{}, Revision{}, ErrProposalConflict
	}
	if proposal.BaseRevisionID != current.CurrentRevisionID ||
		proposal.BaseRevisionNumber != current.CurrentRevisionNumber ||
		proposal.BaseRevisionDigest != current.CurrentRevisionDigest ||
		proposal.BaseRevisionDigest != input.ExpectedBaseRevisionDigest {
		return GatheringPlan{}, Proposal{}, Revision{}, ErrRevisionConflict
	}
	revision := Revision{
		RevisionNumber:            current.CurrentRevisionNumber + 1,
		BaseRevisionID:            current.CurrentRevisionID,
		BaseRevisionNumber:        current.CurrentRevisionNumber,
		BaseRevisionDigest:        current.CurrentRevisionDigest,
		CommittedProposalID:       proposal.ProposalID,
		CommittedByPersonaID:      input.ActorPersonaID,
		Items:                     cloneItems(proposal.Items),
		AcknowledgementPolicy:     clonePolicy(proposal.AcknowledgementPolicy),
		AffectedParticipationRefs: cloneParticipationRefs(proposal.AffectedParticipationRefs),
		CommittedAt:               now,
	}
	var err error
	revision.RevisionDigest, err = revisionContentDigest(revision)
	if err != nil {
		return GatheringPlan{}, Proposal{}, Revision{}, err
	}
	revision.RevisionID = stableRevisionID(current.ID, revision.RevisionNumber, revision.RevisionDigest)
	next := clonePlan(current)
	next.Revisions = append(next.Revisions, revision)
	next.CurrentRevisionID = revision.RevisionID
	next.CurrentRevisionNumber = revision.RevisionNumber
	next.CurrentRevisionDigest = revision.RevisionDigest
	next.Version++
	next.UpdatedAt = now
	committedAt := now
	next.Proposals[proposalIndex].Status = ProposalStatusCommitted
	next.Proposals[proposalIndex].CommittedRevisionID = revision.RevisionID
	next.Proposals[proposalIndex].CommittedAt = &committedAt
	next.Acknowledgements = append(next.Acknowledgements, pendingAcknowledgements(revision)...)
	if err := next.Validate(); err != nil {
		return GatheringPlan{}, Proposal{}, Revision{}, err
	}
	return next, cloneProposal(next.Proposals[proposalIndex]), cloneRevision(revision), nil
}

func (plan GatheringPlan) Validate() error {
	if strings.TrimSpace(plan.ID) == "" || strings.TrimSpace(plan.GatheringID) == "" ||
		plan.Version <= 0 || plan.CreatedAt.IsZero() || plan.UpdatedAt.IsZero() ||
		plan.UpdatedAt.Before(plan.CreatedAt) || len(plan.Revisions) == 0 {
		return ErrInvalid
	}
	seenRevisionIDs := map[string]struct{}{}
	revisionByID := map[string]Revision{}
	foundCurrent := false
	for index, revision := range plan.Revisions {
		if err := validateRevision(plan.GatheringID, revision); err != nil {
			return err
		}
		if revision.RevisionNumber != index+1 {
			return ErrRevisionConflict
		}
		if index == 0 {
			if revision.BaseRevisionID != "" || revision.BaseRevisionNumber != 0 || revision.BaseRevisionDigest != zeroDigest {
				return ErrRevisionConflict
			}
		} else {
			previous := plan.Revisions[index-1]
			if revision.BaseRevisionID != previous.RevisionID ||
				revision.BaseRevisionNumber != previous.RevisionNumber ||
				revision.BaseRevisionDigest != previous.RevisionDigest {
				return ErrRevisionConflict
			}
		}
		expectedDigest, digestErr := revisionContentDigest(revision)
		if digestErr != nil || expectedDigest != revision.RevisionDigest ||
			stableRevisionID(plan.ID, revision.RevisionNumber, revision.RevisionDigest) != revision.RevisionID {
			return ErrRevisionConflict
		}
		if _, exists := seenRevisionIDs[revision.RevisionID]; exists {
			return ErrRevisionConflict
		}
		seenRevisionIDs[revision.RevisionID] = struct{}{}
		revisionByID[revision.RevisionID] = revision
		if revision.RevisionID == plan.CurrentRevisionID &&
			revision.RevisionNumber == plan.CurrentRevisionNumber &&
			revision.RevisionDigest == plan.CurrentRevisionDigest {
			foundCurrent = true
		}
	}
	if !foundCurrent || plan.CurrentRevisionNumber != len(plan.Revisions) {
		return ErrRevisionConflict
	}
	seenProposalIDs := map[string]struct{}{}
	for _, proposal := range plan.Proposals {
		if err := validateProposal(plan.GatheringID, proposal); err != nil {
			return err
		}
		expectedDigest, digestErr := proposalContentDigest(proposal)
		if digestErr != nil || expectedDigest != proposal.ProposalDigest {
			return ErrProposalConflict
		}
		if _, exists := seenProposalIDs[proposal.ProposalID]; exists {
			return ErrProposalConflict
		}
		seenProposalIDs[proposal.ProposalID] = struct{}{}
		if proposal.Status == ProposalStatusCommitted {
			committedRevision, exists := revisionByID[proposal.CommittedRevisionID]
			if !exists || proposal.CommittedAt == nil ||
				committedRevision.CommittedProposalID != proposal.ProposalID ||
				committedRevision.BaseRevisionID != proposal.BaseRevisionID ||
				committedRevision.BaseRevisionNumber != proposal.BaseRevisionNumber ||
				committedRevision.BaseRevisionDigest != proposal.BaseRevisionDigest {
				return ErrProposalConflict
			}
		}
	}
	seenAcknowledgements := map[string]struct{}{}
	for _, acknowledgement := range plan.Acknowledgements {
		revision, exists := revisionByID[acknowledgement.RevisionID]
		if !exists || revision.AcknowledgementPolicy.Mode != PlanAcknowledgementModeAffectedParticipations ||
			validateParticipationRef(plan.GatheringID, acknowledgement.ParticipationRef) != nil ||
			!validAcknowledgementStatus(acknowledgement.Status) {
			return ErrInvalid
		}
		matchedAffected := false
		for _, affected := range revision.AffectedParticipationRefs {
			if affected == acknowledgement.ParticipationRef {
				matchedAffected = true
				break
			}
		}
		key := acknowledgement.RevisionID + "\x00" + acknowledgement.ParticipationRef.PersonaID
		if !matchedAffected {
			return ErrInvalid
		}
		if _, duplicate := seenAcknowledgements[key]; duplicate {
			return ErrInvalid
		}
		seenAcknowledgements[key] = struct{}{}
	}
	for _, revision := range plan.Revisions {
		if revision.AcknowledgementPolicy.Mode != PlanAcknowledgementModeAffectedParticipations {
			continue
		}
		for _, affected := range revision.AffectedParticipationRefs {
			key := revision.RevisionID + "\x00" + affected.PersonaID
			if _, exists := seenAcknowledgements[key]; !exists {
				return ErrInvalid
			}
		}
	}
	return nil
}

func validateRevision(gatheringID string, revision Revision) error {
	if strings.TrimSpace(revision.RevisionID) == "" || revision.RevisionNumber <= 0 ||
		strings.TrimSpace(revision.BaseRevisionDigest) == "" || strings.TrimSpace(revision.RevisionDigest) == "" ||
		strings.TrimSpace(revision.CommittedByPersonaID) == "" || revision.CommittedAt.IsZero() {
		return ErrInvalid
	}
	if _, err := normalizeItems(gatheringID, revision.Items); err != nil {
		return err
	}
	_, _, err := normalizeAcknowledgement(gatheringID, revision.AcknowledgementPolicy, revision.AffectedParticipationRefs)
	return err
}

func validateProposal(gatheringID string, proposal Proposal) error {
	if strings.TrimSpace(proposal.ProposalID) == "" || proposal.BasePlanVersion <= 0 ||
		strings.TrimSpace(proposal.BaseRevisionID) == "" || proposal.BaseRevisionNumber <= 0 ||
		strings.TrimSpace(proposal.BaseRevisionDigest) == "" || strings.TrimSpace(proposal.ProposalDigest) == "" ||
		strings.TrimSpace(proposal.ProposedByPersonaID) == "" || proposal.ProposedAt.IsZero() ||
		(proposal.Status != ProposalStatusPending && proposal.Status != ProposalStatusCommitted) {
		return ErrInvalid
	}
	if _, err := normalizeItems(gatheringID, proposal.Items); err != nil {
		return err
	}
	_, _, err := normalizeAcknowledgement(gatheringID, proposal.AcknowledgementPolicy, proposal.AffectedParticipationRefs)
	return err
}

func normalizeItems(gatheringID string, source []PlanItem) ([]PlanItem, error) {
	if len(source) > 256 {
		return nil, ErrInvalid
	}
	items := cloneItems(source)
	seenIDs := map[string]struct{}{}
	seenOrders := map[int]struct{}{}
	for index := range items {
		item := &items[index]
		item.ItemID = strings.TrimSpace(item.ItemID)
		if item.ItemID == "" || item.Order < 0 {
			return nil, ErrInvalid
		}
		if _, exists := seenIDs[item.ItemID]; exists {
			return nil, ErrInvalid
		}
		if _, exists := seenOrders[item.Order]; exists {
			return nil, ErrInvalid
		}
		seenIDs[item.ItemID] = struct{}{}
		seenOrders[item.Order] = struct{}{}
		if err := normalizeAndValidateItem(gatheringID, item); err != nil {
			return nil, err
		}
	}
	if items == nil {
		items = []PlanItem{}
	}
	return items, nil
}

func normalizeAndValidateItem(gatheringID string, item *PlanItem) error {
	if len(item.SourceRefs) > 32 {
		return ErrInvalid
	}
	for index := range item.SourceRefs {
		item.SourceRefs[index] = normalizeSourceRef(item.SourceRefs[index])
		if !validSourceRef(item.SourceRefs[index]) {
			return ErrInvalid
		}
	}
	if item.SourceRefs == nil {
		item.SourceRefs = []SourceRef{}
	}
	if item.AssigneeRef != nil {
		ref := normalizeParticipationRef(*item.AssigneeRef)
		item.AssigneeRef = &ref
		if err := validateParticipationRef(gatheringID, ref); err != nil {
			return err
		}
	}
	payloadCount := boolCount(item.Agenda != nil, item.Place != nil, item.RouteSegment != nil, item.Task != nil, item.Checklist != nil, item.Note != nil)
	if payloadCount != 1 {
		return ErrInvalid
	}
	switch item.Kind {
	case PlanItemKindAgenda:
		if item.Agenda == nil || !onlyPayload(item, PlanItemKindAgenda) {
			return ErrInvalid
		}
		item.Agenda.Content = strings.TrimSpace(item.Agenda.Content)
		if !boundedText(item.Agenda.Content, 6000) || (item.Agenda.DurationMinutes != nil && *item.Agenda.DurationMinutes <= 0) {
			return ErrInvalid
		}
		canonicalizeTimePointer(&item.Agenda.StartsAt)
	case PlanItemKindPlace:
		if item.Place == nil || !onlyPayload(item, PlanItemKindPlace) {
			return ErrInvalid
		}
		item.Place.PlaceRef = normalizeSourceRef(item.Place.PlaceRef)
		item.Place.Instruction = strings.TrimSpace(item.Place.Instruction)
		if !validSourceRef(item.Place.PlaceRef) || len([]byte(item.Place.Instruction)) > 1200 {
			return ErrInvalid
		}
	case PlanItemKindRouteSegment:
		if item.RouteSegment == nil || !onlyPayload(item, PlanItemKindRouteSegment) {
			return ErrInvalid
		}
		item.RouteSegment.FromPlaceRef = normalizeSourceRef(item.RouteSegment.FromPlaceRef)
		item.RouteSegment.ToPlaceRef = normalizeSourceRef(item.RouteSegment.ToPlaceRef)
		item.RouteSegment.Instruction = strings.TrimSpace(item.RouteSegment.Instruction)
		if !validSourceRef(item.RouteSegment.FromPlaceRef) || !validSourceRef(item.RouteSegment.ToPlaceRef) ||
			!validTravelMode(item.RouteSegment.TravelMode) ||
			(item.RouteSegment.EstimatedMinutes != nil && *item.RouteSegment.EstimatedMinutes <= 0) ||
			len([]byte(item.RouteSegment.Instruction)) > 1200 {
			return ErrInvalid
		}
	case PlanItemKindTask:
		if item.Task == nil || !onlyPayload(item, PlanItemKindTask) {
			return ErrInvalid
		}
		item.Task.Content = strings.TrimSpace(item.Task.Content)
		canonicalizeTimePointer(&item.Task.DueAt)
		if !boundedText(item.Task.Content, 6000) {
			return ErrInvalid
		}
	case PlanItemKindChecklist:
		if item.Checklist == nil || !onlyPayload(item, PlanItemKindChecklist) || len(item.Checklist.Entries) > 100 {
			return ErrInvalid
		}
		seen := map[string]struct{}{}
		for index := range item.Checklist.Entries {
			entry := &item.Checklist.Entries[index]
			entry.EntryID = strings.TrimSpace(entry.EntryID)
			entry.Content = strings.TrimSpace(entry.Content)
			if entry.EntryID == "" || !boundedText(entry.Content, 1200) {
				return ErrInvalid
			}
			if _, exists := seen[entry.EntryID]; exists {
				return ErrInvalid
			}
			seen[entry.EntryID] = struct{}{}
		}
		if item.Checklist.Entries == nil {
			item.Checklist.Entries = []ChecklistEntry{}
		}
	case PlanItemKindNote:
		if item.Note == nil || !onlyPayload(item, PlanItemKindNote) {
			return ErrInvalid
		}
		item.Note.Content = strings.TrimSpace(item.Note.Content)
		if !boundedText(item.Note.Content, 12000) {
			return ErrInvalid
		}
	default:
		return ErrInvalid
	}
	return nil
}

func normalizeAcknowledgement(gatheringID string, policy AcknowledgementPolicy, refs []ParticipationRef) (AcknowledgementPolicy, []ParticipationRef, error) {
	policy = clonePolicy(policy)
	canonicalizeTimePointer(&policy.DeadlineAt)
	if policy.Mode != PlanAcknowledgementModeNone && policy.Mode != PlanAcknowledgementModeAffectedParticipations {
		return AcknowledgementPolicy{}, nil, ErrInvalid
	}
	if len(refs) > 512 {
		return AcknowledgementPolicy{}, nil, ErrInvalid
	}
	normalized := cloneParticipationRefs(refs)
	seen := map[string]struct{}{}
	for index := range normalized {
		normalized[index] = normalizeParticipationRef(normalized[index])
		if err := validateParticipationRef(gatheringID, normalized[index]); err != nil {
			return AcknowledgementPolicy{}, nil, err
		}
		key := normalized[index].GatheringID + "\x00" + normalized[index].PersonaID
		if _, exists := seen[key]; exists {
			return AcknowledgementPolicy{}, nil, ErrInvalid
		}
		seen[key] = struct{}{}
	}
	if policy.Mode == PlanAcknowledgementModeNone {
		if len(normalized) != 0 || policy.DeadlineAt != nil {
			return AcknowledgementPolicy{}, nil, ErrInvalid
		}
	} else if len(normalized) == 0 {
		return AcknowledgementPolicy{}, nil, ErrInvalid
	}
	if normalized == nil {
		normalized = []ParticipationRef{}
	}
	return policy, normalized, nil
}

func pendingAcknowledgements(revision Revision) []RevisionAcknowledgement {
	if revision.AcknowledgementPolicy.Mode != PlanAcknowledgementModeAffectedParticipations {
		return []RevisionAcknowledgement{}
	}
	values := make([]RevisionAcknowledgement, 0, len(revision.AffectedParticipationRefs))
	for _, ref := range revision.AffectedParticipationRefs {
		values = append(values, RevisionAcknowledgement{
			RevisionID: revision.RevisionID, ParticipationRef: ref,
			Status: PlanAcknowledgementStatusPending,
		})
	}
	return values
}

func revisionContentDigest(revision Revision) (string, error) {
	return digestValue(struct {
		BaseRevisionID            string
		BaseRevisionNumber        int
		BaseRevisionDigest        string
		CommittedProposalID       string
		CommittedByPersonaID      string
		Items                     []PlanItem
		AcknowledgementPolicy     AcknowledgementPolicy
		AffectedParticipationRefs []ParticipationRef
	}{revision.BaseRevisionID, revision.BaseRevisionNumber, revision.BaseRevisionDigest,
		revision.CommittedProposalID, revision.CommittedByPersonaID, revision.Items,
		revision.AcknowledgementPolicy, revision.AffectedParticipationRefs})
}

func proposalContentDigest(proposal Proposal) (string, error) {
	return digestValue(struct {
		BasePlanVersion           int64
		BaseRevisionID            string
		BaseRevisionNumber        int
		BaseRevisionDigest        string
		ProposedByPersonaID       string
		Items                     []PlanItem
		AcknowledgementPolicy     AcknowledgementPolicy
		AffectedParticipationRefs []ParticipationRef
	}{proposal.BasePlanVersion, proposal.BaseRevisionID, proposal.BaseRevisionNumber,
		proposal.BaseRevisionDigest, proposal.ProposedByPersonaID, proposal.Items,
		proposal.AcknowledgementPolicy, proposal.AffectedParticipationRefs})
}

func digestValue(value any) (string, error) {
	payload, err := json.Marshal(value)
	if err != nil {
		return "", fmt.Errorf("%w: digest payload: %v", ErrInvalid, err)
	}
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func stableRevisionID(planID string, number int, digest string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(planID) + "\x00" + fmt.Sprint(number) + "\x00" + digest))
	return "gplanrev_" + hex.EncodeToString(sum[:16])
}

func CommandResultFromPlan(plan GatheringPlan, proposal *Proposal, replayed bool) CommandResult {
	result := CommandResult{
		PlanID: plan.ID, GatheringID: plan.GatheringID, PlanVersion: plan.Version,
		CurrentRevisionID: plan.CurrentRevisionID, CurrentRevisionNumber: plan.CurrentRevisionNumber,
		CurrentRevisionDigest: plan.CurrentRevisionDigest, Replayed: replayed,
	}
	if proposal != nil {
		result.ProposalID = proposal.ProposalID
		result.ProposalDigest = proposal.ProposalDigest
	}
	return result
}

func clonePlan(source GatheringPlan) GatheringPlan {
	value := source
	value.Revisions = make([]Revision, len(source.Revisions))
	for index := range source.Revisions {
		value.Revisions[index] = cloneRevision(source.Revisions[index])
	}
	value.Proposals = make([]Proposal, len(source.Proposals))
	for index := range source.Proposals {
		value.Proposals[index] = cloneProposal(source.Proposals[index])
	}
	value.Acknowledgements = append([]RevisionAcknowledgement(nil), source.Acknowledgements...)
	for index := range value.Acknowledgements {
		if source.Acknowledgements[index].EvidenceRef != nil {
			ref := *source.Acknowledgements[index].EvidenceRef
			value.Acknowledgements[index].EvidenceRef = &ref
		}
		if source.Acknowledgements[index].RecordedAt != nil {
			recorded := *source.Acknowledgements[index].RecordedAt
			value.Acknowledgements[index].RecordedAt = &recorded
		}
	}
	return value
}

func cloneRevision(source Revision) Revision {
	value := source
	value.Items = cloneItems(source.Items)
	value.AcknowledgementPolicy = clonePolicy(source.AcknowledgementPolicy)
	value.AffectedParticipationRefs = cloneParticipationRefs(source.AffectedParticipationRefs)
	return value
}

func cloneProposal(source Proposal) Proposal {
	value := source
	value.Items = cloneItems(source.Items)
	value.AcknowledgementPolicy = clonePolicy(source.AcknowledgementPolicy)
	value.AffectedParticipationRefs = cloneParticipationRefs(source.AffectedParticipationRefs)
	if source.CommittedAt != nil {
		committed := *source.CommittedAt
		value.CommittedAt = &committed
	}
	return value
}

func cloneItems(source []PlanItem) []PlanItem {
	values := make([]PlanItem, len(source))
	for index := range source {
		values[index] = source[index]
		if source[index].Agenda != nil {
			value := *source[index].Agenda
			values[index].Agenda = &value
		}
		if source[index].Place != nil {
			value := *source[index].Place
			values[index].Place = &value
		}
		if source[index].RouteSegment != nil {
			value := *source[index].RouteSegment
			values[index].RouteSegment = &value
		}
		if source[index].Task != nil {
			value := *source[index].Task
			values[index].Task = &value
		}
		if source[index].Checklist != nil {
			value := *source[index].Checklist
			value.Entries = make([]ChecklistEntry, len(source[index].Checklist.Entries))
			copy(value.Entries, source[index].Checklist.Entries)
			values[index].Checklist = &value
		}
		if source[index].Note != nil {
			value := *source[index].Note
			values[index].Note = &value
		}
		if source[index].AssigneeRef != nil {
			value := *source[index].AssigneeRef
			values[index].AssigneeRef = &value
		}
		values[index].SourceRefs = make([]SourceRef, len(source[index].SourceRefs))
		copy(values[index].SourceRefs, source[index].SourceRefs)
	}
	return values
}

func clonePolicy(source AcknowledgementPolicy) AcknowledgementPolicy {
	value := source
	if source.DeadlineAt != nil {
		deadline := *source.DeadlineAt
		value.DeadlineAt = &deadline
	}
	return value
}

func cloneParticipationRefs(source []ParticipationRef) []ParticipationRef {
	values := make([]ParticipationRef, len(source))
	copy(values, source)
	return values
}

func onlyPayload(item *PlanItem, kind PlanItemKind) bool {
	switch kind {
	case PlanItemKindAgenda:
		return item.Place == nil && item.RouteSegment == nil && item.Task == nil && item.Checklist == nil && item.Note == nil
	case PlanItemKindPlace:
		return item.Agenda == nil && item.RouteSegment == nil && item.Task == nil && item.Checklist == nil && item.Note == nil
	case PlanItemKindRouteSegment:
		return item.Agenda == nil && item.Place == nil && item.Task == nil && item.Checklist == nil && item.Note == nil
	case PlanItemKindTask:
		return item.Agenda == nil && item.Place == nil && item.RouteSegment == nil && item.Checklist == nil && item.Note == nil
	case PlanItemKindChecklist:
		return item.Agenda == nil && item.Place == nil && item.RouteSegment == nil && item.Task == nil && item.Note == nil
	case PlanItemKindNote:
		return item.Agenda == nil && item.Place == nil && item.RouteSegment == nil && item.Task == nil && item.Checklist == nil
	default:
		return false
	}
}

func boolCount(values ...bool) int {
	count := 0
	for _, value := range values {
		if value {
			count++
		}
	}
	return count
}

func boundedText(value string, max int) bool {
	return strings.TrimSpace(value) != "" && len([]byte(value)) <= max
}

func normalizeSourceRef(value SourceRef) SourceRef {
	value.ObjectTypeRef = strings.TrimSpace(value.ObjectTypeRef)
	value.ObjectID = strings.TrimSpace(value.ObjectID)
	return value
}

func validSourceRef(value SourceRef) bool {
	return value.ObjectTypeRef != "" && value.ObjectID != ""
}

func normalizeParticipationRef(value ParticipationRef) ParticipationRef {
	value.GatheringID = strings.TrimSpace(value.GatheringID)
	value.PersonaID = strings.TrimSpace(value.PersonaID)
	return value
}

func validateParticipationRef(gatheringID string, value ParticipationRef) error {
	if value.GatheringID != strings.TrimSpace(gatheringID) || value.PersonaID == "" {
		return ErrInvalid
	}
	return nil
}

func validTravelMode(value PlanTravelMode) bool {
	switch value {
	case PlanTravelModeWalk, PlanTravelModeBicycle, PlanTravelModeTransit, PlanTravelModeDrive, PlanTravelModeFerry, PlanTravelModeOther:
		return true
	default:
		return false
	}
}

func validAcknowledgementStatus(value PlanAcknowledgementStatus) bool {
	switch value {
	case PlanAcknowledgementStatusPending, PlanAcknowledgementStatusAcknowledged, PlanAcknowledgementStatusDeclined:
		return true
	default:
		return false
	}
}

func canonicalTime(value time.Time) time.Time {
	if value.IsZero() {
		return time.Time{}
	}
	return value.UTC().Truncate(time.Millisecond)
}

func canonicalizeTimePointer(value **time.Time) {
	if value == nil || *value == nil {
		return
	}
	normalized := canonicalTime(**value)
	*value = &normalized
}
