package gathering

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	circleerrors "quwoquan_service/services/circle-service/generated/circle_management/circle"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

const lifecycleReceiptRetention = 7 * 24 * time.Hour

// ResolveStandardPublishObligations 在 owner 侧派生发布义务。
// 端只声明 riskControlPolicyRef；policyDecisionRef / policyDigest /
// obligationDigest 属于治理证据，由服务对实际 policy 内容确定性计算，
// 不得要求客户端伪造。三者任一已显式提供（运营管控链路）时保持原值。
func ResolveStandardPublishObligations(
	policy contract.GatheringPolicySet,
) contract.GatheringPolicySet {
	if strings.TrimSpace(policy.RiskControlPolicyRef) == "" {
		return policy
	}
	if strings.TrimSpace(policy.PolicyDecisionRef) != "" ||
		strings.TrimSpace(policy.PolicyDigest) != "" ||
		strings.TrimSpace(policy.ObligationDigest) != "" {
		return policy
	}
	encoded, err := json.Marshal(struct {
		RiskControlPolicyRef string                             `json:"riskControlPolicyRef"`
		AudiencePolicy       contract.GatheringAudiencePolicy   `json:"audiencePolicy"`
		AdmissionPolicy      contract.GatheringAdmissionPolicy  `json:"admissionPolicy"`
		MaxParticipants      int64                              `json:"maxParticipants"`
		DisclosurePolicy     contract.GatheringDisclosurePolicy `json:"disclosurePolicy"`
	}{
		RiskControlPolicyRef: strings.TrimSpace(policy.RiskControlPolicyRef),
		AudiencePolicy:       policy.AudiencePolicy,
		AdmissionPolicy:      policy.AdmissionPolicy,
		MaxParticipants:      policy.CapacityPolicy.MaxParticipants,
		DisclosurePolicy:     policy.DisclosurePolicy,
	})
	if err != nil {
		// 编码失败时保持义务缺失，让 publish 按既有校验 fail-closed。
		return policy
	}
	policyDigest := sha256.Sum256(encoded)
	obligationDigest := sha256.Sum256(
		[]byte(strings.TrimSpace(policy.RiskControlPolicyRef) + ":standard-obligations"),
	)
	policy.PolicyDecisionRef = strings.TrimSpace(policy.RiskControlPolicyRef) + ":standard"
	policy.PolicyDigest = "sha256:" + hex.EncodeToString(policyDigest[:])
	policy.ObligationDigest = "sha256:" + hex.EncodeToString(obligationDigest[:])
	return policy
}

// ParticipationLifecycleHook 由 Scope C 实现。Scope A 只在聚合 mutation 内调用，
// 不在此处复制 creator Participation 或 revision acknowledgement 规则。
type ParticipationLifecycleHook interface {
	InitializeCreatorParticipation(
		current *model.Gathering,
		creatorPersonaID string,
		creatorParticipates bool,
		occurredAt time.Time,
	) error
	MarkActiveRevisionAcknowledgementsPending(
		current *model.Gathering,
		revision contract.GatheringRevision,
		deadlineAt time.Time,
		occurredAt time.Time,
	) error
}

// GatheringOutcomeCalculator 由 Scope C 的 evidence/attendance calculator 实现。
// Complete 不接收客户端指定的 Outcome。
type GatheringOutcomeCalculator interface {
	Calculate(current model.Gathering, occurredAt time.Time) (contract.GatheringOutcome, error)
}

type GatheringLifecycleHostAuthority interface {
	PrepareCreation(context.Context, PrepareHostCommand) (HostPreparation, error)
	RequirePublishAuthority(
		context.Context,
		string,
		int64,
	) (model.AuditFact, error)
}

// GatheringSafetyTerminationAuthorizer is the Trust & Safety policy seam.
// Implementations must fail closed with a canonical permission/control error.
type GatheringSafetyTerminationAuthorizer interface {
	AuthorizeSafetyTermination(
		ctx context.Context,
		request GatheringSafetyTerminationAuthorizationRequest,
	) error
}

const GatheringSafetyTerminationAction = "terminate_gathering"

