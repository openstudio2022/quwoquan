// readiness_case: withdraw-gathering-application-local
package application_test

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strconv"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	runtimeerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
	persistence "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/persistence"
)

const (
	withdrawGatheringCollection = "gatherings"
	withdrawReceiptCollection   = "gathering_command_receipts"
	withdrawOutboxCollection    = "gathering_outbox"
	withdrawSequenceCollection  = "gathering_outbox_sequences"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-014
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-014.t1
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-014.t2
func TestWithdrawGatheringApplicationCommitsOnlyTheApplicantsPendingParticipation(t *testing.T) {
	runtime := startWithdrawRealMongo(t)
	store := persistence.NewMongoAggregateStore(runtime.Database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure canonical Gathering indexes: %v", err)
	}

	now := time.Now().UTC().Truncate(time.Millisecond)
	initial := canonicalWithdrawGathering(now)
	seedWithdrawGathering(t, store, initial, now)
	facade := app.NewCommandFacade(store)

	apply, err := facade.ApplyToGathering(
		withdrawOperationContext("ApplyToGathering", "persona-applicant", "apply"),
		app.ApplyToGatheringCommand{
			GatheringParticipationVersionCommand: app.GatheringParticipationVersionCommand{
				GatheringID:                  initial.ID,
				ExpectedGatheringVersion:     initial.Version,
				ExpectedParticipationVersion: 0,
			},
			Answers: []model.GatheringApplicationAnswer{{
				QuestionID: "attendance-intent",
				AnswerText: "I will attend the canonical Gathering",
			}},
		},
	)
	if err != nil {
		t.Fatalf("apply through production GatheringCommandFacet: %v", err)
	}
	if apply.IdempotentReplay ||
		apply.ParticipationState != gatheringclient.GatheringParticipationStateApplicationPending ||
		apply.ParticipationVersion != 1 {
		t.Fatalf("application result is not canonical: %+v", apply)
	}

	beforeWithdraw := loadWithdrawGathering(t, store, initial.ID)
	beforeTarget := findWithdrawParticipation(t, beforeWithdraw, "persona-applicant")
	beforeOther := findWithdrawParticipation(t, beforeWithdraw, "persona-existing")
	if beforeTarget.AdmissionSource != contract.GatheringAdmissionSourceApplication ||
		beforeTarget.State != contract.GatheringParticipationStateApplicationPending ||
		len(beforeTarget.ApplicationAnswers) != 1 ||
		beforeTarget.ReviewExpectedBy.IsZero() {
		t.Fatalf("application setup did not persist canonical pending state: %+v", beforeTarget)
	}

	assertWithdrawFailureIsAtomic(
		t,
		facade,
		store,
		runtime.Database,
		withdrawOperationContext("WithdrawGatheringApplication", "persona-intruder", "unauthorized"),
		app.GatheringParticipationVersionCommand{
			GatheringID:                  initial.ID,
			ExpectedGatheringVersion:     beforeWithdraw.Version,
			ExpectedParticipationVersion: beforeTarget.Version,
		},
		gatheringerrors.ErrGatheringParticipationConflict.Error(),
	)
	invalidSource := findWithdrawParticipation(t, beforeWithdraw, "persona-invalid-source")
	assertWithdrawFailureIsAtomic(
		t,
		facade,
		store,
		runtime.Database,
		withdrawOperationContext("WithdrawGatheringApplication", "persona-invalid-source", "invalid-source"),
		app.GatheringParticipationVersionCommand{
			GatheringID:                  initial.ID,
			ExpectedGatheringVersion:     beforeWithdraw.Version,
			ExpectedParticipationVersion: invalidSource.Version,
		},
		gatheringerrors.ErrGatheringTransitionForbidden.Error(),
	)
	assertWithdrawFailureIsAtomic(
		t,
		facade,
		store,
		runtime.Database,
		withdrawOperationContext("WithdrawGatheringApplication", "persona-applicant", "stale-root"),
		app.GatheringParticipationVersionCommand{
			GatheringID:                  initial.ID,
			ExpectedGatheringVersion:     beforeWithdraw.Version - 1,
			ExpectedParticipationVersion: beforeTarget.Version,
		},
		gatheringerrors.ErrGatheringVersionConflict.Error(),
	)
	assertWithdrawFailureIsAtomic(
		t,
		facade,
		store,
		runtime.Database,
		withdrawOperationContext("WithdrawGatheringApplication", "persona-applicant", "stale-participation"),
		app.GatheringParticipationVersionCommand{
			GatheringID:                  initial.ID,
			ExpectedGatheringVersion:     beforeWithdraw.Version,
			ExpectedParticipationVersion: beforeTarget.Version + 1,
		},
		gatheringerrors.ErrGatheringParticipationConflict.Error(),
	)

	withdrawCommand := app.GatheringParticipationVersionCommand{
		GatheringID:                  initial.ID,
		ExpectedGatheringVersion:     beforeWithdraw.Version,
		ExpectedParticipationVersion: beforeTarget.Version,
	}
	withdrawContext := withdrawOperationContext(
		"WithdrawGatheringApplication",
		"persona-applicant",
		"success",
	)
	first, err := facade.WithdrawGatheringApplication(withdrawContext, withdrawCommand)
	if err != nil {
		t.Fatalf("withdraw through production GatheringCommandFacet: %v", err)
	}
	if first.IdempotentReplay ||
		first.ParticipationState != gatheringclient.GatheringParticipationStateClosed ||
		first.ParticipationVersion != beforeTarget.Version+1 ||
		first.AggregateVersion != beforeWithdraw.Version+1 {
		t.Fatalf("withdraw result is not canonical: %+v", first)
	}

	afterWithdraw := loadWithdrawGathering(t, store, initial.ID)
	afterTarget := findWithdrawParticipation(t, afterWithdraw, "persona-applicant")
	afterOther := findWithdrawParticipation(t, afterWithdraw, "persona-existing")
	if afterTarget.State != contract.GatheringParticipationStateClosed ||
		afterTarget.ClosedReason != contract.GatheringParticipationClosedReasonWithdrawn ||
		afterTarget.ClosedByPersonaID != "persona-applicant" ||
		afterTarget.ClosedAt.IsZero() ||
		!afterTarget.ReviewExpectedBy.IsZero() ||
		afterTarget.Version != beforeTarget.Version+1 ||
		afterTarget.AttemptNo != beforeTarget.AttemptNo ||
		afterTarget.AdmissionSource != beforeTarget.AdmissionSource ||
		!reflect.DeepEqual(afterTarget.ApplicationAnswers, beforeTarget.ApplicationAnswers) {
		t.Fatalf("withdraw changed the wrong application fields: before=%+v after=%+v", beforeTarget, afterTarget)
	}
	if !reflect.DeepEqual(beforeOther, afterOther) {
		t.Fatalf("withdraw changed another Participation: before=%+v after=%+v", beforeOther, afterOther)
	}
	if beforeWithdraw.ConversationID != afterWithdraw.ConversationID ||
		beforeWithdraw.RoomBindingStatus != afterWithdraw.RoomBindingStatus ||
		!reflect.DeepEqual(beforeWithdraw.AdmissionControl, afterWithdraw.AdmissionControl) {
		t.Fatalf("withdraw changed room or admission state: before=%+v after=%+v", beforeWithdraw, afterWithdraw)
	}
	if !reflect.DeepEqual(
		withdrawUnrelatedState(beforeWithdraw, "persona-applicant"),
		withdrawUnrelatedState(afterWithdraw, "persona-applicant"),
	) {
		t.Fatalf("withdraw changed aggregate state outside the target application")
	}

	assertWithdrawPersistence(t, runtime.Database, afterWithdraw, afterTarget)
	countsAfterFirst := readWithdrawStoreCounts(t, runtime.Database)
	if countsAfterFirst != (withdrawStoreCounts{
		gatherings: 1,
		receipts:   3,
		outbox:     3,
		sequences:  1,
	}) {
		t.Fatalf("canonical commit counts after withdraw = %+v", countsAfterFirst)
	}

	replayed, err := facade.WithdrawGatheringApplication(withdrawContext, withdrawCommand)
	if err != nil {
		t.Fatalf("replay withdraw through production GatheringCommandFacet: %v", err)
	}
	if !replayed.IdempotentReplay ||
		replayed.AggregateVersion != first.AggregateVersion ||
		replayed.ParticipationVersion != first.ParticipationVersion ||
		replayed.ParticipationState != first.ParticipationState {
		t.Fatalf("withdraw replay drifted: first=%+v replay=%+v", first, replayed)
	}
	assertWithdrawStateAndCountsUnchanged(
		t,
		store,
		runtime.Database,
		afterWithdraw,
		countsAfterFirst,
	)

	conflictingCommand := withdrawCommand
	conflictingCommand.ExpectedGatheringVersion++
	assertWithdrawFailureIsAtomic(
		t,
		facade,
		store,
		runtime.Database,
		withdrawContext,
		conflictingCommand,
		gatheringerrors.ErrGatheringIdempotencyConflict.Error(),
	)
	assertWithdrawFailureIsAtomic(
		t,
		facade,
		store,
		runtime.Database,
		withdrawOperationContext("WithdrawGatheringApplication", "persona-applicant", "terminal"),
		app.GatheringParticipationVersionCommand{
			GatheringID:                  initial.ID,
			ExpectedGatheringVersion:     afterWithdraw.Version,
			ExpectedParticipationVersion: afterTarget.Version,
		},
		gatheringerrors.ErrGatheringTransitionForbidden.Error(),
	)

	for _, lifecycle := range []struct {
		name   string
		status contract.GatheringLifecycleStatus
	}{
		{name: "draft", status: contract.GatheringLifecycleStatusDraft},
		{name: "completed", status: contract.GatheringLifecycleStatusCompleted},
	} {
		t.Run("reject_"+lifecycle.name+"_root", func(t *testing.T) {
			blocked := canonicalLifecycleBlockedWithdrawGathering(
				now,
				"gathering-withdraw-"+lifecycle.name,
				lifecycle.status,
			)
			seedWithdrawGathering(t, store, blocked, now)
			blockedTarget := findWithdrawParticipation(t, blocked, "persona-blocked-root")
			assertWithdrawFailureIsAtomic(
				t,
				facade,
				store,
				runtime.Database,
				withdrawOperationContext(
					"WithdrawGatheringApplication",
					"persona-blocked-root",
					lifecycle.name+"-root",
				),
				app.GatheringParticipationVersionCommand{
					GatheringID:                  blocked.ID,
					ExpectedGatheringVersion:     blocked.Version,
					ExpectedParticipationVersion: blockedTarget.Version,
				},
				gatheringerrors.ErrGatheringTransitionForbidden.Error(),
			)
		})
	}
}

func startWithdrawRealMongo(t *testing.T) *testinfra.RealMongo {
	t.Helper()
	startupContext, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(
		startupContext,
		"circle_gathering_withdraw_local_contract",
	)
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		shutdownContext, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer shutdownCancel()
		if err := runtime.Close(shutdownContext); err != nil {
			t.Errorf("close real MongoDB: %v", err)
		}
	})
	return runtime
}

