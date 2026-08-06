package gathering

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

var ErrHostAuthorityUnavailable = errors.New("Gathering Host authority owner unavailable")

type HostAuthorityReader interface {
	ReadHostAuthority(context.Context, model.HostAuthorityQuery) (model.HostAuthorityEvidence, error)
}

type PrepareHostCommand struct {
	HostBinding contract.HostBinding
}

type AssignCoHostCommand struct {
	GatheringID              string
	CoHostPersonaID          string
	AuthorityEvidenceRef     string
	AuthorityVersion         int64
	ExpectedGatheringVersion int64
}

type RevokeCoHostCommand struct {
	GatheringID                  string
	CoHostPersonaID              string
	ReasonRef                    string
	ExpectedGatheringVersion     int64
	ExpectedParticipationVersion int64
}

type TransferOrganizerCommand struct {
	GatheringID                  string
	NewPrimaryOrganizerPersonaID string
	AuthorityEvidenceRef         string
	AuthorityVersion             int64
	ExpectedGatheringVersion     int64
}

type AcknowledgeRevisionCommand struct {
	GatheringID                  string
	RevisionID                   string
	RevisionDigest               string
	Decision                     gatheringclient.GatheringRevisionAcknowledgementDecision
	ExpectedGatheringVersion     int64
	ExpectedParticipationVersion int64
}

type AttendanceCommand struct {
	GatheringID                  string
	EvidenceRefs                 []contract.CanonicalObjectRef
	ExpectedGatheringVersion     int64
	ExpectedParticipationVersion int64
}

type HostPreparation struct {
	HostBinding          contract.HostBinding
	OrganizerAssignments []contract.OrganizerAssignment
	AuditFact            model.AuditFact
}

type HostOutcomeCommandResult struct {
	gatheringclient.GatheringCommandResult
	AuditFact model.AuditFact `json:"-"`
}

type HostOutcomeFacade struct {
	store      ports.AggregateStore
	authority  HostAuthorityReader
	calculator model.OutcomeCalculator
	now        func() time.Time
}

func NewHostOutcomeFacade(
	store ports.AggregateStore,
	authority HostAuthorityReader,
) *HostOutcomeFacade {
	if store == nil || authority == nil {
		panic("Gathering HostOutcomeFacade requires AggregateStore and HostAuthorityReader")
	}
	return &HostOutcomeFacade{
		store: store, authority: authority,
		calculator: model.NewOutcomeCalculator(), now: time.Now,
	}
}

// InitializeCreatorParticipation satisfies Scope A's lifecycle hook. Organizer
// authority never creates a seat implicitly; only the explicit
// creatorParticipates flag creates a separate active Participation.
func (facade *HostOutcomeFacade) InitializeCreatorParticipation(
	current *contract.Gathering,
	creatorPersonaID string,
	creatorParticipates bool,
	occurredAt time.Time,
) error {
	if !creatorParticipates {
		return nil
	}
	creatorPersonaID = strings.TrimSpace(creatorPersonaID)
	if current == nil || creatorPersonaID == "" || occurredAt.IsZero() {
		return gatheringerrors.ErrGatheringTransitionForbidden
	}
	if model.ParticipationIndex(current.Participations, creatorPersonaID) >= 0 {
		return gatheringerrors.ErrGatheringParticipationConflict
	}
	if current.PolicySet.CapacityPolicy.MaxParticipants <=
		hostOutcomeOccupiedSeats(current.Participations, occurredAt) {
		return gatheringerrors.ErrGatheringCapacityFull
	}
	acknowledgement := contract.GatheringRevisionAcknowledgement{
		RevisionID:     current.CurrentGatheringRevisionID,
		RevisionNumber: current.CurrentGatheringRevisionNumber,
		Status:         contract.GatheringRevisionAcknowledgementStatusNotRequired,
	}
	if len(current.Revisions) != 0 {
		acknowledgement.RevisionDigest = current.Revisions[len(current.Revisions)-1].Digest
	}
	current.Participations = append(current.Participations, contract.GatheringParticipation{
		GatheringID:     current.ID,
		PersonaID:       creatorPersonaID,
		State:           contract.GatheringParticipationStateActive,
		AdmissionSource: contract.GatheringAdmissionSourceOpen,
		AttemptNo:       1,
		JoinedAt:        occurredAt.UTC(),
		Version:         1,
		Attendance: contract.GatheringAttendance{
			Status:       contract.GatheringAttendanceStatusNotDeclared,
			EvidenceRefs: []contract.CanonicalObjectRef{},
		},
		CurrentChangeAcknowledgement: acknowledgement,
	})
	return nil
}