type GatheringSafetyTerminationAuthorizationRequest struct {
	ActorPersonaID           string
	GatheringID              string
	Action                   string
	EvidenceRef              string
	DecisionRef              string
	ExpectedGatheringVersion int64
}

type CreateGatheringDraftCommand struct {
	HostBinding         contract.HostBinding
	CreatorParticipates bool
	Purpose             contract.GatheringPurpose
	Schedule            contract.GatheringSchedule
	Place               contract.GatheringPlace
	PolicySet           contract.GatheringPolicySet
}

type GatheringVersionCommand struct {
	GatheringID              string
	ExpectedGatheringVersion int64
}

type UpdateGatheringCommand struct {
	GatheringID               string
	ExpectedGatheringVersion  int64
	Purpose                   contract.GatheringPurpose
	Schedule                  contract.GatheringSchedule
	Place                     contract.GatheringPlace
	PolicySet                 contract.GatheringPolicySet
	HostBinding               contract.HostBinding
	AcknowledgementDeadlineAt time.Time
}

type GatheringReasonCommand struct {
	GatheringID              string
	ExpectedGatheringVersion int64
	ReasonRef                string
	EvidenceRefs             []contract.CanonicalObjectRef
}

type LifecycleCommandResult = gatheringclient.GatheringCommandResult

type LifecycleFacade struct {
	store          ports.AggregateStore
	targets        ports.TargetReader
	hosts          GatheringLifecycleHostAuthority
	participations ParticipationLifecycleHook
	outcomes       GatheringOutcomeCalculator
	safety         GatheringSafetyTerminationAuthorizer
	now            func() time.Time
}

func NewLifecycleFacade(
	store ports.AggregateStore,
	targets ports.TargetReader,
	hosts GatheringLifecycleHostAuthority,
	participations ParticipationLifecycleHook,
	outcomes GatheringOutcomeCalculator,
	safety GatheringSafetyTerminationAuthorizer,
) *LifecycleFacade {
	if store == nil || targets == nil || hosts == nil || participations == nil ||
		outcomes == nil || safety == nil {
		panic("Gathering LifecycleFacade requires store, target and host readers, Participation hook, Outcome calculator and safety authorizer")
	}
	return &LifecycleFacade{
		store: store, targets: targets, hosts: hosts,
		participations: participations, outcomes: outcomes,
		safety: safety, now: time.Now,
	}
}