func seedWithdrawGathering(
	t *testing.T,
	store *persistence.MongoAggregateStore,
	value model.Gathering,
	now time.Time,
) {
	t.Helper()
	receipt, err := store.Commit(context.Background(), ports.CommitRequest{
		GatheringID:      value.ID,
		ReceiptKey:       "persona-owner:seed-" + value.ID,
		CommandDigest:    "seed-" + value.ID + "-v1",
		ReceiptExpiresAt: now.Add(7 * 24 * time.Hour),
		EventType:        gatheringevent.GatheringDraftCreated,
		Mutate: func(current *model.Gathering) (model.Gathering, error) {
			if current != nil {
				return model.Gathering{}, model.ErrInvalidLifecycleArgument
			}
			return value, nil
		},
	})
	if err != nil {
		t.Fatalf("seed Gathering through canonical aggregate commit: %v", err)
	}
	if receipt.Replayed || receipt.Gathering.ID != value.ID || receipt.Gathering.Version != 1 {
		t.Fatalf("seed receipt is not canonical: %+v", receipt)
	}
}

func canonicalWithdrawGathering(now time.Time) model.Gathering {
	return model.Gathering{
		ID:                 "gathering-withdraw-local-contract",
		Version:            1,
		CreatedByPersonaID: "persona-owner",
		HostBinding: contract.HostBinding{
			HostSubjectKind:      contract.GatheringHostSubjectKindPersona,
			HostSubjectID:        "persona-owner",
			AuthorityEvidenceRef: "authority/withdraw-local",
			AuthorityVersion:     1,
			AuthorityExpiresAt:   now.Add(24 * time.Hour),
		},
		OrganizerAssignments: []contract.OrganizerAssignment{{
			PersonaID:            "persona-owner",
			Role:                 contract.GatheringOrganizerRolePrimaryOrganizer,
			AuthorityEvidenceRef: "authority/withdraw-local",
			AuthorityVersion:     1,
			AssignedAt:           now.Add(-time.Hour),
			Version:              1,
		}},
		Purpose: contract.GatheringPurpose{
			Title:            "Canonical withdraw contract",
			Summary:          "The pending application may be withdrawn only by its applicant.",
			TopicRefs:        []string{},
			RequirementRefs:  []string{},
			SourceObjectRefs: []contract.GatheringSourceRef{},
			CostNotice:       contract.GatheringCostNoticeFree,
		},
		Schedule: contract.GatheringSchedule{
			Timezone:          "Asia/Shanghai",
			StartAt:           now.Add(4 * time.Hour),
			EndAt:             now.Add(6 * time.Hour),
			AdmissionClosesAt: now.Add(3 * time.Hour),
		},
		PolicySet: contract.GatheringPolicySet{
			AudiencePolicy:  contract.GatheringAudiencePolicyPublic,
			AdmissionPolicy: contract.GatheringAdmissionPolicyApproval,
			CapacityPolicy: contract.GatheringCapacityPolicy{
				MaxParticipants: 3,
			},
			ApplicationQuestions: []contract.GatheringApplicationQuestion{{
				QuestionID: "attendance-intent",
				Prompt:     "Why will you attend?",
				Kind:       contract.GatheringApplicationQuestionKindText,
				Options:    []contract.GatheringApplicationQuestionOption{},
				Required:   true,
			}},
		},
		AdmissionControl: contract.GatheringAdmissionControl{
			Status:  contract.GatheringAdmissionControlStatusOpen,
			Version: 1,
		},
		LifecycleStatus:   contract.GatheringLifecycleStatusPublished,
		ConversationID:    "conversation-withdraw-local-contract",
		RoomBindingStatus: contract.GatheringRoomBindingStatusReady,
		Participations: []model.GatheringParticipation{{
			GatheringID:        "gathering-withdraw-local-contract",
			PersonaID:          "persona-existing",
			State:              contract.GatheringParticipationStateActive,
			AdmissionSource:    contract.GatheringAdmissionSourceOpen,
			AttemptNo:          1,
			JoinedAt:           now.Add(-30 * time.Minute),
			Version:            3,
			ApplicationAnswers: []model.GatheringApplicationAnswer{},
			Attendance: contract.GatheringAttendance{
				Status:       contract.GatheringAttendanceStatusNotDeclared,
				EvidenceRefs: []contract.CanonicalObjectRef{},
			},
			CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{
				Status: contract.GatheringRevisionAcknowledgementStatusNotRequired,
			},
		}, {
			GatheringID:        "gathering-withdraw-local-contract",
			PersonaID:          "persona-invalid-source",
			State:              contract.GatheringParticipationStateApplicationPending,
			AdmissionSource:    contract.GatheringAdmissionSourceInvitation,
			AttemptNo:          1,
			Version:            4,
			ApplicationAnswers: []model.GatheringApplicationAnswer{},
			ReviewExpectedBy:   now.Add(2 * time.Hour),
			Attendance: contract.GatheringAttendance{
				Status:       contract.GatheringAttendanceStatusNotDeclared,
				EvidenceRefs: []contract.CanonicalObjectRef{},
			},
			CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{
				Status: contract.GatheringRevisionAcknowledgementStatusNotRequired,
			},
		}},
		Revisions: []contract.GatheringRevision{},
		AvailabilityWatches: []contract.GatheringAvailabilityWatch{{
			GatheringID: "gathering-withdraw-local-contract",
			PersonaID:   "persona-watcher",
			Status:      contract.GatheringAvailabilityWatchStatusActive,
			Version:     1,
			CreatedAt:   now.Add(-45 * time.Minute),
			UpdatedAt:   now.Add(-45 * time.Minute),
		}},
		CreatedAt: now.Add(-time.Hour),
		UpdatedAt: now.Add(-time.Hour),
	}
}

