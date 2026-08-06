package gathering

import (
	"fmt"
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

type OutcomeTemporalPhase string

const (
	AcknowledgementDecisionAccept  = "accept"
	AcknowledgementDecisionDecline = "decline"

	OutcomeTemporalPhaseUpcoming   OutcomeTemporalPhase = "upcoming"
	OutcomeTemporalPhaseInProgress OutcomeTemporalPhase = "in_progress"
	OutcomeTemporalPhaseEnded      OutcomeTemporalPhase = "ended"
)

// RequireMaterialRevisionAcknowledgement installs a pending acknowledgement
// only on active Participation records. It never derives acceptance from
// silence, organizer status, or another participant's decision.
func RequireMaterialRevisionAcknowledgement(
	participations []contract.GatheringParticipation,
	revision contract.GatheringRevision,
	deadlineAt time.Time,
) ([]contract.GatheringParticipation, error) {
	if !revision.MaterialChange {
		return cloneParticipations(participations), nil
	}
	if strings.TrimSpace(revision.RevisionID) == "" ||
		strings.TrimSpace(revision.Digest) == "" ||
		revision.RevisionNumber <= 0 {
		return nil, fmt.Errorf("%w: material revision identity is incomplete", gatheringerrors.ErrGatheringReconfirmationRequired)
	}
	next := cloneParticipations(participations)
	for index := range next {
		if next[index].State != contract.GatheringParticipationStateActive {
			continue
		}
		next[index].CurrentChangeAcknowledgement = contract.GatheringRevisionAcknowledgement{
			RevisionID:     revision.RevisionID,
			RevisionNumber: revision.RevisionNumber,
			RevisionDigest: revision.Digest,
			Status:         contract.GatheringRevisionAcknowledgementStatusPending,
			DeadlineAt:     hostOutcomeUTCOrZero(deadlineAt),
		}
		next[index].Version++
	}
	return next, nil
}

func DecideRevisionAcknowledgement(
	current contract.GatheringParticipation,
	revisionID string,
	revisionDigest string,
	decision string,
	expectedVersion int64,
	decidedAt time.Time,
) (contract.GatheringParticipation, AuditFact, error) {
	if err := requireCurrentParticipation(current, expectedVersion); err != nil {
		return contract.GatheringParticipation{}, AuditFact{}, err
	}
	acknowledgement := current.CurrentChangeAcknowledgement
	revisionID = strings.TrimSpace(revisionID)
	revisionDigest = strings.TrimSpace(revisionDigest)
	if acknowledgement.Status != contract.GatheringRevisionAcknowledgementStatusPending ||
		acknowledgement.RevisionID != revisionID ||
		acknowledgement.RevisionDigest != revisionDigest {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf(
			"%w: acknowledgement must target the current material revision",
			gatheringerrors.ErrGatheringReconfirmationRequired,
		)
	}
	if decidedAt.IsZero() {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: acknowledgement time is required", gatheringerrors.ErrGatheringTransitionForbidden)
	}
	if !acknowledgement.DeadlineAt.IsZero() && !decidedAt.Before(acknowledgement.DeadlineAt) {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: acknowledgement deadline elapsed", gatheringerrors.ErrGatheringReconfirmationExpired)
	}

	next := cloneParticipation(current)
	operation := "AcknowledgeGatheringRevision"
	switch decision {
	case AcknowledgementDecisionAccept:
		next.CurrentChangeAcknowledgement.Status = contract.GatheringRevisionAcknowledgementStatusAccepted
	case AcknowledgementDecisionDecline:
		next.CurrentChangeAcknowledgement.Status = contract.GatheringRevisionAcknowledgementStatusDeclined
		operation = "DeclineGatheringRevision"
	default:
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: unsupported acknowledgement decision", gatheringerrors.ErrGatheringTransitionForbidden)
	}
	next.CurrentChangeAcknowledgement.AcknowledgedAt = decidedAt.UTC()
	next.Version++
	return next, AuditFact{
		Operation:            operation,
		ActorPersonaID:       current.PersonaID,
		ParticipantPersonaID: current.PersonaID,
		RevisionID:           acknowledgement.RevisionID,
		RevisionNumber:       acknowledgement.RevisionNumber,
		OccurredAt:           decidedAt.UTC(),
	}, nil
}

// ExitDeclinedRevision is deliberately separate from acknowledgement. It
// closes only the caller's Participation after an explicit decline; it does
// not mutate another participant or reinterpret a missing response as consent.
func ExitDeclinedRevision(
	current contract.GatheringParticipation,
	expectedVersion int64,
	exitedAt time.Time,
) (contract.GatheringParticipation, AuditFact, error) {
	if err := requireCurrentParticipation(current, expectedVersion); err != nil {
		return contract.GatheringParticipation{}, AuditFact{}, err
	}
	if current.CurrentChangeAcknowledgement.Status != contract.GatheringRevisionAcknowledgementStatusDeclined ||
		exitedAt.IsZero() {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: explicit revision decline is required before exit", gatheringerrors.ErrGatheringTransitionForbidden)
	}
	next := cloneParticipation(current)
	next.State = contract.GatheringParticipationStateClosed
	next.ClosedReason = contract.GatheringParticipationClosedReasonLeft
	next.ClosedAt = exitedAt.UTC()
	next.ClosedByPersonaID = current.PersonaID
	next.SeatHoldUntil = time.Time{}
	next.Version++
	return next, AuditFact{
		Operation:            "LeaveGathering",
		ActorPersonaID:       current.PersonaID,
		ParticipantPersonaID: current.PersonaID,
		RevisionID:           current.CurrentChangeAcknowledgement.RevisionID,
		RevisionNumber:       current.CurrentChangeAcknowledgement.RevisionNumber,
		OccurredAt:           exitedAt.UTC(),
	}, nil
}

func DeclareArrival(
	current contract.GatheringParticipation,
	expectedVersion int64,
	phase OutcomeTemporalPhase,
	evidenceRefs []contract.CanonicalObjectRef,
	declaredAt time.Time,
) (contract.GatheringParticipation, AuditFact, error) {
	if err := requireCurrentParticipation(current, expectedVersion); err != nil {
		return contract.GatheringParticipation{}, AuditFact{}, err
	}
	if phase != OutcomeTemporalPhaseInProgress || declaredAt.IsZero() || !validEvidenceRefs(evidenceRefs) {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: arrival requires in-progress typed evidence", gatheringerrors.ErrGatheringAttendanceConflict)
	}
	if current.Attendance.Status != contract.GatheringAttendanceStatusNotDeclared {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: arrival was already decided", gatheringerrors.ErrGatheringAttendanceConflict)
	}
	next := cloneParticipation(current)
	next.Attendance = contract.GatheringAttendance{
		Status:       contract.GatheringAttendanceStatusArrived,
		DeclaredAt:   declaredAt.UTC(),
		EvidenceRefs: cloneEvidenceRefs(evidenceRefs),
	}
	next.Version++
	return next, attendanceAuditFact("DeclareGatheringArrival", current.PersonaID, declaredAt), nil
}

func DeclareLeaveEarly(
	current contract.GatheringParticipation,
	expectedVersion int64,
	phase OutcomeTemporalPhase,
	evidenceRefs []contract.CanonicalObjectRef,
	declaredAt time.Time,
) (contract.GatheringParticipation, AuditFact, error) {
	if err := requireCurrentParticipation(current, expectedVersion); err != nil {
		return contract.GatheringParticipation{}, AuditFact{}, err
	}
	if phase != OutcomeTemporalPhaseInProgress || declaredAt.IsZero() ||
		current.Attendance.Status != contract.GatheringAttendanceStatusArrived ||
		!validEvidenceRefs(evidenceRefs) {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: early leave requires an arrived participant and typed evidence", gatheringerrors.ErrGatheringAttendanceConflict)
	}
	mergedEvidence := mergeEvidenceRefs(current.Attendance.EvidenceRefs, evidenceRefs)
	if len(mergedEvidence) > 16 {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: attendance evidence exceeds contract limit", gatheringerrors.ErrGatheringAttendanceConflict)
	}
	next := cloneParticipation(current)
	next.Attendance.Status = contract.GatheringAttendanceStatusLeftEarly
	next.Attendance.DeclaredAt = declaredAt.UTC()
	next.Attendance.EvidenceRefs = mergedEvidence
	next.Version++
	return next, attendanceAuditFact("DeclareGatheringLeaveEarly", current.PersonaID, declaredAt), nil
}

// CompleteSelf records only one participant's attendance. It never changes
// Gathering.lifecycleStatus or selects an aggregate Outcome.
func CompleteSelf(
	current contract.GatheringParticipation,
	expectedVersion int64,
	phase OutcomeTemporalPhase,
	evidenceRefs []contract.CanonicalObjectRef,
	declaredAt time.Time,
) (contract.GatheringParticipation, AuditFact, error) {
	if err := requireCurrentParticipation(current, expectedVersion); err != nil {
		return contract.GatheringParticipation{}, AuditFact{}, err
	}
	if phase != OutcomeTemporalPhaseEnded || declaredAt.IsZero() ||
		current.Attendance.Status != contract.GatheringAttendanceStatusArrived ||
		!validEvidenceRefs(evidenceRefs) {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: self completion requires prior arrival and ended phase evidence", gatheringerrors.ErrGatheringAttendanceConflict)
	}
	mergedEvidence := mergeEvidenceRefs(current.Attendance.EvidenceRefs, evidenceRefs)
	if len(mergedEvidence) > 16 {
		return contract.GatheringParticipation{}, AuditFact{}, fmt.Errorf("%w: attendance evidence exceeds contract limit", gatheringerrors.ErrGatheringAttendanceConflict)
	}
	next := cloneParticipation(current)
	next.Attendance.Status = contract.GatheringAttendanceStatusCompleted
	next.Attendance.DeclaredAt = declaredAt.UTC()
	next.Attendance.EvidenceRefs = mergedEvidence
	next.Version++
	return next, attendanceAuditFact("CompleteGatheringSelf", current.PersonaID, declaredAt), nil
}

func ParticipationIndex(participations []contract.GatheringParticipation, personaID string) int {
	personaID = strings.TrimSpace(personaID)
	for index := range participations {
		if participations[index].PersonaID == personaID {
			return index
		}
	}
	return -1
}

func requireCurrentParticipation(current contract.GatheringParticipation, expectedVersion int64) error {
	if strings.TrimSpace(current.GatheringID) == "" || strings.TrimSpace(current.PersonaID) == "" ||
		current.State != contract.GatheringParticipationStateActive {
		return fmt.Errorf("%w: active Participation required", gatheringerrors.ErrGatheringActiveParticipationRequired)
	}
	if current.Version != expectedVersion {
		return fmt.Errorf("%w: Participation version changed", gatheringerrors.ErrGatheringParticipationConflict)
	}
	return nil
}

func cloneParticipations(value []contract.GatheringParticipation) []contract.GatheringParticipation {
	result := make([]contract.GatheringParticipation, len(value))
	for index := range value {
		result[index] = cloneParticipation(value[index])
	}
	return result
}

func cloneParticipation(value contract.GatheringParticipation) contract.GatheringParticipation {
	value.ApplicationAnswers = append([]contract.GatheringApplicationAnswer(nil), value.ApplicationAnswers...)
	value.Attendance.EvidenceRefs = cloneEvidenceRefs(value.Attendance.EvidenceRefs)
	return value
}

func cloneEvidenceRefs(value []contract.CanonicalObjectRef) []contract.CanonicalObjectRef {
	return append([]contract.CanonicalObjectRef(nil), value...)
}

func validEvidenceRefs(value []contract.CanonicalObjectRef) bool {
	if len(value) == 0 || len(value) > 16 {
		return false
	}
	for _, reference := range value {
		if strings.TrimSpace(reference.ObjectTypeRef) == "" || strings.TrimSpace(reference.ObjectID) == "" {
			return false
		}
	}
	return true
}

func mergeEvidenceRefs(
	existing []contract.CanonicalObjectRef,
	appended []contract.CanonicalObjectRef,
) []contract.CanonicalObjectRef {
	result := cloneEvidenceRefs(existing)
	seen := make(map[string]struct{}, len(result))
	for _, reference := range result {
		seen[reference.ObjectTypeRef+"\x00"+reference.ObjectID] = struct{}{}
	}
	for _, reference := range appended {
		key := reference.ObjectTypeRef + "\x00" + reference.ObjectID
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		result = append(result, reference)
	}
	return result
}

func attendanceAuditFact(operation string, personaID string, occurredAt time.Time) AuditFact {
	return AuditFact{
		Operation:            operation,
		ActorPersonaID:       personaID,
		ParticipantPersonaID: personaID,
		OccurredAt:           occurredAt.UTC(),
	}
}