func hostOutcomeOccupiedSeats(
	participations []contract.GatheringParticipation,
	evaluatedAt time.Time,
) int64 {
	var occupied int64
	for _, participation := range participations {
		switch participation.State {
		case contract.GatheringParticipationStateActive:
			occupied++
		case contract.GatheringParticipationStateInvitedPending:
			if !participation.SeatHoldUntil.IsZero() && evaluatedAt.Before(participation.SeatHoldUntil) {
				occupied++
			}
		}
	}
	return occupied
}

func (facade *HostOutcomeFacade) MarkActiveRevisionAcknowledgementsPending(
	current *contract.Gathering,
	revision contract.GatheringRevision,
	deadlineAt time.Time,
	_ time.Time,
) error {
	if current == nil ||
		revision.RevisionID != current.CurrentGatheringRevisionID ||
		revision.RevisionNumber != current.CurrentGatheringRevisionNumber {
		return gatheringerrors.ErrGatheringReconfirmationRequired
	}
	participations, err := model.RequireMaterialRevisionAcknowledgement(
		current.Participations,
		revision,
		deadlineAt,
	)
	if err != nil {
		return err
	}
	current.Participations = participations
	return nil
}

// Calculate satisfies Scope A's aggregate Complete calculator seam.
// CompleteSelf only contributes one Participation fact; this method alone
// selects occurred/did_not_happen/disputed/unverified after temporal end.
func (facade *HostOutcomeFacade) Calculate(
	current contract.Gathering,
	occurredAt time.Time,
) (contract.GatheringOutcome, error) {
	return facade.calculator.Calculate(model.OutcomeCalculationInput{
		TemporalPhase:  model.OutcomeTemporalPhaseAt(current.Schedule, occurredAt),
		Participations: current.Participations,
		CalculatedAt:   occurredAt.UTC(),
	})
}

// PrepareCreation validates typed owner authority before a Create mutation.
// The caller writes these values into the new root in the same transaction as
// createdByPersonaId; no Participation is synthesized.
func (facade *HostOutcomeFacade) PrepareCreation(
	ctx context.Context,
	command PrepareHostCommand,
) (HostPreparation, error) {
	_, actorPersonaID, err := trustedCommandContext(ctx)
	if err != nil {
		return HostPreparation{}, err
	}
	evaluatedAt := facade.now().UTC()
	query := authorityQuery(
		command.HostBinding,
		actorPersonaID,
		actorPersonaID,
		model.HostAuthorityCreateDraft,
		evaluatedAt,
	)
	evidence, err := facade.readAuthority(ctx, command.HostBinding, query)
	if err != nil {
		return HostPreparation{}, err
	}
	binding, assignments, fact, err := model.InitializeHostState(
		actorPersonaID,
		command.HostBinding,
		evidence,
		evaluatedAt,
	)
	if err != nil {
		return HostPreparation{}, mapHostOutcomeError(err)
	}
	return HostPreparation{
		HostBinding: binding, OrganizerAssignments: assignments, AuditFact: fact,
	}, nil
}

