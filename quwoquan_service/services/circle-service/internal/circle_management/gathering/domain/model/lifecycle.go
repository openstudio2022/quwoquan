package gathering

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

type TemporalPhase string

type GatheringLifecycleStatus = contract.GatheringLifecycleStatus
type GatheringRoomBindingStatus = contract.GatheringRoomBindingStatus

const (
	GatheringLifecycleStatusDraft     = contract.GatheringLifecycleStatusDraft
	GatheringLifecycleStatusPublished = contract.GatheringLifecycleStatusPublished
	GatheringLifecycleStatusCancelled = contract.GatheringLifecycleStatusCancelled
	GatheringLifecycleStatusCompleted = contract.GatheringLifecycleStatusCompleted

	GatheringRoomBindingStatusPending = contract.GatheringRoomBindingStatusPending
	GatheringRoomBindingStatusReady   = contract.GatheringRoomBindingStatusReady
	GatheringRoomBindingStatusFailed  = contract.GatheringRoomBindingStatusFailed
)

var ErrInvalidLifecycleArgument = errors.New("invalid Gathering lifecycle argument")

type CreateGatheringDraftInput struct {
	ID                 string
	CreatedByPersonaID string
	HostBinding        contract.HostBinding
	Purpose            contract.GatheringPurpose
	Schedule           contract.GatheringSchedule
	Place              contract.GatheringPlace
	PolicySet          contract.GatheringPolicySet
	CreatedAt          time.Time
}

func CreateGatheringDraft(input CreateGatheringDraftInput) (Gathering, error) {
	now := input.CreatedAt.UTC()
	input.ID = strings.TrimSpace(input.ID)
	input.CreatedByPersonaID = strings.TrimSpace(input.CreatedByPersonaID)
	input.HostBinding = normalizeHostBinding(input.HostBinding)
	if input.ID == "" || input.CreatedByPersonaID == "" || input.CreatedAt.IsZero() ||
		!validHostAuthority(input.HostBinding, now) {
		return Gathering{}, ErrInvalidLifecycleArgument
	}

	purpose := normalizePurpose(input.Purpose)
	schedule := normalizeSchedule(input.Schedule)
	place := normalizePlace(input.Place)
	policySet := normalizePolicySet(input.PolicySet)
	revision := initialGatheringRevision(
		input.ID,
		input.CreatedByPersonaID,
		input.HostBinding,
		purpose,
		schedule,
		place,
		policySet,
		now,
	)
	return Gathering{
		ID:                 input.ID,
		Version:            1,
		CreatedByPersonaID: input.CreatedByPersonaID,
		HostBinding:        input.HostBinding,
		OrganizerAssignments: []contract.OrganizerAssignment{{
			PersonaID:            input.CreatedByPersonaID,
			Role:                 contract.GatheringOrganizerRolePrimaryOrganizer,
			AuthorityEvidenceRef: input.HostBinding.AuthorityEvidenceRef,
			AuthorityVersion:     input.HostBinding.AuthorityVersion,
			AssignedAt:           now,
			Version:              1,
		}},
		Purpose:                        purpose,
		Schedule:                       schedule,
		Place:                          place,
		PolicySet:                      policySet,
		AdmissionControl:               contract.GatheringAdmissionControl{Status: contract.GatheringAdmissionControlStatusOpen, Version: 1},
		LifecycleStatus:                contract.GatheringLifecycleStatusDraft,
		RoomBindingStatus:              contract.GatheringRoomBindingStatusPending,
		CurrentGatheringRevisionID:     revision.RevisionID,
		CurrentGatheringRevisionNumber: revision.RevisionNumber,
		Participations:                 []contract.GatheringParticipation{},
		Revisions:                      []contract.GatheringRevision{revision},
		AvailabilityWatches:            []contract.GatheringAvailabilityWatch{},
		CreatedAt:                      now,
		UpdatedAt:                      now,
	}, nil
}

func ResolveTemporalPhase(current Gathering, evaluatedAt time.Time) TemporalPhase {
	if evaluatedAt.IsZero() || current.Schedule.StartAt.IsZero() ||
		evaluatedAt.Before(current.Schedule.StartAt) {
		return TemporalPhaseUpcoming
	}
	if !current.Schedule.EndAt.IsZero() && !evaluatedAt.Before(current.Schedule.EndAt) {
		return TemporalPhaseEnded
	}
	return TemporalPhaseInProgress
}

