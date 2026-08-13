package gathering

import (
	"crypto/sha256"
	"encoding/hex"
	"strconv"
	"strings"
	"time"

	wire "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

// Storage consumes the canonical aggregate model. HTTP responses consume the
// generated named wire slices below; this package does not define a second
// response contract.
type CanonicalObjectRef = contract.CanonicalObjectRef
type GatheringReadModel = contract.Gathering
type ParticipationRecord = contract.GatheringParticipation
type ApplicationAnswer = contract.GatheringApplicationAnswer

type PublicCard = wire.GatheringPublicCardSlice
type PublicDetail = wire.GatheringPublicDetailSlice
type PrivateDetail = wire.GatheringPrivateDetailSlice
type ParticipationStatus = wire.GatheringParticipationStatusSlice
type Capacity = wire.GatheringCapacitySlice
type ApplicationInboxItem = wire.GatheringApplicationInboxItemSlice
type ApplicationInboxPage = wire.GatheringApplicationInboxPageSlice
type RosterItem = wire.GatheringRosterItemSlice
type RosterPage = wire.GatheringRosterPageSlice
type ByHostPage = wire.GatheringByHostPageSlice
type BySourcePage = wire.GatheringBySourcePageSlice

type HostRef struct {
	SubjectKind contract.GatheringHostSubjectKind
	SubjectID   string
}

type viewerAccess struct {
	PersonaID     string
	IsOrganizer   bool
	OrganizerRole contract.GatheringOrganizerRole
	Participation *ParticipationRecord
}

type derivedProjection struct {
	Capacity  wire.GatheringCapacitySlice
	Temporal  wire.GatheringTemporalPhaseSlice
	Admission wire.GatheringAdmissionStateSlice
}

func ProjectPublicDetail(
	value GatheringReadModel,
	viewerPersonaID string,
	now time.Time,
) PublicDetail {
	viewer := resolveViewerAccess(value, viewerPersonaID)
	revisions := make([]wire.GatheringRevisionSummarySlice, 0, len(value.Revisions))
	for _, revision := range value.Revisions {
		revisions = append(revisions, wire.GatheringRevisionSummarySlice{
			RevisionID:     revision.RevisionID,
			RevisionNumber: revision.RevisionNumber,
			Digest:         revision.Digest,
			MaterialChange: revision.MaterialChange,
			CreatedAt:      revision.CreatedAt.UTC(),
		})
	}
	result := PublicDetail{
		Card:             projectPublicCard(value, viewer, now.UTC()),
		AudiencePolicy:   wire.GatheringAudiencePolicy(value.PolicySet.AudiencePolicy),
		AdmissionPolicy:  wire.GatheringAdmissionPolicy(value.PolicySet.AdmissionPolicy),
		DisclosurePolicy: toWireDisclosurePolicy(value.PolicySet.DisclosurePolicy),
		Revisions:        revisions,
	}
	if viewer.Participation != nil {
		result.ViewerParticipationState = wire.GatheringParticipationState(
			viewer.Participation.State,
		)
	}
	if (viewer.IsOrganizer || isActive(viewer.Participation)) &&
		value.RoomBindingStatus == contract.GatheringRoomBindingStatusReady {
		result.ConversationID = strings.TrimSpace(value.ConversationID)
	}
	return result
}

func ProjectPrivateDetail(
	value GatheringReadModel,
	_ string,
	now time.Time,
) PrivateDetail {
	derived := deriveProjection(value, now.UTC())
	organizers := make(
		[]wire.OrganizerAssignment,
		0,
		len(value.OrganizerAssignments),
	)
	for _, assignment := range value.OrganizerAssignments {
		organizers = append(organizers, toWireOrganizerAssignment(assignment))
	}
	return PrivateDetail{
		GatheringID:                    value.ID,
		AggregateVersion:               value.Version,
		CreatedByPersonaID:             value.CreatedByPersonaID,
		HostBinding:                    toWireHostBinding(value.HostBinding),
		OrganizerAssignments:           organizers,
		Purpose:                        toWirePurpose(value.Purpose),
		Schedule:                       toWireSchedule(value.Schedule),
		Place:                          toWirePlace(value.Place),
		PolicySet:                      toWirePolicySet(value.PolicySet),
		AdmissionControl:               toWireAdmissionControl(value.AdmissionControl),
		LifecycleStatus:                wire.GatheringLifecycleStatus(value.LifecycleStatus),
		Outcome:                        toWireOutcome(value.Outcome),
		ConversationID:                 value.ConversationID,
		RoomBindingStatus:              wire.GatheringRoomBindingStatus(value.RoomBindingStatus),
		CurrentGatheringRevisionID:     value.CurrentGatheringRevisionID,
		CurrentGatheringRevisionNumber: value.CurrentGatheringRevisionNumber,
		Capacity:                       derived.Capacity,
		Temporal:                       derived.Temporal,
		Admission:                      derived.Admission,
		CreatedAt:                      value.CreatedAt.UTC(),
		UpdatedAt:                      value.UpdatedAt.UTC(),
	}
}

func ProjectPublicCard(value GatheringReadModel, now time.Time) PublicCard {
	return projectPublicCard(value, viewerAccess{}, now.UTC())
}

func projectPublicCard(
	value GatheringReadModel,
	viewer viewerAccess,
	now time.Time,
) PublicCard {
	derived := deriveProjection(value, now.UTC())
	card := PublicCard{
		GatheringID:                    value.ID,
		AggregateVersion:               value.Version,
		Host:                           projectHost(value),
		Purpose:                        projectPublicPurpose(value.Purpose),
		Schedule:                       projectPublicSchedule(value.Schedule, value.PolicySet.DisclosurePolicy, viewer),
		Place:                          projectPublicPlace(value.Place, value.PolicySet.DisclosurePolicy, viewer),
		Capacity:                       derived.Capacity,
		Temporal:                       derived.Temporal,
		Admission:                      derived.Admission,
		LifecycleStatus:                wire.GatheringLifecycleStatus(value.LifecycleStatus),
		OutcomeStatus:                  wire.GatheringOutcomeStatus(value.Outcome.Status),
		CurrentGatheringRevisionID:     value.CurrentGatheringRevisionID,
		CurrentGatheringRevisionNumber: value.CurrentGatheringRevisionNumber,
		UpdatedAt:                      value.UpdatedAt.UTC(),
	}
	card.CardDigest = publicCardDigest(card)
	return card
}

func ProjectApplicationItem(value ParticipationRecord) ApplicationInboxItem {
	answers := make(
		[]wire.GatheringApplicationAnswer,
		0,
		len(value.ApplicationAnswers),
	)
	for _, answer := range value.ApplicationAnswers {
		answers = append(answers, wire.GatheringApplicationAnswer{
			QuestionID:        answer.QuestionID,
			AnswerText:        answer.AnswerText,
			SelectedOptionIds: cloneStrings(answer.SelectedOptionIds),
		})
	}
	return ApplicationInboxItem{
		GatheringID:          value.GatheringID,
		PersonaID:            value.PersonaID,
		ParticipationVersion: value.Version,
		AttemptNo:            value.AttemptNo,
		Answers:              answers,
		ReviewExpectedBy:     utcOrZero(value.ReviewExpectedBy),
	}
}

func ProjectRosterItem(value ParticipationRecord) RosterItem {
	return RosterItem{
		PersonaID:                    value.PersonaID,
		State:                        wire.GatheringParticipationState(value.State),
		AdmissionSource:              wire.GatheringAdmissionSource(value.AdmissionSource),
		JoinedAt:                     utcOrZero(value.JoinedAt),
		AttendanceStatus:             wire.GatheringAttendanceStatus(value.Attendance.Status),
		CurrentAcknowledgementStatus: wire.GatheringRevisionAcknowledgementStatus(value.CurrentChangeAcknowledgement.Status),
	}
}

func deriveProjection(
	value GatheringReadModel,
	now time.Time,
) derivedProjection {
	capacity := deriveCapacity(value, now)
	temporalPhase := deriveTemporalPhase(value.Schedule, now)
	admissionState := deriveAdmissionState(
		value,
		capacity,
		temporalPhase,
		now,
	)
	return derivedProjection{
		Capacity: capacity,
		Temporal: wire.GatheringTemporalPhaseSlice{
			TemporalPhase: temporalPhase,
			EvaluatedAt:   now.UTC(),
		},
		Admission: wire.GatheringAdmissionStateSlice{
			AdmissionState: admissionState,
			ReasonRef: admissionReasonRef(
				value,
				temporalPhase,
				admissionState,
				now,
			),
			EvaluatedAt: now.UTC(),
		},
	}
}

func deriveCapacity(
	value GatheringReadModel,
	now time.Time,
) wire.GatheringCapacitySlice {
	maxParticipants := value.PolicySet.CapacityPolicy.MaxParticipants
	var active, invited int64
	for index := range value.Participations {
		participation := &value.Participations[index]
		switch participation.State {
		case contract.GatheringParticipationStateActive:
			active++
		case contract.GatheringParticipationStateInvitedPending:
			if !participation.SeatHoldUntil.IsZero() &&
				participation.SeatHoldUntil.After(now) {
				invited++
			}
		}
	}
	occupied := active + invited
	remaining := maxParticipants - occupied
	if remaining < 0 {
		remaining = 0
	}
	return wire.GatheringCapacitySlice{
		MaxParticipants:      maxParticipants,
		ActiveSeatCount:      active,
		InvitedSeatHoldCount: invited,
		OccupiedSeats:        occupied,
		RemainingSeats:       remaining,
		Full:                 maxParticipants <= occupied,
	}
}

func deriveTemporalPhase(
	schedule contract.GatheringSchedule,
	now time.Time,
) wire.GatheringTemporalPhase {
	if schedule.StartAt.IsZero() || now.Before(schedule.StartAt.UTC()) {
		return wire.GatheringTemporalPhaseUpcoming
	}
	if schedule.EndAt.IsZero() || now.Before(schedule.EndAt.UTC()) {
		return wire.GatheringTemporalPhaseInProgress
	}
	return wire.GatheringTemporalPhaseEnded
}

func deriveAdmissionState(
	value GatheringReadModel,
	capacity wire.GatheringCapacitySlice,
	temporalPhase wire.GatheringTemporalPhase,
	now time.Time,
) wire.GatheringAdmissionState {
	if value.LifecycleStatus != contract.GatheringLifecycleStatusPublished ||
		temporalPhase != wire.GatheringTemporalPhaseUpcoming {
		return wire.GatheringAdmissionStateClosed
	}
	if !value.Schedule.AdmissionClosesAt.IsZero() &&
		!now.Before(value.Schedule.AdmissionClosesAt.UTC()) {
		return wire.GatheringAdmissionStateClosed
	}
	if value.AdmissionControl.Status ==
		contract.GatheringAdmissionControlStatusPaused {
		return wire.GatheringAdmissionStatePaused
	}
	if capacity.Full {
		return wire.GatheringAdmissionStateFull
	}
	return wire.GatheringAdmissionStateAccepting
}

func admissionReasonRef(
	value GatheringReadModel,
	temporalPhase wire.GatheringTemporalPhase,
	admissionState wire.GatheringAdmissionState,
	now time.Time,
) string {
	switch admissionState {
	case wire.GatheringAdmissionStateFull:
		return "capacity_full"
	case wire.GatheringAdmissionStatePaused:
		return "admission_paused"
	case wire.GatheringAdmissionStateClosed:
		switch {
		case value.LifecycleStatus != contract.GatheringLifecycleStatusPublished:
			return "lifecycle_closed"
		case temporalPhase != wire.GatheringTemporalPhaseUpcoming:
			return "temporal_closed"
		case !value.Schedule.AdmissionClosesAt.IsZero() &&
			!now.Before(value.Schedule.AdmissionClosesAt.UTC()):
			return "deadline_closed"
		default:
			return "admission_closed"
		}
	default:
		return ""
	}
}

func resolveViewerAccess(
	value GatheringReadModel,
	personaID string,
) viewerAccess {
	personaID = strings.TrimSpace(personaID)
	viewer := viewerAccess{PersonaID: personaID}
	if personaID == "" {
		return viewer
	}
	if personaID == strings.TrimSpace(value.CreatedByPersonaID) {
		viewer.IsOrganizer = true
		viewer.OrganizerRole = contract.GatheringOrganizerRolePrimaryOrganizer
	}
	for index := range value.OrganizerAssignments {
		assignment := &value.OrganizerAssignments[index]
		if assignment.PersonaID == personaID && assignment.RevokedAt.IsZero() {
			viewer.IsOrganizer = true
			viewer.OrganizerRole = assignment.Role
			break
		}
	}
	for index := range value.Participations {
		if value.Participations[index].PersonaID == personaID {
			copy := value.Participations[index]
			viewer.Participation = &copy
			break
		}
	}
	return viewer
}

func projectHost(value GatheringReadModel) wire.GatheringHostSummarySlice {
	return wire.GatheringHostSummarySlice{
		HostSubjectKind: wire.GatheringHostSubjectKind(
			value.HostBinding.HostSubjectKind,
		),
		HostSubjectID: value.HostBinding.HostSubjectID,
		HostDigest: digestStrings(
			string(value.HostBinding.HostSubjectKind),
			value.HostBinding.HostSubjectID,
			strconv.FormatInt(value.HostBinding.AuthorityVersion, 10),
		),
	}
}

func projectPublicPurpose(
	value contract.GatheringPurpose,
) wire.GatheringPublicPurposeSlice {
	return wire.GatheringPublicPurposeSlice{
		Title:           value.Title,
		Summary:         value.Summary,
		CoverRef:        toWireObjectRef(value.CoverRef),
		TopicRefs:       cloneStrings(value.TopicRefs),
		RequirementRefs: cloneStrings(value.RequirementRefs),
		CostNotice:      wire.GatheringCostNotice(value.CostNotice),
		CostDescription: value.CostDescription,
	}
}

func projectPublicSchedule(
	value contract.GatheringSchedule,
	disclosure contract.GatheringDisclosurePolicy,
	viewer viewerAccess,
) wire.GatheringPublicScheduleSlice {
	projected := model.ProjectDisclosureSchedule(
		value,
		disclosure,
		viewer.IsOrganizer || isActive(viewer.Participation),
	)
	return wire.GatheringPublicScheduleSlice{
		Timezone:  projected.Timezone,
		StartAt:   projected.StartAt,
		EndAt:     projected.EndAt,
		DateLabel: projected.DateLabel,
	}
}

func projectPublicPlace(
	value contract.GatheringPlace,
	disclosure contract.GatheringDisclosurePolicy,
	viewer viewerAccess,
) wire.GatheringPublicPlaceSlice {
	canSeePrivatePlace := viewer.IsOrganizer || isActive(viewer.Participation)
	projected := model.ProjectDisclosurePlace(
		value,
		disclosure,
		canSeePrivatePlace,
	)
	result := wire.GatheringPublicPlaceSlice{
		Mode:             wire.GatheringPlaceMode(projected.Mode),
		CoarsePlaceLabel: projected.CoarsePlaceLabel,
	}
	if projected.CoarseVisible {
		result.CoarsePlaceRef = toWireObjectRef(value.CoarsePlaceRef)
	}
	// 精确集合点属于加入后/组织者详情事实。即使 Host 选择 exact policy，
	// 匿名 PublicCard 也只承担发现，不得成为精确位置广播通道。
	if canSeePrivatePlace {
		result.ExactMeetingPoint = projected.ExactMeetingPoint
	}
	return result
}

func toWireHostBinding(value contract.HostBinding) wire.HostBinding {
	return wire.HostBinding{
		HostSubjectKind:      wire.GatheringHostSubjectKind(value.HostSubjectKind),
		HostSubjectID:        value.HostSubjectID,
		AuthorityEvidenceRef: value.AuthorityEvidenceRef,
		AuthorityVersion:     value.AuthorityVersion,
		AuthorityExpiresAt:   utcOrZero(value.AuthorityExpiresAt),
	}
}

func toWireOrganizerAssignment(
	value contract.OrganizerAssignment,
) wire.OrganizerAssignment {
	return wire.OrganizerAssignment{
		PersonaID:            value.PersonaID,
		Role:                 wire.GatheringOrganizerRole(value.Role),
		AuthorityEvidenceRef: value.AuthorityEvidenceRef,
		AuthorityVersion:     value.AuthorityVersion,
		AssignedAt:           utcOrZero(value.AssignedAt),
		RevokedAt:            utcOrZero(value.RevokedAt),
		Version:              value.Version,
	}
}

func toWirePurpose(
	value contract.GatheringPurpose,
) wire.GatheringPurpose {
	sources := make([]wire.GatheringSourceRef, 0, len(value.SourceObjectRefs))
	for _, source := range value.SourceObjectRefs {
		sources = append(sources, wire.GatheringSourceRef{
			ObjectRef:    toWireObjectRef(source.ObjectRef),
			RouteID:      source.RouteID,
			SourceDigest: source.SourceDigest,
		})
	}
	return wire.GatheringPurpose{
		Title:            value.Title,
		Summary:          value.Summary,
		CoverRef:         toWireObjectRef(value.CoverRef),
		TopicRefs:        cloneStrings(value.TopicRefs),
		RequirementRefs:  cloneStrings(value.RequirementRefs),
		SourceObjectRefs: sources,
		CostNotice:       wire.GatheringCostNotice(value.CostNotice),
		CostDescription:  value.CostDescription,
	}
}

func toWireSchedule(
	value contract.GatheringSchedule,
) wire.GatheringSchedule {
	return wire.GatheringSchedule{
		Timezone:          value.Timezone,
		StartAt:           utcOrZero(value.StartAt),
		EndAt:             utcOrZero(value.EndAt),
		AdmissionClosesAt: utcOrZero(value.AdmissionClosesAt),
	}
}

func toWirePlace(value contract.GatheringPlace) wire.GatheringPlace {
	return wire.GatheringPlace{
		Mode:              wire.GatheringPlaceMode(value.Mode),
		CoarsePlaceRef:    toWireObjectRef(value.CoarsePlaceRef),
		CoarsePlaceLabel:  value.CoarsePlaceLabel,
		ExactMeetingPoint: value.ExactMeetingPoint,
		OnlineLocationRef: value.OnlineLocationRef,
	}
}

func toWirePolicySet(
	value contract.GatheringPolicySet,
) wire.GatheringPolicySet {
	questions := make(
		[]wire.GatheringApplicationQuestion,
		0,
		len(value.ApplicationQuestions),
	)
	for _, question := range value.ApplicationQuestions {
		options := make(
			[]wire.GatheringApplicationQuestionOption,
			0,
			len(question.Options),
		)
		for _, option := range question.Options {
			options = append(options, wire.GatheringApplicationQuestionOption{
				OptionID: option.OptionID,
				Label:    option.Label,
			})
		}
		questions = append(questions, wire.GatheringApplicationQuestion{
			QuestionID: question.QuestionID,
			Prompt:     question.Prompt,
			Kind:       wire.GatheringApplicationQuestionKind(question.Kind),
			Options:    options,
			Required:   question.Required,
		})
	}
	return wire.GatheringPolicySet{
		AudiencePolicy: wire.GatheringAudiencePolicy(value.AudiencePolicy),
		AdmissionPolicy: wire.GatheringAdmissionPolicy(
			value.AdmissionPolicy,
		),
		CapacityPolicy: wire.GatheringCapacityPolicy{
			MaxParticipants: value.CapacityPolicy.MaxParticipants,
		},
		DisclosurePolicy:     toWireDisclosurePolicy(value.DisclosurePolicy),
		ApplicationQuestions: questions,
		RiskControlPolicyRef: value.RiskControlPolicyRef,
		PolicyDecisionRef:    value.PolicyDecisionRef,
		PolicyDigest:         value.PolicyDigest,
		ObligationDigest:     value.ObligationDigest,
	}
}

func toWireDisclosurePolicy(
	value contract.GatheringDisclosurePolicy,
) wire.GatheringDisclosurePolicy {
	return wire.GatheringDisclosurePolicy{
		TimeDisclosure: wire.GatheringTimeDisclosure(
			value.TimeDisclosure,
		),
		PlaceDisclosure: wire.GatheringPlaceDisclosure(
			value.PlaceDisclosure,
		),
		RosterDisclosure: wire.GatheringRosterDisclosure(
			value.RosterDisclosure,
		),
	}
}

func toWireAdmissionControl(
	value contract.GatheringAdmissionControl,
) wire.GatheringAdmissionControl {
	return wire.GatheringAdmissionControl{
		Status:            wire.GatheringAdmissionControlStatus(value.Status),
		PausedByPersonaID: value.PausedByPersonaID,
		ReasonRef:         value.ReasonRef,
		PausedAt:          utcOrZero(value.PausedAt),
		Version:           value.Version,
	}
}

func toWireOutcome(value contract.GatheringOutcome) wire.GatheringOutcome {
	evidence := make(
		[]wire.CanonicalObjectRef,
		0,
		len(value.EvidenceRefs),
	)
	for _, reference := range value.EvidenceRefs {
		evidence = append(evidence, toWireObjectRef(reference))
	}
	return wire.GatheringOutcome{
		Status:                   wire.GatheringOutcomeStatus(value.Status),
		IndependentEvidenceCount: value.IndependentEvidenceCount,
		EvidenceRefs:             evidence,
		CalculatedAt:             utcOrZero(value.CalculatedAt),
		CalculationDigest:        value.CalculationDigest,
	}
}

func toWireObjectRef(value CanonicalObjectRef) wire.CanonicalObjectRef {
	return wire.CanonicalObjectRef{
		ObjectTypeRef: value.ObjectTypeRef,
		ObjectID:      value.ObjectID,
	}
}

func publicCardDigest(card PublicCard) string {
	return digestStrings(
		card.GatheringID,
		strconv.FormatInt(card.AggregateVersion, 10),
		card.CurrentGatheringRevisionID,
		strconv.FormatInt(card.CurrentGatheringRevisionNumber, 10),
		string(card.LifecycleStatus),
		string(card.OutcomeStatus),
	)
}

func digestStrings(values ...string) string {
	digest := sha256.Sum256([]byte(strings.Join(values, "\x00")))
	return hex.EncodeToString(digest[:])
}

func isActive(value *ParticipationRecord) bool {
	return value != nil &&
		value.State == contract.GatheringParticipationStateActive
}

func utcOrZero(value time.Time) time.Time {
	if value.IsZero() {
		return time.Time{}
	}
	return value.UTC()
}

func cloneTimePointer(value time.Time) *time.Time {
	if value.IsZero() {
		return nil
	}
	copy := value.UTC()
	return &copy
}

func cloneOptionalTimePointer(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	return cloneTimePointer(*value)
}

func cloneStrings(values []string) []string {
	if values == nil {
		return []string{}
	}
	return append([]string(nil), values...)
}

func cloneAnswers(values []ApplicationAnswer) []ApplicationAnswer {
	result := make([]ApplicationAnswer, 0, len(values))
	for _, value := range values {
		value.SelectedOptionIds = cloneStrings(value.SelectedOptionIds)
		result = append(result, value)
	}
	return result
}
