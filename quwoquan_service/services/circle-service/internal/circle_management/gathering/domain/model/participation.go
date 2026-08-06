package gathering

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sort"
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

type GatheringParticipation = contract.GatheringParticipation
type GatheringApplicationAnswer = contract.GatheringApplicationAnswer
type GatheringParticipationState = contract.GatheringParticipationState
type GatheringAdmissionSource = contract.GatheringAdmissionSource
type GatheringParticipationClosedReason = contract.GatheringParticipationClosedReason

const (
	ParticipationStateInvitedPending     = contract.GatheringParticipationStateInvitedPending
	ParticipationStateApplicationPending = contract.GatheringParticipationStateApplicationPending
	ParticipationStateActive             = contract.GatheringParticipationStateActive
	ParticipationStateClosed             = contract.GatheringParticipationStateClosed

	AdmissionSourceOpen        = contract.GatheringAdmissionSourceOpen
	AdmissionSourceApplication = contract.GatheringAdmissionSourceApplication
	AdmissionSourceInvitation  = contract.GatheringAdmissionSourceInvitation

	ClosedReasonDeclined      = contract.GatheringParticipationClosedReasonDeclined
	ClosedReasonRevoked       = contract.GatheringParticipationClosedReasonRevoked
	ClosedReasonExpired       = contract.GatheringParticipationClosedReasonExpired
	ClosedReasonWithdrawn     = contract.GatheringParticipationClosedReasonWithdrawn
	ClosedReasonRejected      = contract.GatheringParticipationClosedReasonRejected
	ClosedReasonLeft          = contract.GatheringParticipationClosedReasonLeft
	ClosedReasonRemoved       = contract.GatheringParticipationClosedReasonRemoved
	ClosedReasonSafetyRemoved = contract.GatheringParticipationClosedReasonSafetyRemoved
)

type ParticipationCommandInput struct {
	ActorPersonaID               string
	ParticipantPersonaID         string
	ExpectedGatheringVersion     int64
	ExpectedParticipationVersion int64
	OccurredAt                   time.Time
}

type ApplyParticipationInput struct {
	ParticipationCommandInput
	Answers []GatheringApplicationAnswer
}

type ReviewParticipationInput struct {
	ParticipationCommandInput
	Decision  gatheringclient.GatheringApplicationReviewDecision
	ReasonRef string
}

type InviteParticipationInput struct {
	ParticipationCommandInput
	SeatHoldUntil time.Time
}

type CloseParticipationInput struct {
	ParticipationCommandInput
	ReasonRef string
}

