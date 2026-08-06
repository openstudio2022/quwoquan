package gathering

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

type OutcomeCalculationInput struct {
	TemporalPhase  OutcomeTemporalPhase
	Participations []contract.GatheringParticipation
	CalculatedAt   time.Time
}

// OutcomeCalculator is the aggregate-completion boundary. CompleteSelf feeds
// participant attendance into it; Scope A's lifecycle Complete is the only
// writer of lifecycle/outcome. The calculator never emits penalty or
// relationship directives.
type OutcomeCalculator struct {
	minimumIndependentEvidence int
}

func NewOutcomeCalculator() OutcomeCalculator {
	return OutcomeCalculator{minimumIndependentEvidence: 2}
}

func (calculator OutcomeCalculator) Calculate(
	input OutcomeCalculationInput,
) (contract.GatheringOutcome, error) {
	if input.CalculatedAt.IsZero() {
		return contract.GatheringOutcome{}, fmt.Errorf("%w: outcome calculation time is required", gatheringerrors.ErrGatheringTransitionForbidden)
	}
	if calculator.minimumIndependentEvidence < 2 {
		calculator.minimumIndependentEvidence = 2
	}
	if input.TemporalPhase != OutcomeTemporalPhaseEnded {
		return contract.GatheringOutcome{}, fmt.Errorf("%w: aggregate completion requires ended temporal phase", gatheringerrors.ErrGatheringTransitionForbidden)
	}

	positive := make(map[string][]contract.CanonicalObjectRef)
	negative := make(map[string][]contract.CanonicalObjectRef)
	for _, participation := range input.Participations {
		if participation.State != contract.GatheringParticipationStateActive ||
			!validEvidenceRefs(participation.Attendance.EvidenceRefs) {
			continue
		}
		personaID := strings.TrimSpace(participation.PersonaID)
		if personaID == "" {
			continue
		}
		switch participation.Attendance.Status {
		case contract.GatheringAttendanceStatusArrived,
			contract.GatheringAttendanceStatusLeftEarly,
			contract.GatheringAttendanceStatusCompleted:
			positive[personaID] = cloneEvidenceRefs(participation.Attendance.EvidenceRefs)
		case contract.GatheringAttendanceStatusNoShow:
			negative[personaID] = cloneEvidenceRefs(participation.Attendance.EvidenceRefs)
		}
	}

	status := contract.GatheringOutcomeStatusUnverified
	var independentCount int64
	selected := make(map[string][]contract.CanonicalObjectRef)
	switch {
	case len(positive) > 0 && len(negative) > 0:
		status = contract.GatheringOutcomeStatusDisputed
		independentCount = int64(len(positive) + len(negative))
		mergeParticipantEvidence(selected, positive)
		mergeParticipantEvidence(selected, negative)
	case len(positive) >= calculator.minimumIndependentEvidence:
		status = contract.GatheringOutcomeStatusOccurred
		independentCount = int64(len(positive))
		mergeParticipantEvidence(selected, positive)
	case len(negative) >= calculator.minimumIndependentEvidence:
		status = contract.GatheringOutcomeStatusDidNotHappen
		independentCount = int64(len(negative))
		mergeParticipantEvidence(selected, negative)
	default:
		mergeParticipantEvidence(selected, positive)
		mergeParticipantEvidence(selected, negative)
		independentCount = int64(len(positive) + len(negative))
	}
	return calculatedOutcome(
		status,
		independentCount,
		flattenParticipantEvidence(selected),
		sortedPersonaIDs(selected),
		input.CalculatedAt,
	)
}

func OutcomeTemporalPhaseAt(
	schedule contract.GatheringSchedule,
	evaluatedAt time.Time,
) OutcomeTemporalPhase {
	if evaluatedAt.IsZero() || schedule.StartAt.IsZero() || evaluatedAt.Before(schedule.StartAt) {
		return OutcomeTemporalPhaseUpcoming
	}
	if schedule.EndAt.IsZero() || evaluatedAt.Before(schedule.EndAt) {
		return OutcomeTemporalPhaseInProgress
	}
	return OutcomeTemporalPhaseEnded
}

