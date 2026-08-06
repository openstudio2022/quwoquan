// readiness_case: create-gathering-local
// readiness_case: publish-gathering-local
// readiness_case: cancel-gathering-local
// readiness_case: complete-gathering-local
package application_test

import (
	"context"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestScopeALifecycleFacadePersistsReceiptOutboxAndStableReplay(t *testing.T) {
	store := newScopeACommitStore()
	hook := &scopeAParticipationHook{}
	facade := app.NewLifecycleFacade(
		store,
		scopeATargetReader{},
		scopeAHostAuthority{},
		hook,
		scopeAOutcomeCalculator{},
		scopeAAllowSafetyAuthorizer{},
	)
	command := scopeACreateCommand(time.Now().UTC())
	ctx := scopeACommandContext("create-replay")

	first, err := facade.CreateGatheringDraft(ctx, command)
	if err != nil {
		t.Fatalf("first create: %v", err)
	}
	replayed, err := facade.CreateGatheringDraft(ctx, command)
	if err != nil {
		t.Fatalf("replayed create: %v", err)
	}
	if !replayed.IdempotentReplay || replayed.GatheringID != first.GatheringID ||
		replayed.AggregateVersion != first.AggregateVersion ||
		replayed.ConversationID != "" ||
		replayed.RoomBindingStatus !=
			gatheringclient.GatheringRoomBindingStatusPending {
		t.Fatalf("stale or inconsistent replay: first=%+v replay=%+v", first, replayed)
	}
	if hook.initializeCalls != 1 || store.outboxCount() != 1 || store.receiptCount() != 1 {
		t.Fatalf(
			"transaction evidence mismatch: init=%d outbox=%d receipts=%d",
			hook.initializeCalls,
			store.outboxCount(),
			store.receiptCount(),
		)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
func TestScopeALifecycleFacadePublishesRoomReadyDraftAndReplaysCanonicalReceipt(t *testing.T) {
	store := newScopeACommitStore()
	facade := app.NewLifecycleFacade(
		store,
		scopeATargetReader{},
		scopeAHostAuthority{},
		&scopeAParticipationHook{},
		scopeAOutcomeCalculator{},
		scopeAAllowSafetyAuthorizer{},
	)
	current := scopeAMustCreateModelDraft(t, time.Now().UTC())
	current.RoomBindingStatus = contract.GatheringRoomBindingStatusReady
	current.ConversationID = "conversation-publish-ready"
	store.values[current.ID] = current
	command := app.GatheringVersionCommand{
		GatheringID:              current.ID,
		ExpectedGatheringVersion: current.Version,
	}
	ctx := scopeACommandContext("publish-ready")

	first, err := facade.PublishGathering(ctx, command)
	if err != nil {
		t.Fatalf("publish room-ready draft: %v", err)
	}
	replayed, err := facade.PublishGathering(ctx, command)
	if err != nil {
		t.Fatalf("replay room-ready publish: %v", err)
	}
	stored, found, err := store.Load(context.Background(), current.ID)
	if err != nil || !found {
		t.Fatalf("load published Gathering: found=%v err=%v", found, err)
	}
	events := store.outboxEvents()
	if first.IdempotentReplay ||
		first.GatheringID != current.ID ||
		first.AggregateVersion != current.Version+1 ||
		first.LifecycleStatus != gatheringclient.GatheringLifecycleStatusPublished ||
		first.ConversationID != current.ConversationID ||
		first.RoomBindingStatus != gatheringclient.GatheringRoomBindingStatusReady ||
		first.CurrentGatheringRevisionID != current.CurrentGatheringRevisionID ||
		first.CurrentGatheringRevisionNumber != current.CurrentGatheringRevisionNumber {
		t.Fatalf("publish result violated canonical contract: current=%+v result=%+v", current, first)
	}
	if !replayed.IdempotentReplay ||
		replayed.GatheringID != first.GatheringID ||
		replayed.AggregateVersion != first.AggregateVersion ||
		replayed.LifecycleStatus != first.LifecycleStatus ||
		replayed.ConversationID != first.ConversationID ||
		replayed.RoomBindingStatus != first.RoomBindingStatus ||
		replayed.CurrentGatheringRevisionID != first.CurrentGatheringRevisionID ||
		replayed.CurrentGatheringRevisionNumber != first.CurrentGatheringRevisionNumber {
		t.Fatalf("publish replay did not return canonical receipt: first=%+v replay=%+v", first, replayed)
	}
	if stored.LifecycleStatus != contract.GatheringLifecycleStatusPublished ||
		stored.Version != current.Version+1 ||
		stored.ConversationID != current.ConversationID ||
		stored.RoomBindingStatus != contract.GatheringRoomBindingStatusReady ||
		len(events) != 1 ||
		events[0] != gatheringevent.GatheringPublished ||
		store.receiptCount() != 1 {
		t.Fatalf(
			"publish commit evidence mismatch: stored=%+v events=%v receipts=%d",
			stored,
			events,
			store.receiptCount(),
		)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-003
func TestScopeALifecycleFacadeCallsAckHookOnlyForMaterialRevision(t *testing.T) {
	store := newScopeACommitStore()
	hook := &scopeAParticipationHook{}
	facade := app.NewLifecycleFacade(
		store,
		scopeATargetReader{},
		scopeAHostAuthority{},
		hook,
		scopeAOutcomeCalculator{},
		scopeAAllowSafetyAuthorizer{},
	)
	now := time.Now().UTC()
	created, err := facade.CreateGatheringDraft(
		scopeACommandContext("create-for-update"),
		scopeACreateCommand(now),
	)
	if err != nil {
		t.Fatalf("create draft: %v", err)
	}
	current, found, err := store.Load(context.Background(), created.GatheringID)
	if err != nil || !found {
		t.Fatalf("load draft: found=%v err=%v", found, err)
	}
	result, err := facade.UpdateGathering(
		scopeACommandContext("material-update"),
		app.UpdateGatheringCommand{
			GatheringID:               current.ID,
			ExpectedGatheringVersion:  current.Version,
			Purpose:                   withScopeATitle(current.Purpose, "新的活动主题"),
			Schedule:                  current.Schedule,
			Place:                     current.Place,
			PolicySet:                 current.PolicySet,
			HostBinding:               current.HostBinding,
			AcknowledgementDeadlineAt: now.Add(90 * time.Minute),
		},
	)
	if err != nil {
		t.Fatalf("material update: %v", err)
	}
	if hook.ackCalls != 1 || result.CurrentGatheringRevisionNumber != 2 ||
		store.outboxCount() != 2 {
		t.Fatalf(
			"material revision evidence mismatch: result=%+v ack=%d outbox=%d",
			result,
			hook.ackCalls,
			store.outboxCount(),
		)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestScopeALifecycleFacadeMapsCASAndIdempotencyConflicts(t *testing.T) {
	store := newScopeACommitStore()
	facade := app.NewLifecycleFacade(
		store,
		scopeATargetReader{},
		scopeAHostAuthority{},
		&scopeAParticipationHook{},
		scopeAOutcomeCalculator{},
		scopeAAllowSafetyAuthorizer{},
	)
	now := time.Now().UTC()
	created, err := facade.CreateGatheringDraft(
		scopeACommandContext("create-conflicts"),
		scopeACreateCommand(now),
	)
	if err != nil {
		t.Fatalf("create draft: %v", err)
	}
	if _, err := facade.PublishGathering(
		scopeACommandContext("stale-publish"),
		app.GatheringVersionCommand{
			GatheringID:              created.GatheringID,
			ExpectedGatheringVersion: created.AggregateVersion - 1,
		},
	); err == nil {
		t.Fatal("stale publish unexpectedly succeeded")
	}

	conflicting := scopeACreateCommand(now)
	conflicting.Purpose.Title = "不同请求"
	if _, err := facade.CreateGatheringDraft(
		scopeACommandContext("create-conflicts"),
		conflicting,
	); err == nil {
		t.Fatal("same idempotency key with different digest unexpectedly succeeded")
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-002
func TestScopeALifecycleFacadeCompletesOnlyWithCalculatorOutcome(t *testing.T) {
	store := newScopeACommitStore()
	calculator := &scopeACountingOutcomeCalculator{}
	facade := app.NewLifecycleFacade(
		store,
		scopeATargetReader{},
		scopeAHostAuthority{},
		&scopeAParticipationHook{},
		calculator,
		scopeAAllowSafetyAuthorizer{},
	)
	current := scopeAMustCreateModelDraft(t, time.Now().UTC().Add(-8*time.Hour))
	current.LifecycleStatus = contract.GatheringLifecycleStatusPublished
	current.RoomBindingStatus = contract.GatheringRoomBindingStatusReady
	current.ConversationID = "conversation-complete"
	store.values[current.ID] = current
	ctx := scopeACommandContext("complete-with-calculator")

	first, err := facade.CompleteGathering(ctx, app.GatheringVersionCommand{
		GatheringID:              current.ID,
		ExpectedGatheringVersion: current.Version,
	})
	if err != nil {
		t.Fatalf("complete ended Gathering: %v", err)
	}
	replayed, err := facade.CompleteGathering(ctx, app.GatheringVersionCommand{
		GatheringID:              current.ID,
		ExpectedGatheringVersion: current.Version,
	})
	if err != nil {
		t.Fatalf("replay complete Gathering: %v", err)
	}
	if first.OutcomeStatus != gatheringclient.GatheringOutcomeStatusOccurred ||
		!replayed.IdempotentReplay ||
		calculator.calls != 1 ||
		store.outboxCount() != 1 {
		t.Fatalf(
			"calculator completion invariant failed: first=%+v replay=%+v calls=%d outbox=%d",
			first,
			replayed,
			calculator.calls,
			store.outboxCount(),
		)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestScopeALifecycleFacadeCancelsUpcomingGatheringThroughCommand(t *testing.T) {
	store := newScopeACommitStore()
	facade := app.NewLifecycleFacade(
		store,
		scopeATargetReader{},
		scopeAHostAuthority{},
		&scopeAParticipationHook{},
		scopeAOutcomeCalculator{},
		scopeAAllowSafetyAuthorizer{},
	)
	current := scopeAMustCreateModelDraft(t, time.Now().UTC())
	store.values[current.ID] = current

	result, err := facade.CancelGathering(
		scopeACommandContext("cancel-upcoming"),
		app.GatheringReasonCommand{
			GatheringID:              current.ID,
			ExpectedGatheringVersion: current.Version,
			ReasonRef:                "reason/organizer-cancelled",
		},
	)
	if err != nil {
		t.Fatalf("cancel upcoming Gathering: %v", err)
	}
	stored, found, err := store.Load(context.Background(), current.ID)
	if err != nil || !found {
		t.Fatalf("load cancelled Gathering: found=%v err=%v", found, err)
	}
	if result.LifecycleStatus !=
		gatheringclient.GatheringLifecycleStatusCancelled ||
		stored.LifecycleStatus != contract.GatheringLifecycleStatusCancelled ||
		stored.CancelledAt.IsZero() || store.outboxCount() != 1 {
		t.Fatalf("cancel command did not persist canonical state: result=%+v stored=%+v outbox=%d", result, stored, store.outboxCount())
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-002
func TestScopeASafetyTerminationFailsClosedBeforeMutation(t *testing.T) {
	store := newScopeACommitStore()
	facade := app.NewLifecycleFacade(
		store,
		scopeATargetReader{},
		scopeAHostAuthority{},
		&scopeAParticipationHook{},
		scopeAOutcomeCalculator{},
		scopeADenySafetyAuthorizer{},
	)
	if _, err := facade.SafetyTerminateGathering(
		scopeACommandContext("deny-safety"),
		app.GatheringReasonCommand{
			GatheringID:              "gathering-protected",
			ExpectedGatheringVersion: 1,
			ReasonRef:                "reason/safety",
		},
	); err == nil {
		t.Fatal("safety termination without authority unexpectedly succeeded")
	}
	if store.receiptCount() != 0 || store.outboxCount() != 0 {
		t.Fatalf(
			"denied safety command mutated owner state: receipts=%d outbox=%d",
			store.receiptCount(),
			store.outboxCount(),
		)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
func TestScopeAOrdinaryHostCannotSafetyTerminateButCanEndEarly(t *testing.T) {
	store := newScopeACommitStore()
	authorizer := &scopeARecordingDenySafetyAuthorizer{}
	facade := app.NewLifecycleFacade(
		store,
		scopeATargetReader{},
		scopeAHostAuthority{},
		&scopeAParticipationHook{},
		scopeAOutcomeCalculator{},
		authorizer,
	)
	current := scopeAMustCreateModelDraft(t, time.Now().UTC().Add(-4*time.Hour))
	current.LifecycleStatus = contract.GatheringLifecycleStatusPublished
	store.values[current.ID] = current

	decisionRef := "content.report/report-host-denied@3#terminate_gathering"
	if _, err := facade.SafetyTerminateGathering(
		scopeACommandContext("ordinary-host-safety-denied"),
		app.GatheringReasonCommand{
			GatheringID:              current.ID,
			ExpectedGatheringVersion: current.Version,
			ReasonRef:                decisionRef,
			EvidenceRefs: []contract.CanonicalObjectRef{{
				ObjectTypeRef: "content.report",
				ObjectID:      "report-host-denied",
			}},
		},
	); err == nil ||
		!strings.Contains(err.Error(), "gathering_safety_termination_denied") {
		t.Fatalf("ordinary Host safety termination error=%v", err)
	}
	if authorizer.calls != 1 || store.receiptCount() != 0 || store.outboxCount() != 0 {
		t.Fatalf(
			"denied safety command crossed mutation boundary: calls=%d receipts=%d outbox=%d",
			authorizer.calls,
			store.receiptCount(),
			store.outboxCount(),
		)
	}

	result, err := facade.EndGatheringEarly(
		scopeACommandContext("ordinary-host-end-early"),
		app.GatheringReasonCommand{
			GatheringID:              current.ID,
			ExpectedGatheringVersion: current.Version,
			ReasonRef:                "host/ended-early",
		},
	)
	if err != nil {
		t.Fatalf("ordinary Host EndGatheringEarly: %v", err)
	}
	if result.OutcomeStatus != gatheringclient.GatheringOutcomeStatusEndedEarly ||
		authorizer.calls != 1 ||
		store.receiptCount() != 1 ||
		store.outboxCount() != 1 {
		t.Fatalf(
			"ordinary EndGatheringEarly was coupled to safety authority: result=%+v calls=%d receipts=%d outbox=%d",
			result,
			authorizer.calls,
			store.receiptCount(),
			store.outboxCount(),
		)
	}
}

type scopeAStoredReceipt struct {
	digest   string
	snapshot model.Gathering
}

type scopeACommitStore struct {
	mu       sync.Mutex
	values   map[string]model.Gathering
	receipts map[string]scopeAStoredReceipt
	outbox   []string
}

func newScopeACommitStore() *scopeACommitStore {
	return &scopeACommitStore{
		values:   make(map[string]model.Gathering),
		receipts: make(map[string]scopeAStoredReceipt),
	}
}

func (store *scopeACommitStore) Load(
	_ context.Context,
	gatheringID string,
) (model.Gathering, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	value, found := store.values[gatheringID]
	return value, found, nil
}

func (store *scopeACommitStore) Commit(
	_ context.Context,
	request ports.CommitRequest,
) (ports.CommitReceipt, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, found := store.receipts[request.ReceiptKey]; found {
		if receipt.digest != request.CommandDigest {
			return ports.CommitReceipt{}, gatheringerrors.ErrGatheringIdempotencyConflict
		}
		return ports.CommitReceipt{Gathering: receipt.snapshot, Replayed: true}, nil
	}
	current, found := store.values[request.GatheringID]
	var pointer *model.Gathering
	if found {
		copy := current
		pointer = &copy
	}
	next, err := request.Mutate(pointer)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if found && next.Version < current.Version {
		return ports.CommitReceipt{}, ports.ErrVersionConflict
	}
	changed := !found || next.Version != current.Version
	store.values[next.ID] = next
	store.receipts[request.ReceiptKey] = scopeAStoredReceipt{
		digest:   request.CommandDigest,
		snapshot: next,
	}
	if changed {
		store.outbox = append(store.outbox, request.EventType)
	}
	return ports.CommitReceipt{Gathering: next}, nil
}

func (store *scopeACommitStore) outboxCount() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return len(store.outbox)
}

func (store *scopeACommitStore) outboxEvents() []string {
	store.mu.Lock()
	defer store.mu.Unlock()
	return append([]string(nil), store.outbox...)
}

func (store *scopeACommitStore) receiptCount() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return len(store.receipts)
}

type scopeATargetReader struct{}

func (scopeATargetReader) RequireNavigable(
	context.Context,
	contract.GatheringSourceRef,
) error {
	return nil
}

type scopeAHostAuthority struct{}

func (scopeAHostAuthority) PrepareCreation(
	_ context.Context,
	command app.PrepareHostCommand,
) (app.HostPreparation, error) {
	return app.HostPreparation{
		HostBinding: command.HostBinding,
		OrganizerAssignments: []contract.OrganizerAssignment{{
			PersonaID:            "persona-owner",
			Role:                 contract.GatheringOrganizerRolePrimaryOrganizer,
			AuthorityEvidenceRef: command.HostBinding.AuthorityEvidenceRef,
			AuthorityVersion:     command.HostBinding.AuthorityVersion,
			AssignedAt:           time.Now().UTC(),
			Version:              1,
		}},
	}, nil
}

func (scopeAHostAuthority) RequirePublishAuthority(
	context.Context,
	string,
	int64,
) (model.AuditFact, error) {
	return model.AuditFact{}, nil
}

type scopeAParticipationHook struct {
	initializeCalls int
	ackCalls        int
}

func (hook *scopeAParticipationHook) InitializeCreatorParticipation(
	_ *model.Gathering,
	_ string,
	_ bool,
	_ time.Time,
) error {
	hook.initializeCalls++
	return nil
}

func (hook *scopeAParticipationHook) MarkActiveRevisionAcknowledgementsPending(
	_ *model.Gathering,
	_ contract.GatheringRevision,
	_ time.Time,
	_ time.Time,
) error {
	hook.ackCalls++
	return nil
}

type scopeAOutcomeCalculator struct{}

func (scopeAOutcomeCalculator) Calculate(
	_ model.Gathering,
	occurredAt time.Time,
) (contract.GatheringOutcome, error) {
	return contract.GatheringOutcome{
		Status:                   contract.GatheringOutcomeStatusOccurred,
		IndependentEvidenceCount: 2,
		EvidenceRefs: []contract.CanonicalObjectRef{{
			ObjectTypeRef: "GatheringAttendanceEvidence",
			ObjectID:      "evidence-1",
		}},
		CalculatedAt:      occurredAt.UTC(),
		CalculationDigest: "calculated-outcome",
	}, nil
}

type scopeACountingOutcomeCalculator struct {
	calls int
}

type scopeAAllowSafetyAuthorizer struct{}

func (scopeAAllowSafetyAuthorizer) AuthorizeSafetyTermination(
	_ context.Context,
	_ app.GatheringSafetyTerminationAuthorizationRequest,
) error {
	return nil
}

type scopeADenySafetyAuthorizer struct{}

func (scopeADenySafetyAuthorizer) AuthorizeSafetyTermination(
	_ context.Context,
	_ app.GatheringSafetyTerminationAuthorizationRequest,
) error {
	return gatheringerrors.ErrGatheringSafetyTerminationDenied
}

type scopeARecordingDenySafetyAuthorizer struct{ calls int }

func (authorizer *scopeARecordingDenySafetyAuthorizer) AuthorizeSafetyTermination(
	_ context.Context,
	request app.GatheringSafetyTerminationAuthorizationRequest,
) error {
	authorizer.calls++
	if request.ActorPersonaID != "persona-owner" ||
		request.Action != app.GatheringSafetyTerminationAction ||
		request.EvidenceRef != "content.report/report-host-denied" ||
		request.DecisionRef !=
			"content.report/report-host-denied@3#terminate_gathering" {
		return gatheringerrors.ErrGatheringSafetyAuthorityUnavailable
	}
	return gatheringerrors.ErrGatheringSafetyTerminationDenied
}

func (calculator *scopeACountingOutcomeCalculator) Calculate(
	current model.Gathering,
	occurredAt time.Time,
) (contract.GatheringOutcome, error) {
	calculator.calls++
	return scopeAOutcomeCalculator{}.Calculate(current, occurredAt)
}

func scopeACommandContext(idempotencyKey string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "GatheringScopeALocalContract",
		RequestID:      "request-" + idempotencyKey,
		TraceID:        "trace-" + idempotencyKey,
		IdempotencyKey: idempotencyKey,
		Actor: operation.ActorContext{
			PersonaID: "persona-owner",
		},
	})
}

func scopeACreateCommand(now time.Time) app.CreateGatheringDraftCommand {
	return app.CreateGatheringDraftCommand{
		HostBinding: contract.HostBinding{
			HostSubjectKind:      contract.GatheringHostSubjectKindPersona,
			HostSubjectID:        "persona-owner",
			AuthorityEvidenceRef: "authority/owner",
			AuthorityVersion:     1,
			AuthorityExpiresAt:   now.Add(24 * time.Hour),
		},
		Purpose: contract.GatheringPurpose{
			Title:      "周末徒步",
			Summary:    "一起完成近郊徒步",
			CostNotice: contract.GatheringCostNoticeFree,
		},
		Schedule: contract.GatheringSchedule{
			Timezone:          "Asia/Shanghai",
			StartAt:           now.Add(3 * time.Hour),
			EndAt:             now.Add(5 * time.Hour),
			AdmissionClosesAt: now.Add(2 * time.Hour),
		},
		Place: contract.GatheringPlace{
			Mode:              contract.GatheringPlaceModePhysical,
			CoarsePlaceLabel:  "杭州",
			ExactMeetingPoint: "地铁站 A 口",
		},
		PolicySet: contract.GatheringPolicySet{
			AudiencePolicy:  contract.GatheringAudiencePolicyPublic,
			AdmissionPolicy: contract.GatheringAdmissionPolicyOpen,
			CapacityPolicy: contract.GatheringCapacityPolicy{
				MaxParticipants: 12,
			},
			DisclosurePolicy: contract.GatheringDisclosurePolicy{
				TimeDisclosure:   contract.GatheringTimeDisclosureExact,
				PlaceDisclosure:  contract.GatheringPlaceDisclosureExact,
				RosterDisclosure: contract.GatheringRosterDisclosureCountOnly,
			},
			RiskControlPolicyRef: "risk/default",
			PolicyDecisionRef:    "decision/allow",
			PolicyDigest:         "sha256:ca7acf0a841461bfd3e8d38fa0a80f7c7131dcc59c95d225f5c0987bfad35973",
			ObligationDigest:     "obligation-digest",
		},
	}
}

func withScopeATitle(
	purpose contract.GatheringPurpose,
	title string,
) contract.GatheringPurpose {
	purpose.Title = title
	return purpose
}

var _ ports.AggregateStore = (*scopeACommitStore)(nil)