func canonicalLifecycleBlockedWithdrawGathering(
	now time.Time,
	gatheringID string,
	status contract.GatheringLifecycleStatus,
) model.Gathering {
	value := canonicalWithdrawGathering(now)
	value.ID = gatheringID
	value.ConversationID = "conversation-" + gatheringID
	value.LifecycleStatus = status
	value.Participations = []model.GatheringParticipation{{
		GatheringID:     gatheringID,
		PersonaID:       "persona-blocked-root",
		State:           contract.GatheringParticipationStateApplicationPending,
		AdmissionSource: contract.GatheringAdmissionSourceApplication,
		AttemptNo:       1,
		Version:         1,
		ApplicationAnswers: []model.GatheringApplicationAnswer{{
			QuestionID: "attendance-intent",
			AnswerText: "The root lifecycle must still gate this application",
		}},
		ReviewExpectedBy: now.Add(2 * time.Hour),
		Attendance: contract.GatheringAttendance{
			Status:       contract.GatheringAttendanceStatusNotDeclared,
			EvidenceRefs: []contract.CanonicalObjectRef{},
		},
		CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{
			Status: contract.GatheringRevisionAcknowledgementStatusNotRequired,
		},
	}}
	value.AvailabilityWatches = []contract.GatheringAvailabilityWatch{}
	if status == contract.GatheringLifecycleStatusDraft {
		value.ConversationID = ""
		value.RoomBindingStatus = contract.GatheringRoomBindingStatusPending
	}
	if status == contract.GatheringLifecycleStatusCompleted {
		value.CompletedAt = now.Add(-time.Minute)
	}
	return value
}