// RequirePublishAuthority is intentionally separate from ordinary organizer
// authorization. Publication revalidates the canonical Host owner evidence;
// ordinary management commands below depend only on active assignments.
func (facade *HostOutcomeFacade) RequirePublishAuthority(
	ctx context.Context,
	gatheringID string,
	expectedVersion int64,
) (model.AuditFact, error) {
	_, actorPersonaID, err := trustedCommandContext(ctx)
	if err != nil {
		return model.AuditFact{}, err
	}
	current, found, err := facade.store.Load(ctx, strings.TrimSpace(gatheringID))
	if err != nil {
		return model.AuditFact{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	if !found {
		return model.AuditFact{}, gatheringerrors.AppErrorFromGatheringNotFound("Gathering not found")
	}
	if current.Version != expectedVersion {
		return model.AuditFact{}, gatheringerrors.AppErrorFromGatheringVersionConflict("Gathering version changed")
	}
	if err := model.RequireOrganizer(current.OrganizerAssignments, actorPersonaID); err != nil {
		return model.AuditFact{}, mapHostOutcomeError(err)
	}
	query := authorityQuery(
		current.HostBinding,
		actorPersonaID,
		actorPersonaID,
		model.HostAuthorityPublish,
		facade.now().UTC(),
	)
	if _, err := facade.readAuthority(ctx, current.HostBinding, query); err != nil {
		return model.AuditFact{}, err
	}
	return model.AuditFact{
		Operation:            "PublishGathering",
		ActorPersonaID:       actorPersonaID,
		ParticipantPersonaID: actorPersonaID,
		HostSubjectKind:      query.HostSubjectKind,
		HostSubjectID:        query.HostSubjectID,
		AuthorityEvidenceRef: query.AuthorityEvidenceRef,
		AuthorityVersion:     query.AuthorityVersion,
		OccurredAt:           query.EvaluatedAt,
	}, nil
}

func (facade *HostOutcomeFacade) AssignCoHost(
	ctx context.Context,
	command AssignCoHostCommand,
) (HostOutcomeCommandResult, error) {
	currentContext, actorPersonaID, err := trustedCommandContext(ctx)
	if err != nil {
		return HostOutcomeCommandResult{}, err
	}
	gathering, found, err := facade.store.Load(ctx, strings.TrimSpace(command.GatheringID))
	if err != nil {
		return HostOutcomeCommandResult{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	if !found {
		return HostOutcomeCommandResult{}, gatheringerrors.AppErrorFromGatheringNotFound("Gathering not found")
	}
	if strings.TrimSpace(command.AuthorityEvidenceRef) != gathering.HostBinding.AuthorityEvidenceRef ||
		command.AuthorityVersion != gathering.HostBinding.AuthorityVersion {
		return HostOutcomeCommandResult{}, gatheringerrors.AppErrorFromGatheringHostAuthorityInvalid(
			"authority evidence does not match HostBinding",
		)
	}
	query := authorityQuery(
		gathering.HostBinding,
		actorPersonaID,
		command.CoHostPersonaID,
		model.HostAuthorityAssignOrganizer,
		facade.now().UTC(),
	)
	evidence, err := facade.readAuthority(ctx, gathering.HostBinding, query)
	if err != nil {
		return HostOutcomeCommandResult{}, err
	}
	return facade.commitMutation(
		ctx, actorPersonaID, currentContext.IdempotencyKey, "assign-co-host", command,
		command.GatheringID, gatheringevent.GatheringRevisionAppended,
		func(existing *contract.Gathering) (contract.Gathering, model.AuditFact, error) {
			if existing == nil {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringNotFound
			}
			if existing.Version != command.ExpectedGatheringVersion {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringVersionConflict
			}
			if !sameHostBinding(existing.HostBinding, gathering.HostBinding) {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringHostAuthorityInvalid
			}
			assignments, fact, mutationErr := model.AssignCoHost(
				existing.OrganizerAssignments,
				actorPersonaID,
				command.CoHostPersonaID,
				evidence,
				facade.now().UTC(),
			)
			if mutationErr != nil {
				return contract.Gathering{}, model.AuditFact{}, mutationErr
			}
			next := cloneHostOutcomeAggregate(*existing)
			next.OrganizerAssignments = assignments
			revision, revisionErr := organizerAssignmentRevision(next, actorPersonaID, fact.OccurredAt, false)
			if revisionErr != nil {
				return contract.Gathering{}, model.AuditFact{}, revisionErr
			}
			next.Revisions = append(next.Revisions, revision)
			next.CurrentGatheringRevisionID = revision.RevisionID
			next.CurrentGatheringRevisionNumber = revision.RevisionNumber
			fact.RevisionID = revision.RevisionID
			fact.RevisionNumber = revision.RevisionNumber
			advanceAggregate(&next, fact.OccurredAt)
			return next, fact, nil
		},
	)
}

func (facade *HostOutcomeFacade) RevokeCoHost(
	ctx context.Context,
	command RevokeCoHostCommand,
) (HostOutcomeCommandResult, error) {
	currentContext, actorPersonaID, err := trustedCommandContext(ctx)
	if err != nil {
		return HostOutcomeCommandResult{}, err
	}
	return facade.commitMutation(
		ctx, actorPersonaID, currentContext.IdempotencyKey, "revoke-co-host", command,
		command.GatheringID, gatheringevent.GatheringRevisionAppended,
		func(existing *contract.Gathering) (contract.Gathering, model.AuditFact, error) {
			if existing == nil {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringNotFound
			}
			if existing.Version != command.ExpectedGatheringVersion {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringVersionConflict
			}
			assignments, fact, mutationErr := model.RevokeCoHost(
				existing.OrganizerAssignments,
				actorPersonaID,
				command.CoHostPersonaID,
				facade.now().UTC(),
			)
			if mutationErr != nil {
				return contract.Gathering{}, model.AuditFact{}, mutationErr
			}
			next := cloneHostOutcomeAggregate(*existing)
			next.OrganizerAssignments = assignments
			revision, revisionErr := organizerAssignmentRevision(next, actorPersonaID, fact.OccurredAt, false)
			if revisionErr != nil {
				return contract.Gathering{}, model.AuditFact{}, revisionErr
			}
			next.Revisions = append(next.Revisions, revision)
			next.CurrentGatheringRevisionID = revision.RevisionID
			next.CurrentGatheringRevisionNumber = revision.RevisionNumber
			fact.RevisionID = revision.RevisionID
			fact.RevisionNumber = revision.RevisionNumber
			advanceAggregate(&next, fact.OccurredAt)
			return next, fact, nil
		},
	)
}

func (facade *HostOutcomeFacade) TransferOrganizer(
	ctx context.Context,
	command TransferOrganizerCommand,
) (HostOutcomeCommandResult, error) {
	currentContext, actorPersonaID, err := trustedCommandContext(ctx)
	if err != nil {
		return HostOutcomeCommandResult{}, err
	}
	gathering, found, err := facade.store.Load(ctx, strings.TrimSpace(command.GatheringID))
	if err != nil {
		return HostOutcomeCommandResult{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	if !found {
		return HostOutcomeCommandResult{}, gatheringerrors.AppErrorFromGatheringNotFound("Gathering not found")
	}
	if strings.TrimSpace(command.AuthorityEvidenceRef) != gathering.HostBinding.AuthorityEvidenceRef ||
		command.AuthorityVersion != gathering.HostBinding.AuthorityVersion {
		return HostOutcomeCommandResult{}, gatheringerrors.AppErrorFromGatheringHostAuthorityInvalid(
			"authority evidence does not match HostBinding",
		)
	}
	query := authorityQuery(
		gathering.HostBinding,
		actorPersonaID,
		command.NewPrimaryOrganizerPersonaID,
		model.HostAuthorityTransferOrganizer,
		facade.now().UTC(),
	)
	evidence, err := facade.readAuthority(ctx, gathering.HostBinding, query)
	if err != nil {
		return HostOutcomeCommandResult{}, err
	}
	return facade.commitMutation(
		ctx, actorPersonaID, currentContext.IdempotencyKey, "transfer-organizer", command,
		command.GatheringID, gatheringevent.GatheringRevisionAppended,
		func(existing *contract.Gathering) (contract.Gathering, model.AuditFact, error) {
			if existing == nil {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringNotFound
			}
			if existing.Version != command.ExpectedGatheringVersion {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringVersionConflict
			}
			if !sameHostBinding(existing.HostBinding, gathering.HostBinding) {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringHostAuthorityInvalid
			}
			now := facade.now().UTC()
			if model.OutcomeTemporalPhaseAt(existing.Schedule, now) !=
				model.OutcomeTemporalPhaseUpcoming {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringOperationNotAllowedInProgress
			}
			assignments, fact, mutationErr := model.TransferPrimaryOrganizer(
				existing.OrganizerAssignments,
				actorPersonaID,
				command.NewPrimaryOrganizerPersonaID,
				evidence,
				now,
			)
			if mutationErr != nil {
				return contract.Gathering{}, model.AuditFact{}, mutationErr
			}
			next := cloneHostOutcomeAggregate(*existing)
			next.OrganizerAssignments = assignments
			revision, revisionErr := organizerAssignmentRevision(next, actorPersonaID, now, true)
			if revisionErr != nil {
				return contract.Gathering{}, model.AuditFact{}, revisionErr
			}
			next.Revisions = append(next.Revisions, revision)
			next.CurrentGatheringRevisionID = revision.RevisionID
			next.CurrentGatheringRevisionNumber = revision.RevisionNumber
			next.Participations, revisionErr = model.RequireMaterialRevisionAcknowledgement(
				next.Participations,
				revision,
				next.Schedule.StartAt,
			)
			if revisionErr != nil {
				return contract.Gathering{}, model.AuditFact{}, revisionErr
			}
			fact.RevisionID = revision.RevisionID
			fact.RevisionNumber = revision.RevisionNumber
			advanceAggregate(&next, now)
			return next, fact, nil
		},
	)
}

func (facade *HostOutcomeFacade) AcknowledgeRevision(
	ctx context.Context,
	command AcknowledgeRevisionCommand,
) (HostOutcomeCommandResult, error) {
	currentContext, actorPersonaID, err := trustedCommandContext(ctx)
	if err != nil {
		return HostOutcomeCommandResult{}, err
	}
	return facade.commitMutation(
		ctx, actorPersonaID, currentContext.IdempotencyKey, "acknowledge-revision", command,
		command.GatheringID, gatheringevent.GatheringParticipationChanged,
		func(existing *contract.Gathering) (contract.Gathering, model.AuditFact, error) {
			if existing == nil {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringNotFound
			}
			if existing.Version != command.ExpectedGatheringVersion {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringVersionConflict
			}
			index := model.ParticipationIndex(existing.Participations, actorPersonaID)
			if index < 0 {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringActiveParticipationRequired
			}
			participation, fact, mutationErr := model.DecideRevisionAcknowledgement(
				existing.Participations[index],
				command.RevisionID,
				command.RevisionDigest,
				string(command.Decision),
				command.ExpectedParticipationVersion,
				facade.now().UTC(),
			)
			if mutationErr != nil {
				return contract.Gathering{}, model.AuditFact{}, mutationErr
			}
			next := cloneHostOutcomeAggregate(*existing)
			next.Participations[index] = participation
			advanceAggregate(&next, fact.OccurredAt)
			return next, fact, nil
		},
	)
}

func (facade *HostOutcomeFacade) DeclareArrival(
	ctx context.Context,
	command AttendanceCommand,
) (HostOutcomeCommandResult, error) {
	return facade.updateAttendance(ctx, "declare-arrival", "DeclareGatheringArrival", command, model.DeclareArrival)
}

func (facade *HostOutcomeFacade) DeclareLeaveEarly(
	ctx context.Context,
	command AttendanceCommand,
) (HostOutcomeCommandResult, error) {
	return facade.updateAttendance(ctx, "leave-early", "DeclareGatheringLeaveEarly", command, model.DeclareLeaveEarly)
}

func (facade *HostOutcomeFacade) CompleteSelf(
	ctx context.Context,
	command AttendanceCommand,
) (HostOutcomeCommandResult, error) {
	return facade.updateAttendance(ctx, "complete-self", "CompleteGatheringSelf", command, model.CompleteSelf)
}

type attendanceMutation func(
	contract.GatheringParticipation,
	int64,
	model.OutcomeTemporalPhase,
	[]contract.CanonicalObjectRef,
	time.Time,
) (contract.GatheringParticipation, model.AuditFact, error)

func (facade *HostOutcomeFacade) updateAttendance(
	ctx context.Context,
	digestOperation string,
	auditOperation string,
	command AttendanceCommand,
	apply attendanceMutation,
) (HostOutcomeCommandResult, error) {
	currentContext, actorPersonaID, err := trustedCommandContext(ctx)
	if err != nil {
		return HostOutcomeCommandResult{}, err
	}
	return facade.commitMutation(
		ctx, actorPersonaID, currentContext.IdempotencyKey, digestOperation, command,
		command.GatheringID, gatheringevent.GatheringParticipationChanged,
		func(existing *contract.Gathering) (contract.Gathering, model.AuditFact, error) {
			if existing == nil {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringNotFound
			}
			if existing.Version != command.ExpectedGatheringVersion {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringVersionConflict
			}
			index := model.ParticipationIndex(existing.Participations, actorPersonaID)
			if index < 0 {
				return contract.Gathering{}, model.AuditFact{}, gatheringerrors.ErrGatheringActiveParticipationRequired
			}
			now := facade.now().UTC()
			participation, fact, mutationErr := apply(
				existing.Participations[index],
				command.ExpectedParticipationVersion,
				model.OutcomeTemporalPhaseAt(existing.Schedule, now),
				command.EvidenceRefs,
				now,
			)
			if mutationErr != nil {
				return contract.Gathering{}, model.AuditFact{}, mutationErr
			}
			fact.Operation = auditOperation
			next := cloneHostOutcomeAggregate(*existing)
			next.Participations[index] = participation
			advanceAggregate(&next, fact.OccurredAt)
			return next, fact, nil
		},
	)
}

type hostOutcomeMutation func(*contract.Gathering) (contract.Gathering, model.AuditFact, error)

func (facade *HostOutcomeFacade) commitMutation(
	ctx context.Context,
	actorPersonaID string,
	idempotencyKey string,
	operationName string,
	payload any,
	gatheringID string,
	eventType string,
	mutation hostOutcomeMutation,
) (HostOutcomeCommandResult, error) {
	digest, err := commandDigest(actorPersonaID, operationName, payload)
	if err != nil {
		return HostOutcomeCommandResult{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	var auditFact model.AuditFact
	receipt, err := facade.store.Commit(ctx, ports.CommitRequest{
		GatheringID:      strings.TrimSpace(gatheringID),
		ReceiptKey:       receiptKey(actorPersonaID, idempotencyKey),
		CommandDigest:    digest,
		ReceiptExpiresAt: facade.now().UTC().Add(receiptRetention),
		EventType:        eventType,
		Mutate: func(existing *contract.Gathering) (contract.Gathering, error) {
			next, fact, mutationErr := mutation(existing)
			if mutationErr == nil {
				auditFact = fact
			}
			return next, mutationErr
		},
	})
	if err != nil {
		return HostOutcomeCommandResult{}, mapHostOutcomeError(err)
	}
	return hostOutcomeResult(receipt.Gathering, actorPersonaID, receipt.Replayed, auditFact), nil
}

func (facade *HostOutcomeFacade) readAuthority(
	ctx context.Context,
	binding contract.HostBinding,
	query model.HostAuthorityQuery,
) (model.HostAuthorityEvidence, error) {
	evidence, err := facade.authority.ReadHostAuthority(ctx, query)
	if err != nil {
		return model.HostAuthorityEvidence{}, gatheringerrors.AppErrorFromGatheringHostAuthorityInvalid(
			fmt.Sprintf("%v: %v", ErrHostAuthorityUnavailable, err),
		)
	}
	if err := model.ValidateHostAuthority(binding, query, evidence); err != nil {
		return model.HostAuthorityEvidence{}, mapHostOutcomeError(err)
	}
	return evidence, nil
}

func authorityQuery(
	binding contract.HostBinding,
	actorPersonaID string,
	organizerPersonaID string,
	action model.HostAuthorityAction,
	evaluatedAt time.Time,
) model.HostAuthorityQuery {
	return model.HostAuthorityQuery{
		HostSubjectKind:      binding.HostSubjectKind,
		HostSubjectID:        binding.HostSubjectID,
		ActorPersonaID:       strings.TrimSpace(actorPersonaID),
		OrganizerPersonaID:   strings.TrimSpace(organizerPersonaID),
		AuthorityEvidenceRef: binding.AuthorityEvidenceRef,
		AuthorityVersion:     binding.AuthorityVersion,
		Action:               action,
		EvaluatedAt:          evaluatedAt.UTC(),
	}
}

func sameHostBinding(left contract.HostBinding, right contract.HostBinding) bool {
	return left.HostSubjectKind == right.HostSubjectKind &&
		left.HostSubjectID == right.HostSubjectID &&
		left.AuthorityEvidenceRef == right.AuthorityEvidenceRef &&
		left.AuthorityVersion == right.AuthorityVersion &&
		left.AuthorityExpiresAt.Equal(right.AuthorityExpiresAt)
}

func organizerAssignmentRevision(
	current contract.Gathering,
	actorPersonaID string,
	createdAt time.Time,
	materialChange bool,
) (contract.GatheringRevision, error) {
	revisionNumber := current.CurrentGatheringRevisionNumber + 1
	hostDigest, err := digestValue(struct {
		Kind      contract.GatheringHostSubjectKind `json:"kind"`
		SubjectID string                            `json:"subjectId"`
		Evidence  string                            `json:"evidence"`
		Version   int64                             `json:"version"`
	}{
		Kind: current.HostBinding.HostSubjectKind, SubjectID: current.HostBinding.HostSubjectID,
		Evidence: current.HostBinding.AuthorityEvidenceRef, Version: current.HostBinding.AuthorityVersion,
	})
	if err != nil {
		return contract.GatheringRevision{}, err
	}
	revisionDigest, err := digestValue(struct {
		GatheringID string                         `json:"gatheringId"`
		Number      int64                          `json:"number"`
		Purpose     contract.GatheringPurpose      `json:"purpose"`
		Schedule    contract.GatheringSchedule     `json:"schedule"`
		Place       contract.GatheringPlace        `json:"place"`
		PolicySet   contract.GatheringPolicySet    `json:"policySet"`
		Organizers  []contract.OrganizerAssignment `json:"organizers"`
	}{
		GatheringID: current.ID, Number: revisionNumber, Purpose: current.Purpose,
		Schedule: current.Schedule, Place: current.Place, PolicySet: current.PolicySet,
		Organizers: current.OrganizerAssignments,
	})
	if err != nil {
		return contract.GatheringRevision{}, err
	}
	return contract.GatheringRevision{
		RevisionID:     fmt.Sprintf("%s-revision-%d-%s", current.ID, revisionNumber, revisionDigest[:16]),
		RevisionNumber: revisionNumber,
		Purpose:        current.Purpose,
		Schedule:       current.Schedule,
		Place:          current.Place,
		PolicySet:      current.PolicySet,
		HostSnapshot: contract.GatheringHostSnapshot{
			HostSubjectKind:      current.HostBinding.HostSubjectKind,
			HostSubjectID:        current.HostBinding.HostSubjectID,
			AuthorityEvidenceRef: current.HostBinding.AuthorityEvidenceRef,
			AuthorityVersion:     current.HostBinding.AuthorityVersion,
			HostDigest:           hostDigest,
		},
		Digest:             revisionDigest,
		MaterialChange:     materialChange,
		CreatedByPersonaID: strings.TrimSpace(actorPersonaID),
		CreatedAt:          createdAt.UTC(),
	}, nil
}

func digestValue(value any) (string, error) {
	encoded, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:]), nil
}

func hostOutcomeResult(
	value contract.Gathering,
	participantPersonaID string,
	replayed bool,
	fact model.AuditFact,
) HostOutcomeCommandResult {
	result := HostOutcomeCommandResult{
		GatheringCommandResult: gatheringclient.GatheringCommandResult{
			GatheringID:      value.ID,
			AggregateVersion: value.Version,
			LifecycleStatus: gatheringclient.GatheringLifecycleStatus(
				value.LifecycleStatus,
			),
			CurrentGatheringRevisionID:     value.CurrentGatheringRevisionID,
			CurrentGatheringRevisionNumber: value.CurrentGatheringRevisionNumber,
			OutcomeStatus: gatheringclient.GatheringOutcomeStatus(
				value.Outcome.Status,
			),
			ConversationID: value.ConversationID,
			RoomBindingStatus: gatheringclient.GatheringRoomBindingStatus(
				value.RoomBindingStatus,
			),
			IdempotentReplay: replayed,
		},
		AuditFact: fact,
	}
	if index := model.ParticipationIndex(value.Participations, participantPersonaID); index >= 0 {
		result.ParticipationState =
			gatheringclient.GatheringParticipationState(
				value.Participations[index].State,
			)
		result.ParticipationVersion = value.Participations[index].Version
	}
	return result
}

func advanceAggregate(value *contract.Gathering, occurredAt time.Time) {
	value.Version++
	value.UpdatedAt = occurredAt.UTC()
}

func cloneHostOutcomeAggregate(value contract.Gathering) contract.Gathering {
	value.OrganizerAssignments = append(
		[]contract.OrganizerAssignment(nil),
		value.OrganizerAssignments...,
	)
	value.Participations = append(
		[]contract.GatheringParticipation(nil),
		value.Participations...,
	)
	value.Revisions = append([]contract.GatheringRevision(nil), value.Revisions...)
	value.AvailabilityWatches = append([]contract.GatheringAvailabilityWatch(nil), value.AvailabilityWatches...)
	return value
}

func mapHostOutcomeError(err error) error {
	switch {
	case errors.Is(err, gatheringerrors.ErrGatheringNotFound):
		return gatheringerrors.AppErrorFromGatheringNotFound(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringPermissionDenied):
		return gatheringerrors.AppErrorFromGatheringPermissionDenied(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringHostAuthorityInvalid):
		return gatheringerrors.AppErrorFromGatheringHostAuthorityInvalid(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringOrganizerTransferRequired):
		return gatheringerrors.AppErrorFromGatheringOrganizerTransferRequired(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringOperationNotAllowedInProgress):
		return gatheringerrors.AppErrorFromGatheringOperationNotAllowedInProgress(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringActiveParticipationRequired):
		return gatheringerrors.AppErrorFromGatheringActiveParticipationRequired(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringReconfirmationRequired):
		return gatheringerrors.AppErrorFromGatheringReconfirmationRequired(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringReconfirmationExpired):
		return gatheringerrors.AppErrorFromGatheringReconfirmationExpired(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringAttendanceConflict):
		return gatheringerrors.AppErrorFromGatheringAttendanceConflict(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringOutcomeUnverified):
		return gatheringerrors.AppErrorFromGatheringOutcomeUnverified(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringOutcomeDisputed):
		return gatheringerrors.AppErrorFromGatheringOutcomeDisputed(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringParticipationConflict):
		return gatheringerrors.AppErrorFromGatheringParticipationConflict(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden):
		return gatheringerrors.AppErrorFromGatheringTransitionForbidden(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringVersionConflict), errors.Is(err, ports.ErrVersionConflict):
		return gatheringerrors.AppErrorFromGatheringVersionConflict(err.Error())
	case errors.Is(err, model.ErrInvalidArgument):
		return gatheringerrors.AppErrorFromGatheringTransitionForbidden(err.Error())
	default:
		return gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
}