func (facade *LifecycleFacade) CreateGatheringDraft(
	ctx context.Context,
	command CreateGatheringDraftCommand,
) (LifecycleCommandResult, error) {
	current, actorPersonaID, err := trustedLifecycleCommandContext(ctx)
	if err != nil {
		return LifecycleCommandResult{}, err
	}
	preparation, err := facade.hosts.PrepareCreation(
		ctx,
		PrepareHostCommand{HostBinding: command.HostBinding},
	)
	if err != nil {
		return LifecycleCommandResult{}, err
	}
	command.HostBinding = preparation.HostBinding
	command.PolicySet = ResolveStandardPublishObligations(command.PolicySet)
	if err := facade.requireNavigableSources(ctx, command.Purpose.SourceObjectRefs); err != nil {
		return LifecycleCommandResult{}, err
	}
	gatheringID := stableLifecycleID(actorPersonaID, current.IdempotencyKey)
	digest, err := lifecycleCommandDigest(actorPersonaID, "create-draft", command)
	if err != nil {
		return LifecycleCommandResult{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	receipt, err := facade.commit(ctx, ports.CommitRequest{
		GatheringID:      gatheringID,
		ReceiptKey:       lifecycleReceiptKey(actorPersonaID, current.IdempotencyKey),
		CommandDigest:    digest,
		ReceiptExpiresAt: facade.now().UTC().Add(lifecycleReceiptRetention),
		EventType:        gatheringevent.GatheringDraftCreated,
		Mutate: func(existing *model.Gathering) (model.Gathering, error) {
			if existing != nil {
				return model.Gathering{}, ports.ErrVersionConflict
			}
			now := facade.now().UTC()
			created, createErr := model.CreateGatheringDraft(model.CreateGatheringDraftInput{
				ID:                 gatheringID,
				CreatedByPersonaID: actorPersonaID,
				HostBinding:        command.HostBinding,
				Purpose:            command.Purpose,
				Schedule:           command.Schedule,
				Place:              command.Place,
				PolicySet:          command.PolicySet,
				CreatedAt:          now,
			})
			if createErr != nil {
				return model.Gathering{}, createErr
			}
			created.OrganizerAssignments = append(
				[]contract.OrganizerAssignment(nil),
				preparation.OrganizerAssignments...,
			)
			if hookErr := facade.participations.InitializeCreatorParticipation(
				&created,
				actorPersonaID,
				command.CreatorParticipates,
				now,
			); hookErr != nil {
				return model.Gathering{}, hookErr
			}
			return created, nil
		},
	})
	if err != nil {
		return LifecycleCommandResult{}, err
	}
	return lifecycleResultFrom(receipt.Gathering, receipt.Replayed), nil
}

func (facade *LifecycleFacade) PublishGathering(
	ctx context.Context,
	command GatheringVersionCommand,
) (LifecycleCommandResult, error) {
	if _, err := facade.hosts.RequirePublishAuthority(
		ctx,
		command.GatheringID,
		command.ExpectedGatheringVersion,
	); err != nil {
		return LifecycleCommandResult{}, err
	}
	return facade.mutate(
		ctx,
		"publish",
		gatheringevent.GatheringPublished,
		command.GatheringID,
		command,
		func(current model.Gathering, actor string, now time.Time) (model.Gathering, error) {
			return model.PublishGathering(
				current,
				actor,
				command.ExpectedGatheringVersion,
				now,
			)
		},
	)
}

func (facade *LifecycleFacade) UpdateGathering(
	ctx context.Context,
	command UpdateGatheringCommand,
) (LifecycleCommandResult, error) {
	if err := facade.requireNavigableSources(ctx, command.Purpose.SourceObjectRefs); err != nil {
		return LifecycleCommandResult{}, err
	}
	command.PolicySet = ResolveStandardPublishObligations(command.PolicySet)
	return facade.mutate(
		ctx,
		"update",
		gatheringevent.GatheringRevisionAppended,
		command.GatheringID,
		command,
		func(current model.Gathering, actor string, now time.Time) (model.Gathering, error) {
			next, revision, appended, appendErr := model.AppendMaterialGatheringRevision(
				current,
				model.AppendMaterialRevisionInput{
					ActorPersonaID:  actor,
					ExpectedVersion: command.ExpectedGatheringVersion,
					Purpose:         command.Purpose,
					Schedule:        command.Schedule,
					Place:           command.Place,
					PolicySet:       command.PolicySet,
					HostBinding:     command.HostBinding,
					OccurredAt:      now,
				},
			)
			if appendErr != nil || !appended {
				return next, appendErr
			}
			if hookErr := facade.participations.MarkActiveRevisionAcknowledgementsPending(
				&next,
				revision,
				command.AcknowledgementDeadlineAt,
				now,
			); hookErr != nil {
				return model.Gathering{}, hookErr
			}
			return next, nil
		},
	)
}

func (facade *LifecycleFacade) CancelGathering(
	ctx context.Context,
	command GatheringReasonCommand,
) (LifecycleCommandResult, error) {
	return facade.mutate(
		ctx,
		"cancel",
		gatheringevent.GatheringCancelled,
		command.GatheringID,
		command,
		func(current model.Gathering, actor string, now time.Time) (model.Gathering, error) {
			return model.CancelGathering(
				current,
				actor,
				command.ExpectedGatheringVersion,
				command.ReasonRef,
				now,
			)
		},
	)
}

func (facade *LifecycleFacade) CompleteGathering(
	ctx context.Context,
	command GatheringVersionCommand,
) (LifecycleCommandResult, error) {
	return facade.mutate(
		ctx,
		"complete",
		gatheringevent.GatheringCompleted,
		command.GatheringID,
		command,
		func(current model.Gathering, actor string, now time.Time) (model.Gathering, error) {
			outcome, calculateErr := facade.outcomes.Calculate(current, now)
			if calculateErr != nil {
				return model.Gathering{}, calculateErr
			}
			return model.CompleteGathering(
				current,
				actor,
				command.ExpectedGatheringVersion,
				outcome,
				now,
			)
		},
	)
}

func (facade *LifecycleFacade) EndGatheringEarly(
	ctx context.Context,
	command GatheringReasonCommand,
) (LifecycleCommandResult, error) {
	return facade.mutate(
		ctx,
		"end-early",
		gatheringevent.GatheringEndedEarly,
		command.GatheringID,
		command,
		func(current model.Gathering, actor string, now time.Time) (model.Gathering, error) {
			return model.EndGatheringEarly(
				current,
				actor,
				command.ExpectedGatheringVersion,
				command.ReasonRef,
				command.EvidenceRefs,
				now,
			)
		},
	)
}

func (facade *LifecycleFacade) SafetyTerminateGathering(
	ctx context.Context,
	command GatheringReasonCommand,
) (LifecycleCommandResult, error) {
	_, actorPersonaID, err := trustedLifecycleCommandContext(ctx)
	if err != nil {
		return LifecycleCommandResult{}, err
	}
	if err := facade.safety.AuthorizeSafetyTermination(
		ctx,
		GatheringSafetyTerminationAuthorizationRequest{
			ActorPersonaID:           actorPersonaID,
			GatheringID:              command.GatheringID,
			Action:                   GatheringSafetyTerminationAction,
			EvidenceRef:              gatheringSafetyEvidenceRef(command.EvidenceRefs),
			DecisionRef:              command.ReasonRef,
			ExpectedGatheringVersion: command.ExpectedGatheringVersion,
		},
	); err != nil {
		return LifecycleCommandResult{}, mapLifecycleError(err)
	}
	return facade.mutate(
		ctx,
		"safety-terminate",
		gatheringevent.GatheringSafetyTerminated,
		command.GatheringID,
		command,
		func(current model.Gathering, _ string, now time.Time) (model.Gathering, error) {
			return model.SafetyTerminateGathering(
				current,
				command.ExpectedGatheringVersion,
				command.ReasonRef,
				command.EvidenceRefs,
				now,
			)
		},
	)
}

func gatheringSafetyEvidenceRef(
	evidenceRefs []contract.CanonicalObjectRef,
) string {
	for _, ref := range evidenceRefs {
		if strings.TrimSpace(ref.ObjectTypeRef) == "content.report" &&
			strings.TrimSpace(ref.ObjectID) != "" {
			return "content.report/" + strings.TrimSpace(ref.ObjectID)
		}
	}
	return ""
}

type lifecycleMutation func(
	model.Gathering,
	string,
	time.Time,
) (model.Gathering, error)

func (facade *LifecycleFacade) mutate(
	ctx context.Context,
	operationName string,
	eventType string,
	gatheringID string,
	payload any,
	apply lifecycleMutation,
) (LifecycleCommandResult, error) {
	current, actorPersonaID, err := trustedLifecycleCommandContext(ctx)
	if err != nil {
		return LifecycleCommandResult{}, err
	}
	digest, err := lifecycleCommandDigest(actorPersonaID, operationName, payload)
	if err != nil {
		return LifecycleCommandResult{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	receipt, err := facade.commit(ctx, ports.CommitRequest{
		GatheringID:      strings.TrimSpace(gatheringID),
		ReceiptKey:       lifecycleReceiptKey(actorPersonaID, current.IdempotencyKey),
		CommandDigest:    digest,
		ReceiptExpiresAt: facade.now().UTC().Add(lifecycleReceiptRetention),
		EventType:        eventType,
		Mutate: func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return apply(*existing, actorPersonaID, facade.now().UTC())
		},
	})
	if err != nil {
		return LifecycleCommandResult{}, err
	}
	return lifecycleResultFrom(receipt.Gathering, receipt.Replayed), nil
}

func (facade *LifecycleFacade) commit(
	ctx context.Context,
	request ports.CommitRequest,
) (ports.CommitReceipt, error) {
	receipt, err := facade.store.Commit(ctx, request)
	if err == nil {
		return receipt, nil
	}
	return ports.CommitReceipt{}, mapLifecycleError(err)
}

func lifecycleResultFrom(
	value model.Gathering,
	replayed bool,
) LifecycleCommandResult {
	return LifecycleCommandResult{
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
	}
}

func (facade *LifecycleFacade) requireNavigableSources(
	ctx context.Context,
	sources []contract.GatheringSourceRef,
) error {
	for _, source := range sources {
		if err := facade.targets.RequireNavigable(ctx, source); err != nil {
			return gatheringerrors.AppErrorFromGatheringTargetUnavailable(err.Error())
		}
	}
	return nil
}

func trustedLifecycleCommandContext(
	ctx context.Context,
) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Validate(operation.ActorPersona) != nil ||
		strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", circleerrors.AppErrorFromInvalidArgument(
			"trusted persona and Idempotency-Key are required",
		)
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func stableLifecycleID(actorPersonaID, key string) string {
	digest := sha256.Sum256([]byte(
		"gathering\x00" + strings.TrimSpace(actorPersonaID) + "\x00" + strings.TrimSpace(key),
	))
	return "gathering_" + hex.EncodeToString(digest[:12])
}

func lifecycleReceiptKey(actorPersonaID, key string) string {
	return strings.TrimSpace(actorPersonaID) + ":" + strings.TrimSpace(key)
}

func lifecycleCommandDigest(
	actorPersonaID string,
	operationName string,
	payload any,
) (string, error) {
	encoded, err := json.Marshal(struct {
		ActorPersonaID string `json:"actorPersonaId"`
		OperationName  string `json:"operation"`
		Payload        any    `json:"payload"`
	}{
		strings.TrimSpace(actorPersonaID),
		operationName,
		payload,
	})
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:]), nil
}