func withdrawOperationContext(operationID, personaID, key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "circle.gathering." + operationID,
		RequestID:      "request-withdraw-" + key,
		TraceID:        "trace-withdraw-" + key,
		IdempotencyKey: "withdraw-" + key,
		Actor: operation.ActorContext{
			AccountID: "account-" + personaID,
			PersonaID: personaID,
		},
	})
}

func assertWithdrawFailureIsAtomic(
	t *testing.T,
	facade *app.CommandFacade,
	store *persistence.MongoAggregateStore,
	database *mongo.Database,
	ctx context.Context,
	command app.GatheringParticipationVersionCommand,
	wantCode string,
) {
	t.Helper()
	before := loadWithdrawGathering(t, store, command.GatheringID)
	counts := readWithdrawStoreCounts(t, database)
	if _, err := facade.WithdrawGatheringApplication(ctx, command); err == nil {
		t.Fatalf("WithdrawGatheringApplication unexpectedly succeeded; want %s", wantCode)
	} else {
		assertWithdrawErrorCode(t, err, wantCode)
	}
	assertWithdrawStateAndCountsUnchanged(t, store, database, before, counts)
}

func assertWithdrawErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appError *runtimeerrors.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("withdraw error is not canonical AppError: %T %v", err, err)
	}
	if got := appError.Code.String(); got != wantCode {
		t.Fatalf("withdraw error code = %q, want %q", got, wantCode)
	}
}