// JoinOpen atomically starts a new open-admission attempt and consumes one
// seat. A closed row is reused with attemptNo+1; a second row is never added.
func JoinOpen(current Gathering, input ParticipationCommandInput) (Gathering, error) {
	if err := validateParticipationInput(current, input); err != nil {
		return Gathering{}, err
	}
	if err := requireSelfParticipation(input); err != nil {
		return Gathering{}, err
	}
	if current.PolicySet.AdmissionPolicy != contract.GatheringAdmissionPolicyOpen {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if err := requireAdmissionAccepting(current, input.OccurredAt, true); err != nil {
		return Gathering{}, err
	}
	next, index, attemptNo, participationVersion, err := prepareParticipationAttempt(current, input)
	if err != nil {
		return Gathering{}, err
	}
	next.Participations[index] = newParticipation(
		next.ID,
		input.ParticipantPersonaID,
		ParticipationStateActive,
		AdmissionSourceOpen,
		attemptNo,
		participationVersion,
		input.OccurredAt,
	)
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

// Apply creates application_pending after validating the policy-defined typed
// questions. Applications do not consume capacity, but a full Gathering does
// not accept new applications because there is no automatic waitlist.
func Apply(current Gathering, input ApplyParticipationInput) (Gathering, error) {
	if err := validateParticipationInput(current, input.ParticipationCommandInput); err != nil {
		return Gathering{}, err
	}
	if err := requireSelfParticipation(input.ParticipationCommandInput); err != nil {
		return Gathering{}, err
	}
	if current.PolicySet.AdmissionPolicy != contract.GatheringAdmissionPolicyApproval {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if err := requireAdmissionAccepting(current, input.OccurredAt, true); err != nil {
		return Gathering{}, err
	}
	answers, err := normalizeApplicationAnswers(current.PolicySet.ApplicationQuestions, input.Answers)
	if err != nil {
		return Gathering{}, err
	}
	next, index, attemptNo, participationVersion, err := prepareParticipationAttempt(
		current,
		input.ParticipationCommandInput,
	)
	if err != nil {
		return Gathering{}, err
	}
	participation := newParticipation(
		next.ID,
		input.ParticipantPersonaID,
		ParticipationStateApplicationPending,
		AdmissionSourceApplication,
		attemptNo,
		participationVersion,
		input.OccurredAt,
	)
	participation.ApplicationAnswers = answers
	participation.ReviewExpectedBy = admissionReviewExpectedBy(next, input.OccurredAt)
	next.Participations[index] = participation
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

func WithdrawApplication(current Gathering, input ParticipationCommandInput) (Gathering, error) {
	if err := requireSelfParticipation(input); err != nil {
		return Gathering{}, err
	}
	return closeParticipation(
		current,
		CloseParticipationInput{ParticipationCommandInput: input},
		ParticipationStateApplicationPending,
		ClosedReasonWithdrawn,
	)
}

func ReviewApplication(current Gathering, input ReviewParticipationInput) (Gathering, error) {
	if err := validateParticipationInput(current, input.ParticipationCommandInput); err != nil {
		return Gathering{}, err
	}
	if !HasActiveOrganizerAuthority(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	index, participation, err := requireParticipationVersion(
		current,
		input.ParticipantPersonaID,
		input.ExpectedParticipationVersion,
	)
	if err != nil {
		return Gathering{}, err
	}
	if participation.State != ParticipationStateApplicationPending {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	next := cloneParticipationOwnedState(current)
	switch input.Decision {
	case gatheringclient.GatheringApplicationReviewDecisionApprove:
		if err := requireAdmissionAccepting(current, input.OccurredAt, true); err != nil {
			return Gathering{}, err
		}
		activateParticipation(&participation, input.OccurredAt)
	case gatheringclient.GatheringApplicationReviewDecisionReject:
		closeParticipationValue(
			&participation,
			ClosedReasonRejected,
			input.ActorPersonaID,
			input.ReasonRef,
			input.OccurredAt,
		)
	default:
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	next.Participations[index] = participation
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

// Invite reserves a seat in the same owner mutation that writes
// invited_pending. A hold at or before occurredAt is invalid.
func Invite(current Gathering, input InviteParticipationInput) (Gathering, error) {
	if err := validateParticipationInput(current, input.ParticipationCommandInput); err != nil {
		return Gathering{}, err
	}
	if !HasActiveOrganizerAuthority(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	if input.SeatHoldUntil.IsZero() || !input.SeatHoldUntil.After(input.OccurredAt) {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if err := requireAdmissionAccepting(current, input.OccurredAt, true); err != nil {
		return Gathering{}, err
	}
	next, index, attemptNo, participationVersion, err := prepareParticipationAttempt(
		current,
		input.ParticipationCommandInput,
	)
	if err != nil {
		return Gathering{}, err
	}
	participation := newParticipation(
		next.ID,
		input.ParticipantPersonaID,
		ParticipationStateInvitedPending,
		AdmissionSourceInvitation,
		attemptNo,
		participationVersion,
		input.OccurredAt,
	)
	participation.InvitedByPersonaID = strings.TrimSpace(input.ActorPersonaID)
	participation.SeatHoldUntil = input.SeatHoldUntil.UTC()
	next.Participations[index] = participation
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

func AcceptInvitation(current Gathering, input ParticipationCommandInput) (Gathering, error) {
	if err := validateParticipationInput(current, input); err != nil {
		return Gathering{}, err
	}
	if err := requireSelfParticipation(input); err != nil {
		return Gathering{}, err
	}
	index, participation, err := requireActionableInvitation(
		current,
		input,
	)
	if err != nil {
		return Gathering{}, err
	}
	if participation.SeatHoldUntil.IsZero() || !participation.SeatHoldUntil.After(input.OccurredAt) {
		return Gathering{}, gatheringerrors.ErrGatheringSeatHoldExpired
	}
	if err := requireAdmissionOpenForHeldSeat(current, input.OccurredAt); err != nil {
		return Gathering{}, err
	}
	// A live invitation already occupies its seat. Accepting changes the seat
	// owner state but does not consume a second seat, even when full=true.
	if CapacityAt(current, input.OccurredAt).OccupiedSeats > current.PolicySet.CapacityPolicy.MaxParticipants {
		return Gathering{}, gatheringerrors.ErrGatheringCapacityFull
	}
	next := cloneParticipationOwnedState(current)
	activateParticipation(&participation, input.OccurredAt)
	next.Participations[index] = participation
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

func DeclineInvitation(current Gathering, input ParticipationCommandInput) (Gathering, error) {
	if err := validateParticipationInput(current, input); err != nil {
		return Gathering{}, err
	}
	if err := requireSelfParticipation(input); err != nil {
		return Gathering{}, err
	}
	_, participation, err := requireActionableInvitation(
		current,
		input,
	)
	if err != nil {
		return Gathering{}, err
	}
	if participation.SeatHoldUntil.IsZero() || !participation.SeatHoldUntil.After(input.OccurredAt) {
		return Gathering{}, gatheringerrors.ErrGatheringInvitationExpired
	}
	return closeParticipation(
		current,
		CloseParticipationInput{ParticipationCommandInput: input},
		ParticipationStateInvitedPending,
		ClosedReasonDeclined,
	)
}

func RevokeInvitation(current Gathering, input CloseParticipationInput) (Gathering, error) {
	if !HasActiveOrganizerAuthority(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	return closeParticipation(
		current,
		input,
		ParticipationStateInvitedPending,
		ClosedReasonRevoked,
	)
}

func LeaveParticipation(current Gathering, input ParticipationCommandInput) (Gathering, error) {
	if err := requireSelfParticipation(input); err != nil {
		return Gathering{}, err
	}
	if IsPrimaryOrganizer(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringOrganizerTransferRequired
	}
	return closeParticipation(
		current,
		CloseParticipationInput{ParticipationCommandInput: input},
		ParticipationStateActive,
		ClosedReasonLeft,
	)
}

func RemoveParticipation(current Gathering, input CloseParticipationInput) (Gathering, error) {
	if !HasActiveOrganizerAuthority(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	return closeParticipation(
		current,
		input,
		ParticipationStateActive,
		ClosedReasonRemoved,
	)
}

// SafetyRemoveParticipation is an internal owner policy transition, not a
// second public operation. It shares Remove's aggregate boundary but records
// the irreversible safety reason used by all retry paths.
func SafetyRemoveParticipation(current Gathering, input CloseParticipationInput) (Gathering, error) {
	if !HasActiveOrganizerAuthority(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	return closeParticipation(
		current,
		input,
		ParticipationStateActive,
		ClosedReasonSafetyRemoved,
	)
}

func ReinstateParticipation(current Gathering, input CloseParticipationInput) (Gathering, error) {
	if err := validateParticipationInput(current, input.ParticipationCommandInput); err != nil {
		return Gathering{}, err
	}
	if !HasActiveOrganizerAuthority(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	index, participation, err := requireParticipationVersion(
		current,
		input.ParticipantPersonaID,
		input.ExpectedParticipationVersion,
	)
	if err != nil {
		return Gathering{}, err
	}
	if participation.State != ParticipationStateClosed ||
		participation.ClosedReason != ClosedReasonRemoved {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if err := requireAdmissionAccepting(current, input.OccurredAt, true); err != nil {
		return Gathering{}, err
	}
	next := cloneParticipationOwnedState(current)
	participation.AttemptNo++
	participation.AdmissionSource = AdmissionSourceInvitation
	participation.ReasonRef = strings.TrimSpace(input.ReasonRef)
	activateParticipation(&participation, input.OccurredAt)
	next.Participations[index] = participation
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

func FindParticipation(current Gathering, personaID string) (GatheringParticipation, bool) {
	personaID = strings.TrimSpace(personaID)
	index := -1
	for candidate := range current.Participations {
		if strings.TrimSpace(current.Participations[candidate].PersonaID) != personaID {
			continue
		}
		if index >= 0 {
			// A duplicate means the aggregate violates its root-owned identity
			// invariant. Do not select an arbitrary row.
			return GatheringParticipation{}, false
		}
		index = candidate
	}
	if index < 0 {
		return GatheringParticipation{}, false
	}
	return current.Participations[index], true
}

func HasActiveOrganizerAuthority(current Gathering, personaID string) bool {
	return hasActiveOrganizerAuthority(current, personaID)
}

func IsPrimaryOrganizer(current Gathering, personaID string) bool {
	personaID = strings.TrimSpace(personaID)
	for _, assignment := range current.OrganizerAssignments {
		if strings.TrimSpace(assignment.PersonaID) == personaID &&
			assignment.RevokedAt.IsZero() &&
			assignment.Role == contract.GatheringOrganizerRolePrimaryOrganizer {
			return true
		}
	}
	return false
}

func ApplicationAnswersDigest(
	questions []contract.GatheringApplicationQuestion,
	answers []GatheringApplicationAnswer,
) (string, error) {
	normalized, err := normalizeApplicationAnswers(questions, answers)
	if err != nil {
		return "", err
	}
	encoded, err := json.Marshal(normalized)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func normalizeApplicationAnswers(
	questions []contract.GatheringApplicationQuestion,
	answers []GatheringApplicationAnswer,
) ([]GatheringApplicationAnswer, error) {
	if len(questions) > 5 || len(answers) > len(questions) {
		return nil, gatheringerrors.ErrGatheringTransitionForbidden
	}
	questionByID := make(map[string]contract.GatheringApplicationQuestion, len(questions))
	questionOrder := make(map[string]int, len(questions))
	for index, question := range questions {
		questionID := strings.TrimSpace(question.QuestionID)
		if questionID == "" || len(question.Options) > 10 {
			return nil, gatheringerrors.ErrGatheringTransitionForbidden
		}
		if _, duplicate := questionByID[questionID]; duplicate {
			return nil, gatheringerrors.ErrGatheringTransitionForbidden
		}
		questionByID[questionID] = question
		questionOrder[questionID] = index
	}
	normalized := make([]GatheringApplicationAnswer, 0, len(answers))
	answered := make(map[string]struct{}, len(answers))
	for _, answer := range answers {
		answer.QuestionID = strings.TrimSpace(answer.QuestionID)
		answer.AnswerText = strings.TrimSpace(answer.AnswerText)
		if answer.QuestionID == "" || len([]byte(answer.AnswerText)) > 480 ||
			len(answer.SelectedOptionIds) > 10 {
			return nil, gatheringerrors.ErrGatheringTransitionForbidden
		}
		question, known := questionByID[answer.QuestionID]
		if !known {
			return nil, gatheringerrors.ErrGatheringTransitionForbidden
		}
		if _, duplicate := answered[answer.QuestionID]; duplicate {
			return nil, gatheringerrors.ErrGatheringTransitionForbidden
		}
		answered[answer.QuestionID] = struct{}{}

		options := make(map[string]struct{}, len(question.Options))
		for _, option := range question.Options {
			optionID := strings.TrimSpace(option.OptionID)
			if optionID == "" {
				return nil, gatheringerrors.ErrGatheringTransitionForbidden
			}
			if _, duplicate := options[optionID]; duplicate {
				return nil, gatheringerrors.ErrGatheringTransitionForbidden
			}
			options[optionID] = struct{}{}
		}
		selected := make([]string, 0, len(answer.SelectedOptionIds))
		selectedSet := make(map[string]struct{}, len(answer.SelectedOptionIds))
		for _, rawOptionID := range answer.SelectedOptionIds {
			optionID := strings.TrimSpace(rawOptionID)
			if _, allowed := options[optionID]; !allowed {
				return nil, gatheringerrors.ErrGatheringTransitionForbidden
			}
			if _, duplicate := selectedSet[optionID]; duplicate {
				return nil, gatheringerrors.ErrGatheringTransitionForbidden
			}
			selectedSet[optionID] = struct{}{}
			selected = append(selected, optionID)
		}
		sort.Strings(selected)
		answer.SelectedOptionIds = selected

		switch question.Kind {
		case contract.GatheringApplicationQuestionKindText:
			if len(selected) != 0 || (question.Required && answer.AnswerText == "") {
				return nil, gatheringerrors.ErrGatheringTransitionForbidden
			}
		case contract.GatheringApplicationQuestionKindSingleSelect:
			if answer.AnswerText != "" || len(selected) > 1 ||
				(question.Required && len(selected) != 1) {
				return nil, gatheringerrors.ErrGatheringTransitionForbidden
			}
		case contract.GatheringApplicationQuestionKindMultiSelect:
			if answer.AnswerText != "" || (question.Required && len(selected) == 0) {
				return nil, gatheringerrors.ErrGatheringTransitionForbidden
			}
		default:
			return nil, gatheringerrors.ErrGatheringTransitionForbidden
		}
		normalized = append(normalized, answer)
	}
	for questionID, question := range questionByID {
		if question.Required {
			if _, exists := answered[questionID]; !exists {
				return nil, gatheringerrors.ErrGatheringTransitionForbidden
			}
		}
	}
	sort.Slice(normalized, func(left, right int) bool {
		return questionOrder[normalized[left].QuestionID] < questionOrder[normalized[right].QuestionID]
	})
	return normalized, nil
}

func validateParticipationInput(current Gathering, input ParticipationCommandInput) error {
	if strings.TrimSpace(current.ID) == "" ||
		strings.TrimSpace(input.ActorPersonaID) == "" ||
		strings.TrimSpace(input.ParticipantPersonaID) == "" ||
		input.OccurredAt.IsZero() {
		return ErrInvalidArgument
	}
	if input.ExpectedGatheringVersion != current.Version {
		return gatheringerrors.ErrGatheringVersionConflict
	}
	return nil
}

func requireSelfParticipation(input ParticipationCommandInput) error {
	actorID := strings.TrimSpace(input.ActorPersonaID)
	participantID := strings.TrimSpace(input.ParticipantPersonaID)
	if actorID == "" || participantID == "" {
		return ErrInvalidArgument
	}
	if actorID != participantID {
		return gatheringerrors.ErrGatheringPermissionDenied
	}
	return nil
}

func prepareParticipationAttempt(
	current Gathering,
	input ParticipationCommandInput,
) (Gathering, int, int64, int64, error) {
	next := cloneParticipationOwnedState(current)
	index, participation, found, duplicate := participationIndex(next, input.ParticipantPersonaID)
	if duplicate {
		return Gathering{}, 0, 0, 0, gatheringerrors.ErrGatheringParticipationConflict
	}
	if !found {
		if input.ExpectedParticipationVersion != 0 {
			return Gathering{}, 0, 0, 0, gatheringerrors.ErrGatheringParticipationConflict
		}
		next.Participations = append(next.Participations, GatheringParticipation{})
		return next, len(next.Participations) - 1, 1, 1, nil
	}
	if participation.Version != input.ExpectedParticipationVersion {
		return Gathering{}, 0, 0, 0, gatheringerrors.ErrGatheringParticipationConflict
	}
	if participation.State == ParticipationStateActive {
		return Gathering{}, 0, 0, 0, gatheringerrors.ErrGatheringAlreadyActive
	}
	if participation.State != ParticipationStateClosed {
		return Gathering{}, 0, 0, 0, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if participation.ClosedReason == ClosedReasonSafetyRemoved ||
		participation.ClosedReason == ClosedReasonRemoved {
		return Gathering{}, 0, 0, 0, gatheringerrors.ErrGatheringTransitionForbidden
	}
	return next, index, participation.AttemptNo + 1, participation.Version + 1, nil
}

func closeParticipation(
	current Gathering,
	input CloseParticipationInput,
	requiredState GatheringParticipationState,
	reason GatheringParticipationClosedReason,
) (Gathering, error) {
	if err := validateParticipationInput(current, input.ParticipationCommandInput); err != nil {
		return Gathering{}, err
	}
	index, participation, err := requireParticipationVersion(
		current,
		input.ParticipantPersonaID,
		input.ExpectedParticipationVersion,
	)
	if err != nil {
		return Gathering{}, err
	}
	if participation.State != requiredState {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	next := cloneParticipationOwnedState(current)
	closeParticipationValue(
		&participation,
		reason,
		input.ActorPersonaID,
		input.ReasonRef,
		input.OccurredAt,
	)
	next.Participations[index] = participation
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

func requireParticipationVersion(
	current Gathering,
	personaID string,
	expectedVersion int64,
) (int, GatheringParticipation, error) {
	index, participation, found, duplicate := participationIndex(current, personaID)
	if duplicate || !found || participation.Version != expectedVersion {
		return 0, GatheringParticipation{}, gatheringerrors.ErrGatheringParticipationConflict
	}
	return index, participation, nil
}

func requireActionableInvitation(
	current Gathering,
	input ParticipationCommandInput,
) (int, GatheringParticipation, error) {
	index, participation, found, duplicate := participationIndex(
		current,
		input.ParticipantPersonaID,
	)
	if duplicate {
		return 0, GatheringParticipation{}, gatheringerrors.ErrGatheringParticipationConflict
	}
	if !found || participation.AdmissionSource != AdmissionSourceInvitation {
		return 0, GatheringParticipation{},
			gatheringerrors.ErrGatheringInvitationRecipientMismatch
	}
	if current.LifecycleStatus != contract.GatheringLifecycleStatusPublished ||
		participation.State != ParticipationStateInvitedPending {
		return 0, GatheringParticipation{}, gatheringerrors.ErrGatheringInvitationInactive
	}
	if participation.Version != input.ExpectedParticipationVersion {
		return 0, GatheringParticipation{}, gatheringerrors.ErrGatheringParticipationConflict
	}
	return index, participation, nil
}

func participationIndex(
	current Gathering,
	personaID string,
) (int, GatheringParticipation, bool, bool) {
	personaID = strings.TrimSpace(personaID)
	index := -1
	var result GatheringParticipation
	for candidate := range current.Participations {
		if strings.TrimSpace(current.Participations[candidate].PersonaID) != personaID {
			continue
		}
		if strings.TrimSpace(current.Participations[candidate].GatheringID) !=
			strings.TrimSpace(current.ID) ||
			index >= 0 {
			return 0, GatheringParticipation{}, false, true
		}
		index = candidate
		result = current.Participations[candidate]
	}
	return index, result, index >= 0, false
}

func newParticipation(
	gatheringID string,
	personaID string,
	state GatheringParticipationState,
	source GatheringAdmissionSource,
	attemptNo int64,
	version int64,
	occurredAt time.Time,
) GatheringParticipation {
	participation := GatheringParticipation{
		GatheringID:        strings.TrimSpace(gatheringID),
		PersonaID:          strings.TrimSpace(personaID),
		State:              state,
		AdmissionSource:    source,
		AttemptNo:          attemptNo,
		Version:            version,
		ApplicationAnswers: []GatheringApplicationAnswer{},
		Attendance: contract.GatheringAttendance{
			Status:       contract.GatheringAttendanceStatusNotDeclared,
			EvidenceRefs: []contract.CanonicalObjectRef{},
		},
		CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{
			Status: contract.GatheringRevisionAcknowledgementStatusNotRequired,
		},
	}
	if state == ParticipationStateActive {
		participation.JoinedAt = occurredAt.UTC()
	}
	return participation
}

func activateParticipation(participation *GatheringParticipation, occurredAt time.Time) {
	participation.State = ParticipationStateActive
	participation.ClosedReason = GatheringParticipationClosedReason("")
	participation.SeatHoldUntil = time.Time{}
	participation.JoinedAt = occurredAt.UTC()
	participation.ClosedAt = time.Time{}
	participation.ClosedByPersonaID = ""
	participation.ReasonRef = ""
	participation.ReviewExpectedBy = time.Time{}
	participation.Version++
}

func closeParticipationValue(
	participation *GatheringParticipation,
	reason GatheringParticipationClosedReason,
	closedByPersonaID string,
	reasonRef string,
	occurredAt time.Time,
) {
	participation.State = ParticipationStateClosed
	participation.ClosedReason = reason
	participation.SeatHoldUntil = time.Time{}
	participation.ClosedAt = occurredAt.UTC()
	participation.ClosedByPersonaID = strings.TrimSpace(closedByPersonaID)
	participation.ReasonRef = strings.TrimSpace(reasonRef)
	participation.ReviewExpectedBy = time.Time{}
	participation.Version++
}

func admissionReviewExpectedBy(current Gathering, occurredAt time.Time) time.Time {
	if !current.Schedule.AdmissionClosesAt.IsZero() &&
		current.Schedule.AdmissionClosesAt.After(occurredAt) {
		return current.Schedule.AdmissionClosesAt.UTC()
	}
	if !current.Schedule.StartAt.IsZero() && current.Schedule.StartAt.After(occurredAt) {
		return current.Schedule.StartAt.UTC()
	}
	return occurredAt.UTC()
}

func cloneParticipationOwnedState(current Gathering) Gathering {
	next := current
	next.Participations = append([]GatheringParticipation(nil), current.Participations...)
	for index := range next.Participations {
		next.Participations[index].ApplicationAnswers = append(
			[]GatheringApplicationAnswer(nil),
			current.Participations[index].ApplicationAnswers...,
		)
		for answerIndex := range next.Participations[index].ApplicationAnswers {
			next.Participations[index].ApplicationAnswers[answerIndex].SelectedOptionIds = append(
				[]string(nil),
				current.Participations[index].ApplicationAnswers[answerIndex].SelectedOptionIds...,
			)
		}
		next.Participations[index].Attendance.EvidenceRefs = append(
			[]contract.CanonicalObjectRef(nil),
			current.Participations[index].Attendance.EvidenceRefs...,
		)
	}
	next.AvailabilityWatches = append(
		[]contract.GatheringAvailabilityWatch(nil),
		current.AvailabilityWatches...,
	)
	return next
}

func touchParticipationRoot(current *Gathering, occurredAt time.Time) {
	current.Version++
	current.UpdatedAt = occurredAt.UTC()
}
