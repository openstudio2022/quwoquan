package gathering

import (
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

type AppendMaterialRevisionInput struct {
	ActorPersonaID  string
	ExpectedVersion int64
	Purpose         contract.GatheringPurpose
	Schedule        contract.GatheringSchedule
	Place           contract.GatheringPlace
	PolicySet       contract.GatheringPolicySet
	HostBinding     contract.HostBinding
	OccurredAt      time.Time
}

// AppendMaterialGatheringRevision 只追加重大承诺修订；Participation acknowledgement
// 由 application 层调用 Scope C hook 在同一 owner mutation 内处理。
func AppendMaterialGatheringRevision(
	current Gathering,
	input AppendMaterialRevisionInput,
) (Gathering, contract.GatheringRevision, bool, error) {
	if err := requireLifecycleMutation(
		current,
		input.ActorPersonaID,
		input.ExpectedVersion,
		input.OccurredAt,
	); err != nil {
		return Gathering{}, contract.GatheringRevision{}, false, err
	}
	if current.LifecycleStatus == contract.GatheringLifecycleStatusCancelled ||
		current.LifecycleStatus == contract.GatheringLifecycleStatusCompleted {
		return Gathering{}, contract.GatheringRevision{}, false, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if current.LifecycleStatus == contract.GatheringLifecycleStatusPublished &&
		ResolveTemporalPhase(current, input.OccurredAt.UTC()) != TemporalPhaseUpcoming {
		return Gathering{}, contract.GatheringRevision{}, false, gatheringerrors.ErrGatheringOperationNotAllowedInProgress
	}

	hostBinding := normalizeHostBinding(input.HostBinding)
	if !validHostAuthority(hostBinding, input.OccurredAt.UTC()) {
		return Gathering{}, contract.GatheringRevision{}, false, gatheringerrors.ErrGatheringHostAuthorityInvalid
	}
	purpose := normalizePurpose(input.Purpose)
	schedule := normalizeSchedule(input.Schedule)
	place := normalizePlace(input.Place)
	policySet := normalizePolicySet(input.PolicySet)
	if err := validateUpdatedCommitments(
		current.LifecycleStatus,
		purpose,
		schedule,
		place,
		policySet,
		input.OccurredAt.UTC(),
	); err != nil {
		return Gathering{}, contract.GatheringRevision{}, false, err
	}
	digest, err := revisionCommitmentDigest(purpose, schedule, place, policySet, hostBinding)
	if err != nil {
		return Gathering{}, contract.GatheringRevision{}, false, err
	}
	if current.CurrentGatheringRevisionID != "" && len(current.Revisions) != 0 {
		latest := current.Revisions[len(current.Revisions)-1]
		if latest.Digest == digest {
			return current, latest, false, nil
		}
	}

	revisionNumber := current.CurrentGatheringRevisionNumber + 1
	revision, err := newGatheringRevision(
		current.ID,
		revisionNumber,
		purpose,
		schedule,
		place,
		policySet,
		hostBinding,
		digest,
		true,
		input.ActorPersonaID,
		input.OccurredAt.UTC(),
	)
	if err != nil {
		return Gathering{}, contract.GatheringRevision{}, false, err
	}
	next := current
	next.Purpose = purpose
	next.Schedule = schedule
	next.Place = place
	next.PolicySet = policySet
	next.HostBinding = hostBinding
	next.Revisions = append(
		append([]contract.GatheringRevision(nil), current.Revisions...),
		revision,
	)
	next.CurrentGatheringRevisionID = revision.RevisionID
	next.CurrentGatheringRevisionNumber = revision.RevisionNumber
	touchLifecycle(&next, input.OccurredAt)
	return next, revision, true, nil
}

func initialGatheringRevision(
	gatheringID string,
	creatorPersonaID string,
	hostBinding contract.HostBinding,
	purpose contract.GatheringPurpose,
	schedule contract.GatheringSchedule,
	place contract.GatheringPlace,
	policySet contract.GatheringPolicySet,
	createdAt time.Time,
) contract.GatheringRevision {
	digest, err := revisionCommitmentDigest(purpose, schedule, place, policySet, hostBinding)
	if err != nil {
		panic("canonical Gathering revision digest must be serializable: " + err.Error())
	}
	revision, err := newGatheringRevision(
		gatheringID,
		1,
		purpose,
		schedule,
		place,
		policySet,
		hostBinding,
		digest,
		false,
		creatorPersonaID,
		createdAt,
	)
	if err != nil {
		panic("canonical initial Gathering revision must be constructible: " + err.Error())
	}
	return revision
}

func newGatheringRevision(
	gatheringID string,
	revisionNumber int64,
	purpose contract.GatheringPurpose,
	schedule contract.GatheringSchedule,
	place contract.GatheringPlace,
	policySet contract.GatheringPolicySet,
	hostBinding contract.HostBinding,
	digest string,
	materialChange bool,
	createdByPersonaID string,
	createdAt time.Time,
) (contract.GatheringRevision, error) {
	hostDigest, err := canonicalDigest(struct {
		Kind                 contract.GatheringHostSubjectKind
		ID                   string
		AuthorityEvidenceRef string
		AuthorityVersion     int64
	}{
		hostBinding.HostSubjectKind,
		hostBinding.HostSubjectID,
		hostBinding.AuthorityEvidenceRef,
		hostBinding.AuthorityVersion,
	})
	if err != nil {
		return contract.GatheringRevision{}, err
	}
	identityDigest, err := canonicalDigest(struct {
		GatheringID    string
		RevisionNumber int64
		Digest         string
	}{
		strings.TrimSpace(gatheringID),
		revisionNumber,
		digest,
	})
	if err != nil {
		return contract.GatheringRevision{}, err
	}
	return contract.GatheringRevision{
		RevisionID:     "gathering_revision_" + identityDigest[:32],
		RevisionNumber: revisionNumber,
		Purpose:        purpose,
		Schedule:       schedule,
		Place:          place,
		PolicySet:      policySet,
		HostSnapshot: contract.GatheringHostSnapshot{
			HostSubjectKind:      hostBinding.HostSubjectKind,
			HostSubjectID:        hostBinding.HostSubjectID,
			AuthorityEvidenceRef: hostBinding.AuthorityEvidenceRef,
			AuthorityVersion:     hostBinding.AuthorityVersion,
			HostDigest:           hostDigest,
		},
		Digest:             digest,
		MaterialChange:     materialChange,
		CreatedByPersonaID: strings.TrimSpace(createdByPersonaID),
		CreatedAt:          createdAt.UTC(),
	}, nil
}

func revisionCommitmentDigest(
	purpose contract.GatheringPurpose,
	schedule contract.GatheringSchedule,
	place contract.GatheringPlace,
	policySet contract.GatheringPolicySet,
	hostBinding contract.HostBinding,
) (string, error) {
	return canonicalDigest(struct {
		Purpose      contract.GatheringPurpose
		Schedule     contract.GatheringSchedule
		Place        contract.GatheringPlace
		PolicySet    contract.GatheringPolicySet
		HostSnapshot struct {
			HostSubjectKind      contract.GatheringHostSubjectKind
			HostSubjectID        string
			AuthorityEvidenceRef string
			AuthorityVersion     int64
		}
	}{
		Purpose:   purpose,
		Schedule:  schedule,
		Place:     place,
		PolicySet: policySet,
		HostSnapshot: struct {
			HostSubjectKind      contract.GatheringHostSubjectKind
			HostSubjectID        string
			AuthorityEvidenceRef string
			AuthorityVersion     int64
		}{
			hostBinding.HostSubjectKind,
			hostBinding.HostSubjectID,
			hostBinding.AuthorityEvidenceRef,
			hostBinding.AuthorityVersion,
		},
	})
}

func validateUpdatedCommitments(
	status contract.GatheringLifecycleStatus,
	purpose contract.GatheringPurpose,
	schedule contract.GatheringSchedule,
	place contract.GatheringPlace,
	policySet contract.GatheringPolicySet,
	at time.Time,
) error {
	if !schedule.StartAt.IsZero() && !schedule.EndAt.IsZero() &&
		!schedule.EndAt.After(schedule.StartAt) {
		return gatheringerrors.ErrGatheringScheduleInvalid
	}
	if status != contract.GatheringLifecycleStatusPublished {
		return nil
	}
	if !completePurpose(purpose) || !completePlace(place) {
		return gatheringerrors.ErrGatheringDraftIncomplete
	}
	if !completeSchedule(schedule, at) {
		return gatheringerrors.ErrGatheringScheduleInvalid
	}
	return validatePublishPolicy(policySet)
}