func assertWithdrawStateAndCountsUnchanged(
	t *testing.T,
	store *persistence.MongoAggregateStore,
	database *mongo.Database,
	want model.Gathering,
	wantCounts withdrawStoreCounts,
) {
	t.Helper()
	got := loadWithdrawGathering(t, store, want.ID)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("failed or replayed withdraw changed aggregate: before=%+v after=%+v", want, got)
	}
	if gotCounts := readWithdrawStoreCounts(t, database); gotCounts != wantCounts {
		t.Fatalf("failed or replayed withdraw changed store counts: before=%+v after=%+v", wantCounts, gotCounts)
	}
}

func assertWithdrawPersistence(
	t *testing.T,
	database *mongo.Database,
	gathering model.Gathering,
	participation model.GatheringParticipation,
) {
	t.Helper()
	var receipt struct {
		CommandDigest     string          `bson:"commandDigest"`
		AggregateVersion  int64           `bson:"aggregateVersion"`
		AggregateSnapshot model.Gathering `bson:"aggregateSnapshot"`
	}
	if err := database.Collection(withdrawReceiptCollection).FindOne(
		context.Background(),
		bson.M{"_id": "persona-applicant:withdraw-success"},
	).Decode(&receipt); err != nil {
		t.Fatalf("read durable withdraw receipt: %v", err)
	}
	receiptTarget := findWithdrawParticipation(t, receipt.AggregateSnapshot, participation.PersonaID)
	if receipt.CommandDigest == "" ||
		receipt.AggregateVersion != gathering.Version ||
		!reflect.DeepEqual(receiptTarget, participation) {
		t.Fatalf("durable withdraw receipt drifted: %+v", receipt)
	}

	eventID := gathering.ID + ":" + gatheringevent.GatheringParticipationChanged + ":" +
		strconv.FormatInt(gathering.Version, 10)
	var event struct {
		EventType        string `bson:"eventType"`
		AggregateID      string `bson:"aggregateId"`
		AggregateVersion int64  `bson:"aggregateVersion"`
		PayloadJSON      string `bson:"payloadJson"`
	}
	if err := database.Collection(withdrawOutboxCollection).FindOne(
		context.Background(),
		bson.M{"_id": eventID},
	).Decode(&event); err != nil {
		t.Fatalf("read durable withdraw outbox event: %v", err)
	}
	var payload struct {
		GatheringID          string `json:"gatheringId"`
		ActorPersonaID       string `json:"actorPersonaId"`
		ParticipantPersonaID string `json:"participantPersonaId"`
		ParticipationState   string `json:"participationState"`
		AggregateVersion     int64  `json:"aggregateVersion"`
	}
	if err := json.Unmarshal([]byte(event.PayloadJSON), &payload); err != nil {
		t.Fatalf("decode withdraw outbox payload: %v", err)
	}
	if event.EventType != gatheringevent.GatheringParticipationChanged ||
		event.AggregateID != gathering.ID ||
		event.AggregateVersion != gathering.Version ||
		payload.GatheringID != gathering.ID ||
		payload.ActorPersonaID != participation.PersonaID ||
		payload.ParticipantPersonaID != participation.PersonaID ||
		payload.ParticipationState != string(contract.GatheringParticipationStateClosed) ||
		payload.AggregateVersion != gathering.Version {
		t.Fatalf("withdraw outbox payload drifted: event=%+v payload=%+v", event, payload)
	}
}