func PublishGathering(
	current Gathering,
	actorPersonaID string,
	expectedVersion int64,
	occurredAt time.Time,
) (Gathering, error) {
	if err := requireLifecycleMutation(current, actorPersonaID, expectedVersion, occurredAt); err != nil {
		return Gathering{}, err
	}
	if current.LifecycleStatus != contract.GatheringLifecycleStatusDraft {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if !validHostAuthority(current.HostBinding, occurredAt.UTC()) {
		return Gathering{}, gatheringerrors.ErrGatheringHostAuthorityInvalid
	}
	if !completePurpose(current.Purpose) {
		return Gathering{}, gatheringerrors.ErrGatheringDraftIncomplete
	}
	if !completeSchedule(current.Schedule, occurredAt.UTC()) {
		return Gathering{}, gatheringerrors.ErrGatheringScheduleInvalid
	}
	if !completePlace(current.Place) {
		return Gathering{}, gatheringerrors.ErrGatheringDraftIncomplete
	}
	if err := validatePublishPolicy(current.PolicySet); err != nil {
		return Gathering{}, err
	}
	switch current.RoomBindingStatus {
	case contract.GatheringRoomBindingStatusPending:
		return Gathering{}, gatheringerrors.ErrGatheringRoomProvisionPending
	case contract.GatheringRoomBindingStatusFailed:
		return Gathering{}, gatheringerrors.ErrGatheringRoomProvisionFailed
	case contract.GatheringRoomBindingStatusReady:
		if strings.TrimSpace(current.ConversationID) == "" {
			return Gathering{}, gatheringerrors.ErrGatheringRoomProvisionPending
		}
	default:
		return Gathering{}, gatheringerrors.ErrGatheringRoomProvisionPending
	}
	if !revisionMatchesCurrentCommitments(current) {
		return Gathering{}, gatheringerrors.ErrGatheringDraftIncomplete
	}

	next := current
	next.LifecycleStatus = contract.GatheringLifecycleStatusPublished
	touchLifecycle(&next, occurredAt)
	return next, nil
}

func CancelGathering(
	current Gathering,
	actorPersonaID string,
	expectedVersion int64,
	reasonRef string,
	occurredAt time.Time,
) (Gathering, error) {
	if err := requireLifecycleMutation(current, actorPersonaID, expectedVersion, occurredAt); err != nil {
		return Gathering{}, err
	}
	if strings.TrimSpace(reasonRef) == "" {
		return Gathering{}, ErrInvalidLifecycleArgument
	}
	if current.LifecycleStatus != contract.GatheringLifecycleStatusDraft &&
		current.LifecycleStatus != contract.GatheringLifecycleStatusPublished {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if ResolveTemporalPhase(current, occurredAt.UTC()) != TemporalPhaseUpcoming {
		return Gathering{}, gatheringerrors.ErrGatheringCancellationWindowClosed
	}
	next := current
	next.LifecycleStatus = contract.GatheringLifecycleStatusCancelled
	next.CancelledAt = occurredAt.UTC()
	touchLifecycle(&next, occurredAt)
	return next, nil
}

func CompleteGathering(
	current Gathering,
	actorPersonaID string,
	expectedVersion int64,
	outcome contract.GatheringOutcome,
	occurredAt time.Time,
) (Gathering, error) {
	if err := requireLifecycleMutation(current, actorPersonaID, expectedVersion, occurredAt); err != nil {
		return Gathering{}, err
	}
	if current.LifecycleStatus != contract.GatheringLifecycleStatusPublished {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if ResolveTemporalPhase(current, occurredAt.UTC()) != TemporalPhaseEnded {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if err := validateCalculatedOutcome(outcome); err != nil {
		return Gathering{}, err
	}
	switch outcome.Status {
	case contract.GatheringOutcomeStatusUnverified:
		return Gathering{}, gatheringerrors.ErrGatheringOutcomeUnverified
	case contract.GatheringOutcomeStatusDisputed:
		return Gathering{}, gatheringerrors.ErrGatheringOutcomeDisputed
	case contract.GatheringOutcomeStatusEndedEarly, contract.GatheringOutcomeStatusSafetyTerminated:
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	next := current
	next.LifecycleStatus = contract.GatheringLifecycleStatusCompleted
	next.Outcome = cloneOutcome(outcome)
	next.CompletedAt = occurredAt.UTC()
	touchLifecycle(&next, occurredAt)
	return next, nil
}

func EndGatheringEarly(
	current Gathering,
	actorPersonaID string,
	expectedVersion int64,
	reasonRef string,
	evidenceRefs []contract.CanonicalObjectRef,
	occurredAt time.Time,
) (Gathering, error) {
	if err := requireLifecycleMutation(current, actorPersonaID, expectedVersion, occurredAt); err != nil {
		return Gathering{}, err
	}
	if current.LifecycleStatus != contract.GatheringLifecycleStatusPublished {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if ResolveTemporalPhase(current, occurredAt.UTC()) != TemporalPhaseInProgress {
		return Gathering{}, gatheringerrors.ErrGatheringOperationNotAllowedInProgress
	}
	outcome, err := terminalOutcome(
		contract.GatheringOutcomeStatusEndedEarly,
		reasonRef,
		evidenceRefs,
		occurredAt,
	)
	if err != nil {
		return Gathering{}, err
	}
	next := current
	next.LifecycleStatus = contract.GatheringLifecycleStatusCompleted
	next.Outcome = outcome
	next.CompletedAt = occurredAt.UTC()
	touchLifecycle(&next, occurredAt)
	return next, nil
}

func SafetyTerminateGathering(
	current Gathering,
	expectedVersion int64,
	reasonRef string,
	evidenceRefs []contract.CanonicalObjectRef,
	occurredAt time.Time,
) (Gathering, error) {
	if expectedVersion != current.Version {
		return Gathering{}, gatheringerrors.ErrGatheringVersionConflict
	}
	if occurredAt.IsZero() || strings.TrimSpace(reasonRef) == "" {
		return Gathering{}, ErrInvalidLifecycleArgument
	}
	if current.LifecycleStatus == contract.GatheringLifecycleStatusCancelled ||
		current.LifecycleStatus == contract.GatheringLifecycleStatusCompleted {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	outcome, err := terminalOutcome(
		contract.GatheringOutcomeStatusSafetyTerminated,
		reasonRef,
		evidenceRefs,
		occurredAt,
	)
	if err != nil {
		return Gathering{}, err
	}
	next := current
	next.LifecycleStatus = contract.GatheringLifecycleStatusCompleted
	next.Outcome = outcome
	next.CompletedAt = occurredAt.UTC()
	touchLifecycle(&next, occurredAt)
	return next, nil
}

func requireLifecycleMutation(
	current Gathering,
	actorPersonaID string,
	expectedVersion int64,
	occurredAt time.Time,
) error {
	if expectedVersion != current.Version {
		return gatheringerrors.ErrGatheringVersionConflict
	}
	if occurredAt.IsZero() {
		return ErrInvalidLifecycleArgument
	}
	if !hasActiveOrganizerAuthority(current, actorPersonaID) {
		return gatheringerrors.ErrGatheringPermissionDenied
	}
	return nil
}

func hasActiveOrganizerAuthority(current Gathering, actorPersonaID string) bool {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	if actorPersonaID == "" {
		return false
	}
	for _, assignment := range current.OrganizerAssignments {
		if strings.TrimSpace(assignment.PersonaID) == actorPersonaID &&
			assignment.RevokedAt.IsZero() &&
			strings.TrimSpace(assignment.AuthorityEvidenceRef) != "" &&
			assignment.AuthorityVersion > 0 {
			return true
		}
	}
	return false
}

func validHostAuthority(binding contract.HostBinding, at time.Time) bool {
	if strings.TrimSpace(binding.HostSubjectID) == "" ||
		strings.TrimSpace(binding.AuthorityEvidenceRef) == "" ||
		binding.AuthorityVersion <= 0 {
		return false
	}
	switch binding.HostSubjectKind {
	case contract.GatheringHostSubjectKindPersona,
		contract.GatheringHostSubjectKindEntityHomepage,
		contract.GatheringHostSubjectKindCircle:
	default:
		return false
	}
	return binding.AuthorityExpiresAt.IsZero() || binding.AuthorityExpiresAt.After(at)
}

func completePurpose(purpose contract.GatheringPurpose) bool {
	if strings.TrimSpace(purpose.Title) == "" || strings.TrimSpace(purpose.Summary) == "" {
		return false
	}
	switch purpose.CostNotice {
	case contract.GatheringCostNoticeFree:
	case contract.GatheringCostNoticeEstimated, contract.GatheringCostNoticeExternalPaymentRequired:
		if strings.TrimSpace(purpose.CostDescription) == "" {
			return false
		}
	default:
		return false
	}
	for _, source := range purpose.SourceObjectRefs {
		if strings.TrimSpace(source.ObjectRef.ObjectTypeRef) == "" ||
			strings.TrimSpace(source.ObjectRef.ObjectID) == "" ||
			strings.TrimSpace(source.RouteID) == "" ||
			strings.TrimSpace(source.SourceDigest) == "" {
			return false
		}
	}
	return true
}

func completeSchedule(schedule contract.GatheringSchedule, at time.Time) bool {
	if strings.TrimSpace(schedule.Timezone) == "" || schedule.StartAt.IsZero() ||
		schedule.EndAt.IsZero() || !schedule.EndAt.After(schedule.StartAt) ||
		!schedule.StartAt.After(at) {
		return false
	}
	return schedule.AdmissionClosesAt.IsZero() ||
		(!schedule.AdmissionClosesAt.After(schedule.StartAt) &&
			schedule.AdmissionClosesAt.After(at))
}

func completePlace(place contract.GatheringPlace) bool {
	hasCoarsePlace := strings.TrimSpace(place.CoarsePlaceLabel) != "" ||
		(strings.TrimSpace(place.CoarsePlaceRef.ObjectTypeRef) != "" &&
			strings.TrimSpace(place.CoarsePlaceRef.ObjectID) != "")
	switch place.Mode {
	case contract.GatheringPlaceModePhysical:
		return hasCoarsePlace && strings.TrimSpace(place.ExactMeetingPoint) != ""
	case contract.GatheringPlaceModeOnline:
		return strings.TrimSpace(place.OnlineLocationRef) != ""
	case contract.GatheringPlaceModeHybrid:
		return hasCoarsePlace &&
			strings.TrimSpace(place.ExactMeetingPoint) != "" &&
			strings.TrimSpace(place.OnlineLocationRef) != ""
	default:
		return false
	}
}

func validatePublishPolicy(policy contract.GatheringPolicySet) error {
	switch policy.AudiencePolicy {
	case contract.GatheringAudiencePolicyPublic,
		contract.GatheringAudiencePolicyUnlisted,
		contract.GatheringAudiencePolicyCommunityMembers,
		contract.GatheringAudiencePolicyInviteOnly:
	default:
		return gatheringerrors.ErrGatheringDraftIncomplete
	}
	switch policy.AdmissionPolicy {
	case contract.GatheringAdmissionPolicyOpen,
		contract.GatheringAdmissionPolicyApproval,
		contract.GatheringAdmissionPolicyInviteOnly:
	default:
		return gatheringerrors.ErrGatheringDraftIncomplete
	}
	if policy.CapacityPolicy.MaxParticipants < 2 {
		return gatheringerrors.ErrGatheringDraftIncomplete
	}
	switch policy.DisclosurePolicy.TimeDisclosure {
	case contract.GatheringTimeDisclosureExact,
		contract.GatheringTimeDisclosureDateOnly,
		contract.GatheringTimeDisclosureAfterJoin:
	default:
		return gatheringerrors.ErrGatheringDisclosureInvalid
	}
	switch policy.DisclosurePolicy.PlaceDisclosure {
	case contract.GatheringPlaceDisclosureExact,
		contract.GatheringPlaceDisclosureCoarse,
		contract.GatheringPlaceDisclosureAfterJoin:
	default:
		return gatheringerrors.ErrGatheringDisclosureInvalid
	}
	switch policy.DisclosurePolicy.RosterDisclosure {
	case contract.GatheringRosterDisclosureCountOnly,
		contract.GatheringRosterDisclosureJoinedMembers,
		contract.GatheringRosterDisclosurePublicOptIn:
	default:
		return gatheringerrors.ErrGatheringDisclosureInvalid
	}
	if strings.TrimSpace(policy.RiskControlPolicyRef) == "" ||
		strings.TrimSpace(policy.PolicyDecisionRef) == "" ||
		strings.TrimSpace(policy.PolicyDigest) == "" ||
		strings.TrimSpace(policy.ObligationDigest) == "" {
		return gatheringerrors.ErrGatheringPublishObligationMissing
	}
	return nil
}

func validateCalculatedOutcome(outcome contract.GatheringOutcome) error {
	if outcome.CalculatedAt.IsZero() || strings.TrimSpace(outcome.CalculationDigest) == "" ||
		outcome.IndependentEvidenceCount < 0 {
		return ErrInvalidLifecycleArgument
	}
	switch outcome.Status {
	case contract.GatheringOutcomeStatusOccurred,
		contract.GatheringOutcomeStatusDidNotHappen:
		if outcome.IndependentEvidenceCount < 2 ||
			!validLifecycleEvidenceRefs(outcome.EvidenceRefs) {
			return gatheringerrors.ErrGatheringOutcomeUnverified
		}
		return nil
	case contract.GatheringOutcomeStatusEndedEarly,
		contract.GatheringOutcomeStatusSafetyTerminated,
		contract.GatheringOutcomeStatusDisputed,
		contract.GatheringOutcomeStatusUnverified:
		return nil
	default:
		return ErrInvalidLifecycleArgument
	}
}

func validLifecycleEvidenceRefs(values []contract.CanonicalObjectRef) bool {
	if len(values) == 0 {
		return false
	}
	for _, value := range values {
		if strings.TrimSpace(value.ObjectTypeRef) == "" ||
			strings.TrimSpace(value.ObjectID) == "" {
			return false
		}
	}
	return true
}

func terminalOutcome(
	status contract.GatheringOutcomeStatus,
	reasonRef string,
	evidenceRefs []contract.CanonicalObjectRef,
	occurredAt time.Time,
) (contract.GatheringOutcome, error) {
	reasonRef = strings.TrimSpace(reasonRef)
	if reasonRef == "" || occurredAt.IsZero() {
		return contract.GatheringOutcome{}, ErrInvalidLifecycleArgument
	}
	refs := cloneCanonicalRefs(evidenceRefs)
	digest, err := canonicalDigest(struct {
		Status       contract.GatheringOutcomeStatus
		ReasonRef    string
		EvidenceRefs []contract.CanonicalObjectRef
	}{status, reasonRef, refs})
	if err != nil {
		return contract.GatheringOutcome{}, err
	}
	return contract.GatheringOutcome{
		Status:            status,
		EvidenceRefs:      refs,
		CalculatedAt:      occurredAt.UTC(),
		CalculationDigest: digest,
	}, nil
}

func revisionMatchesCurrentCommitments(current Gathering) bool {
	if current.CurrentGatheringRevisionID == "" ||
		current.CurrentGatheringRevisionNumber <= 0 ||
		len(current.Revisions) == 0 {
		return false
	}
	revision := current.Revisions[len(current.Revisions)-1]
	if revision.RevisionID != current.CurrentGatheringRevisionID ||
		revision.RevisionNumber != current.CurrentGatheringRevisionNumber {
		return false
	}
	digest, err := revisionCommitmentDigest(
		current.Purpose,
		current.Schedule,
		current.Place,
		current.PolicySet,
		current.HostBinding,
	)
	return err == nil && digest == revision.Digest
}

func touchLifecycle(current *Gathering, occurredAt time.Time) {
	current.Version++
	current.UpdatedAt = occurredAt.UTC()
}

func normalizeHostBinding(value contract.HostBinding) contract.HostBinding {
	value.HostSubjectID = strings.TrimSpace(value.HostSubjectID)
	value.AuthorityEvidenceRef = strings.TrimSpace(value.AuthorityEvidenceRef)
	value.AuthorityExpiresAt = lifecycleUTCOrZero(value.AuthorityExpiresAt)
	return value
}

func normalizeSchedule(value contract.GatheringSchedule) contract.GatheringSchedule {
	value.Timezone = strings.TrimSpace(value.Timezone)
	value.StartAt = lifecycleUTCOrZero(value.StartAt)
	value.EndAt = lifecycleUTCOrZero(value.EndAt)
	value.AdmissionClosesAt = lifecycleUTCOrZero(value.AdmissionClosesAt)
	return value
}

func normalizePlace(value contract.GatheringPlace) contract.GatheringPlace {
	value.CoarsePlaceRef.ObjectTypeRef = strings.TrimSpace(value.CoarsePlaceRef.ObjectTypeRef)
	value.CoarsePlaceRef.ObjectID = strings.TrimSpace(value.CoarsePlaceRef.ObjectID)
	value.CoarsePlaceLabel = strings.TrimSpace(value.CoarsePlaceLabel)
	value.ExactMeetingPoint = strings.TrimSpace(value.ExactMeetingPoint)
	value.OnlineLocationRef = strings.TrimSpace(value.OnlineLocationRef)
	return value
}

func normalizePurpose(value contract.GatheringPurpose) contract.GatheringPurpose {
	value.Title = strings.TrimSpace(value.Title)
	value.Summary = strings.TrimSpace(value.Summary)
	value.CostDescription = strings.TrimSpace(value.CostDescription)
	value.CoverRef.ObjectTypeRef = strings.TrimSpace(value.CoverRef.ObjectTypeRef)
	value.CoverRef.ObjectID = strings.TrimSpace(value.CoverRef.ObjectID)
	value.TopicRefs = cloneStrings(value.TopicRefs)
	value.RequirementRefs = cloneStrings(value.RequirementRefs)
	sourceObjectRefs := make(
		[]contract.GatheringSourceRef,
		len(value.SourceObjectRefs),
	)
	copy(sourceObjectRefs, value.SourceObjectRefs)
	value.SourceObjectRefs = sourceObjectRefs
	for index := range value.SourceObjectRefs {
		value.SourceObjectRefs[index].ObjectRef.ObjectTypeRef = strings.TrimSpace(value.SourceObjectRefs[index].ObjectRef.ObjectTypeRef)
		value.SourceObjectRefs[index].ObjectRef.ObjectID = strings.TrimSpace(value.SourceObjectRefs[index].ObjectRef.ObjectID)
		value.SourceObjectRefs[index].RouteID = strings.TrimSpace(value.SourceObjectRefs[index].RouteID)
		value.SourceObjectRefs[index].SourceDigest = strings.TrimSpace(value.SourceObjectRefs[index].SourceDigest)
	}
	return value
}

func normalizePolicySet(value contract.GatheringPolicySet) contract.GatheringPolicySet {
	value.RiskControlPolicyRef = strings.TrimSpace(value.RiskControlPolicyRef)
	value.PolicyDecisionRef = strings.TrimSpace(value.PolicyDecisionRef)
	value.PolicyDigest = strings.TrimSpace(value.PolicyDigest)
	value.ObligationDigest = strings.TrimSpace(value.ObligationDigest)
	questions := make(
		[]contract.GatheringApplicationQuestion,
		len(value.ApplicationQuestions),
	)
	copy(questions, value.ApplicationQuestions)
	value.ApplicationQuestions = questions
	for questionIndex := range value.ApplicationQuestions {
		question := &value.ApplicationQuestions[questionIndex]
		question.QuestionID = strings.TrimSpace(question.QuestionID)
		question.Prompt = strings.TrimSpace(question.Prompt)
		options := make(
			[]contract.GatheringApplicationQuestionOption,
			len(question.Options),
		)
		copy(options, question.Options)
		question.Options = options
		for optionIndex := range question.Options {
			question.Options[optionIndex].OptionID = strings.TrimSpace(question.Options[optionIndex].OptionID)
			question.Options[optionIndex].Label = strings.TrimSpace(question.Options[optionIndex].Label)
		}
	}
	return value
}

func cloneOutcome(value contract.GatheringOutcome) contract.GatheringOutcome {
	value.EvidenceRefs = cloneCanonicalRefs(value.EvidenceRefs)
	value.CalculatedAt = value.CalculatedAt.UTC()
	return value
}

func cloneCanonicalRefs(values []contract.CanonicalObjectRef) []contract.CanonicalObjectRef {
	result := make([]contract.CanonicalObjectRef, len(values))
	copy(result, values)
	for index := range result {
		result[index].ObjectTypeRef = strings.TrimSpace(result[index].ObjectTypeRef)
		result[index].ObjectID = strings.TrimSpace(result[index].ObjectID)
	}
	return result
}

func cloneStrings(values []string) []string {
	result := make([]string, len(values))
	copy(result, values)
	for index := range result {
		result[index] = strings.TrimSpace(result[index])
	}
	return result
}

func canonicalDigest(value any) (string, error) {
	encoded, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:]), nil
}

func lifecycleUTCOrZero(value time.Time) time.Time {
	if value.IsZero() {
		return time.Time{}
	}
	// MongoDB BSON DateTime has millisecond precision. Commitments must be
	// computed from that same canonical precision or a persisted draft can no
	// longer prove its own revision digest after a read-back.
	return value.UTC().Truncate(time.Millisecond)
}