func calculatedOutcome(
	status contract.GatheringOutcomeStatus,
	independentCount int64,
	evidenceRefs []contract.CanonicalObjectRef,
	personaIDs []string,
	calculatedAt time.Time,
) (contract.GatheringOutcome, error) {
	if (status == contract.GatheringOutcomeStatusOccurred ||
		status == contract.GatheringOutcomeStatusDidNotHappen) &&
		(independentCount < 2 || !validEvidenceRefs(evidenceRefs)) {
		return contract.GatheringOutcome{}, fmt.Errorf("%w: independent evidence threshold was not met", gatheringerrors.ErrGatheringOutcomeUnverified)
	}
	normalizedEvidence := normalizedEvidenceRefs(evidenceRefs)
	if len(normalizedEvidence) > 32 {
		return contract.GatheringOutcome{}, fmt.Errorf("%w: outcome evidence exceeds contract limit", gatheringerrors.ErrGatheringOutcomeUnverified)
	}
	digestPayload := struct {
		Status           contract.GatheringOutcomeStatus `json:"status"`
		IndependentCount int64                           `json:"independentCount"`
		PersonaIDs       []string                        `json:"personaIds"`
		EvidenceRefs     []contract.CanonicalObjectRef   `json:"evidenceRefs"`
		CalculatedAt     time.Time                       `json:"calculatedAt"`
	}{
		Status:           status,
		IndependentCount: independentCount,
		PersonaIDs:       append([]string(nil), personaIDs...),
		EvidenceRefs:     normalizedEvidence,
		CalculatedAt:     calculatedAt.UTC(),
	}
	encoded, err := json.Marshal(digestPayload)
	if err != nil {
		return contract.GatheringOutcome{}, err
	}
	sum := sha256.Sum256(encoded)
	return contract.GatheringOutcome{
		Status:                   status,
		IndependentEvidenceCount: independentCount,
		EvidenceRefs:             normalizedEvidence,
		CalculatedAt:             calculatedAt.UTC(),
		CalculationDigest:        hex.EncodeToString(sum[:]),
	}, nil
}

func mergeParticipantEvidence(
	target map[string][]contract.CanonicalObjectRef,
	source map[string][]contract.CanonicalObjectRef,
) {
	for personaID, refs := range source {
		target[personaID] = cloneEvidenceRefs(refs)
	}
}

func sortedPersonaIDs(value map[string][]contract.CanonicalObjectRef) []string {
	result := make([]string, 0, len(value))
	for personaID := range value {
		result = append(result, personaID)
	}
	sort.Strings(result)
	return result
}

func flattenParticipantEvidence(
	value map[string][]contract.CanonicalObjectRef,
) []contract.CanonicalObjectRef {
	var result []contract.CanonicalObjectRef
	for _, personaID := range sortedPersonaIDs(value) {
		result = append(result, value[personaID]...)
	}
	return normalizedEvidenceRefs(result)
}

func normalizedEvidenceRefs(value []contract.CanonicalObjectRef) []contract.CanonicalObjectRef {
	result := cloneEvidenceRefs(value)
	sort.Slice(result, func(left, right int) bool {
		if result[left].ObjectTypeRef == result[right].ObjectTypeRef {
			return result[left].ObjectID < result[right].ObjectID
		}
		return result[left].ObjectTypeRef < result[right].ObjectTypeRef
	})
	if len(result) == 0 {
		return []contract.CanonicalObjectRef{}
	}
	unique := result[:0]
	for _, reference := range result {
		if len(unique) > 0 &&
			unique[len(unique)-1].ObjectTypeRef == reference.ObjectTypeRef &&
			unique[len(unique)-1].ObjectID == reference.ObjectID {
			continue
		}
		unique = append(unique, reference)
	}
	return unique
}