type withdrawStoreCounts struct {
	gatherings int64
	receipts   int64
	outbox     int64
	sequences  int64
}

func readWithdrawStoreCounts(t *testing.T, database *mongo.Database) withdrawStoreCounts {
	t.Helper()
	return withdrawStoreCounts{
		gatherings: countWithdrawDocuments(t, database, withdrawGatheringCollection),
		receipts:   countWithdrawDocuments(t, database, withdrawReceiptCollection),
		outbox:     countWithdrawDocuments(t, database, withdrawOutboxCollection),
		sequences:  countWithdrawDocuments(t, database, withdrawSequenceCollection),
	}
}

func countWithdrawDocuments(t *testing.T, database *mongo.Database, collection string) int64 {
	t.Helper()
	count, err := database.Collection(collection).CountDocuments(context.Background(), bson.M{})
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	return count
}

func loadWithdrawGathering(
	t *testing.T,
	store *persistence.MongoAggregateStore,
	gatheringID string,
) model.Gathering {
	t.Helper()
	value, found, err := store.Load(context.Background(), gatheringID)
	if err != nil || !found {
		t.Fatalf("load Gathering %s: found=%v err=%v", gatheringID, found, err)
	}
	return value
}

func findWithdrawParticipation(
	t *testing.T,
	gathering model.Gathering,
	personaID string,
) model.GatheringParticipation {
	t.Helper()
	participation, found := model.FindParticipation(gathering, personaID)
	if !found {
		t.Fatalf("Participation %s is missing from %+v", personaID, gathering.Participations)
	}
	return participation
}

func withdrawUnrelatedState(
	gathering model.Gathering,
	targetPersonaID string,
) model.Gathering {
	gathering.Version = 0
	gathering.UpdatedAt = time.Time{}
	participations := make([]model.GatheringParticipation, 0, len(gathering.Participations))
	for _, participation := range gathering.Participations {
		if participation.PersonaID != targetPersonaID {
			participations = append(participations, participation)
		}
	}
	gathering.Participations = participations
	return gathering
}