func mapLifecycleError(err error) error {
	switch {
	case errors.Is(err, gatheringerrors.ErrGatheringNotFound):
		return gatheringerrors.AppErrorFromGatheringNotFound(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringPermissionDenied):
		return gatheringerrors.AppErrorFromGatheringPermissionDenied(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringDraftIncomplete):
		return gatheringerrors.AppErrorFromGatheringDraftIncomplete(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringHostAuthorityInvalid):
		return gatheringerrors.AppErrorFromGatheringHostAuthorityInvalid(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringPublishObligationMissing):
		return gatheringerrors.AppErrorFromGatheringPublishObligationMissing(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringDisclosureInvalid):
		return gatheringerrors.AppErrorFromGatheringDisclosureInvalid(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringScheduleInvalid):
		return gatheringerrors.AppErrorFromGatheringScheduleInvalid(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden):
		return gatheringerrors.AppErrorFromGatheringTransitionForbidden(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringCancellationWindowClosed):
		return gatheringerrors.AppErrorFromGatheringCancellationWindowClosed(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringOperationNotAllowedInProgress):
		return gatheringerrors.AppErrorFromGatheringOperationNotAllowedInProgress(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringOutcomeUnverified):
		return gatheringerrors.AppErrorFromGatheringOutcomeUnverified(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringOutcomeDisputed):
		return gatheringerrors.AppErrorFromGatheringOutcomeDisputed(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringControlRequired):
		return gatheringerrors.AppErrorFromGatheringControlRequired(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringSafetyTerminationDenied):
		return gatheringerrors.AppErrorFromGatheringSafetyTerminationDenied(
			"Gathering safety termination is not authorized",
		)
	case errors.Is(err, gatheringerrors.ErrGatheringSafetyAuthorityUnavailable):
		return gatheringerrors.AppErrorFromGatheringSafetyAuthorityUnavailable(
			"Gathering safety authority is unavailable",
		)
	case errors.Is(err, gatheringerrors.ErrGatheringRoomProvisionPending):
		return gatheringerrors.AppErrorFromGatheringRoomProvisionPending(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringRoomProvisionFailed):
		return gatheringerrors.AppErrorFromGatheringRoomProvisionFailed(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringVersionConflict),
		errors.Is(err, ports.ErrVersionConflict):
		return gatheringerrors.AppErrorFromGatheringVersionConflict(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringIdempotencyConflict):
		return gatheringerrors.AppErrorFromGatheringIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrInvalidLifecycleArgument):
		return circleerrors.AppErrorFromInvalidArgument(err.Error())
	default:
		return gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
}
