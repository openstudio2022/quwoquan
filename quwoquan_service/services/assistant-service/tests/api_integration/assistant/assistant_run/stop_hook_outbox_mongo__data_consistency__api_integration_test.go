// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
)

type mongoStopHookCapture struct {
	inputs []runruntime.HookInput
}

func (*mongoStopHookCapture) Name() string { return "test.mongo_stop_hook" }

func (*mongoStopHookCapture) Phases() []runruntime.HookPhase {
	return []runruntime.HookPhase{runruntime.HookOnStop}
}

func (hook *mongoStopHookCapture) Invoke(
	_ context.Context,
	input runruntime.HookInput,
) (runruntime.HookResult, error) {
	hook.inputs = append(hook.inputs, input)
	return runruntime.HookResult{
		Decision:             runruntime.HookAllow,
		ProtectedFactsDigest: input.ProtectedFactsDigest,
	}, nil
}

func TestMongoStopHookIntentIsAtomicForEveryStopOutcomeAndSurvivesRestart(t *testing.T) {
	database := requirePublicWebMongo(t)
	resetAssistantRunControlState(t)
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	outcomes := []generated.AssistantRunState{
		generated.AssistantRunStateCompleted,
		generated.AssistantRunStateFailed,
		generated.AssistantRunStateCancelled,
		generated.AssistantRunStatePaused,
		generated.AssistantRunStateWaitingUser,
		generated.AssistantRunStateWaitingApproval,
		generated.AssistantRunStateWaitingExternal,
	}
	invocationIDs := map[string]struct{}{}
	latest := time.Date(2026, 8, 8, 11, 0, 0, 0, time.UTC)
	for index, outcome := range outcomes {
		clock := latest.Add(time.Duration(index) * time.Hour)
		commands := newAssistantRunControlService(repository, &clock)
		run, err := commands.Start(t.Context(), runruntime.StartCommand{
			UserID:          "hook-owner",
			PersonaID:       "hook-owner:persona",
			SessionID:       "hook-session-" + outcome.WireName(),
			ClientRequestID: "hook-start-" + outcome.WireName(),
			InputText:       "验证停止钩子 " + outcome.WireName(),
		})
		if err != nil {
			t.Fatalf("start %s Run: %v", outcome, err)
		}
		stopped, event, receipt := mongoStopHookMutation(t, run, outcome, clock.Add(time.Minute))
		if err := repository.Commit(
			t.Context(), run.Revision, stopped,
			[]runruntime.JournalEvent{event}, &receipt,
		); err != nil {
			t.Fatalf("commit %s Run: %v", outcome, err)
		}
		invocationID := runruntime.StableHookInvocationID(
			run.RunID, runruntime.HookOnStop, stopped.Revision,
		)
		invocationIDs[invocationID] = struct{}{}
		assertMongoStopHookCommitFacts(t, database, repository, stopped, event, receipt)
		latest = stopped.UpdatedAt
	}

	// No relay existed while the transactions committed. Constructing it only
	// now models process death immediately after the terminal/stop commit.
	hook := &mongoStopHookCapture{}
	registry, err := runruntime.NewHookRegistry(
		runruntime.RegisteredHook{Hook: hook},
	)
	if err != nil {
		t.Fatal(err)
	}
	relay := runruntime.NewStopHookRelay(
		repository,
		registry,
		"mongo-stop-hook-restart",
		time.Second,
		16,
		runruntime.WithStopHookRelayClock(func() time.Time {
			return latest.Add(time.Hour)
		}),
	)
	if processed, err := relay.FlushOnce(t.Context()); err != nil || processed != len(outcomes) {
		t.Fatalf("restart relay processed=%d want=%d err=%v", processed, len(outcomes), err)
	}
	if len(hook.inputs) != len(outcomes) {
		t.Fatalf("HookOnStop count=%d want=%d", len(hook.inputs), len(outcomes))
	}
	for _, input := range hook.inputs {
		if _, ok := invocationIDs[input.InvocationID]; !ok ||
			input.Phase != runruntime.HookOnStop || input.RunRevision <= 0 ||
			input.Run.Revision != input.RunRevision ||
			input.Run.State.WireName() != input.Outcome {
			t.Fatalf("unstable durable HookInput=%+v", input)
		}
	}
	processedCount, err := database.Collection("assistant_run_hook_outbox").CountDocuments(
		t.Context(), bson.M{"processedAt": bson.M{"$exists": true}},
	)
	if err != nil || processedCount != int64(len(outcomes)) {
		t.Fatalf("processed hook receipts=%d want=%d err=%v", processedCount, len(outcomes), err)
	}
}

func TestMongoStopHookDuplicateIntentRollsBackRunJournalReceiptTerminalAndQueue(t *testing.T) {
	database := requirePublicWebMongo(t)
	resetAssistantRunControlState(t)
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	clock := time.Date(2026, 8, 8, 13, 0, 0, 0, time.UTC)
	run, err := newAssistantRunControlService(repository, &clock).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "hook-rollback-owner",
			SessionID:       "hook-rollback-session",
			ClientRequestID: "hook-rollback-start",
			InputText:       "验证停止任务事务回滚",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	stopped, event, receipt := mongoStopHookMutation(
		t, run, generated.AssistantRunStateFailed, clock.Add(time.Minute),
	)
	invocationID := runruntime.StableHookInvocationID(
		run.RunID, runruntime.HookOnStop, stopped.Revision,
	)
	if _, err := database.Collection("assistant_run_hook_outbox").InsertOne(
		t.Context(),
		bson.M{
			"_id": invocationID, "runId": run.RunID, "phase": "on_stop",
			"outcome": "failed", "runRevision": stopped.Revision,
			"protectedFactsDigest": runruntime.ProtectedRunFactsDigest(stopped),
			"data":                 bson.M{"outcome": "failed"}, "createdAt": stopped.UpdatedAt,
		},
	); err != nil {
		t.Fatalf("inject duplicate stop intent: %v", err)
	}
	if err := repository.Commit(
		t.Context(), run.Revision, stopped,
		[]runruntime.JournalEvent{event}, &receipt,
	); !errors.Is(err, runruntime.ErrRevisionConflict) {
		t.Fatalf("duplicate stop intent commit error=%v want revision conflict", err)
	}
	current, err := repository.Load(t.Context(), run.RunID)
	if err != nil || current.Revision != run.Revision || current.State != run.State {
		t.Fatalf("Run escaped rolled-back transaction: current=%+v baseline=%+v err=%v", current, run, err)
	}
	assertMongoCount(t, database, "assistant_run_events", bson.M{"_id": event.EventID}, 0)
	assertMongoCount(t, database, "assistant_run_command_receipts", bson.M{"commandId": receipt.CommandID}, 0)
	assertMongoCount(t, database, "assistant_run_terminal_outbox", bson.M{"runId": run.RunID}, 0)
	assertMongoCount(t, database, "assistant_run_work_queue", bson.M{"_id": run.RunID}, 1)
	assertMongoCount(t, database, "assistant_run_hook_outbox", bson.M{"_id": invocationID}, 1)
}

func TestMongoStopHookClaimRetryOwnerFenceAndAckReplay(t *testing.T) {
	database := requirePublicWebMongo(t)
	resetAssistantRunControlState(t)
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	clock := time.Date(2026, 8, 8, 14, 0, 0, 0, time.UTC)
	run, err := newAssistantRunControlService(repository, &clock).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "hook-claim-owner",
			SessionID:       "hook-claim-session",
			ClientRequestID: "hook-claim-start",
			InputText:       "验证停止任务接管",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	stopped, event, receipt := mongoStopHookMutation(
		t, run, generated.AssistantRunStatePaused, clock.Add(time.Minute),
	)
	if err := repository.Commit(
		t.Context(), run.Revision, stopped,
		[]runruntime.JournalEvent{event}, &receipt,
	); err != nil {
		t.Fatal(err)
	}
	claimAt := stopped.UpdatedAt.Add(time.Hour)
	claimed, err := repository.ClaimPendingStopHooks(
		t.Context(), "hook-owner-a", claimAt, time.Minute, 1,
	)
	if err != nil || len(claimed) != 1 || claimed[0].AttemptCount != 1 {
		t.Fatalf("first claim=%+v err=%v", claimed, err)
	}
	digest := mongoStopHookDigest("ack receipt")
	if err := repository.AcknowledgeStopHook(
		t.Context(), claimed[0].InvocationID, "hook-owner-b", claimAt, digest,
	); !errors.Is(err, runruntime.ErrStopHookClaimLost) {
		t.Fatalf("foreign ack error=%v want claim lost", err)
	}
	if err := repository.ReleaseStopHookClaim(
		t.Context(), claimed[0].InvocationID, "hook-owner-b",
	); !errors.Is(err, runruntime.ErrStopHookClaimLost) {
		t.Fatalf("foreign release error=%v want claim lost", err)
	}
	due := claimAt.Add(2 * time.Second)
	if err := repository.ScheduleStopHookRetry(
		t.Context(), claimed[0].InvocationID, "hook-owner-a", claimAt, due, "hook_failed",
	); err != nil {
		t.Fatalf("schedule retry: %v", err)
	}
	beforeDue, err := repository.ClaimPendingStopHooks(
		t.Context(), "hook-owner-b", due.Add(-time.Nanosecond), time.Minute, 1,
	)
	if err != nil || len(beforeDue) != 0 {
		t.Fatalf("pre-due claim=%+v err=%v", beforeDue, err)
	}
	restarted, err := repository.ClaimPendingStopHooks(
		t.Context(), "hook-owner-b", due, time.Minute, 1,
	)
	if err != nil || len(restarted) != 1 || restarted[0].AttemptCount != 2 ||
		restarted[0].InvocationID != claimed[0].InvocationID {
		t.Fatalf("restart due claim=%+v first=%+v err=%v", restarted, claimed, err)
	}
	if err := repository.AcknowledgeStopHook(
		t.Context(), restarted[0].InvocationID, "hook-owner-b", due, digest,
	); err != nil {
		t.Fatalf("ack stop hook: %v", err)
	}
	// Exact acknowledgement replay models a client retry after the server
	// committed but its response was lost.
	if err := repository.AcknowledgeStopHook(
		t.Context(), restarted[0].InvocationID, "hook-owner-b", due.Add(time.Second), digest,
	); err != nil {
		t.Fatalf("exact ack replay: %v", err)
	}
	remaining, err := repository.ClaimPendingStopHooks(
		t.Context(), "hook-owner-c", due.Add(time.Hour), time.Minute, 1,
	)
	if err != nil || len(remaining) != 0 {
		t.Fatalf("processed hook reclaimed=%+v err=%v", remaining, err)
	}
}

func mongoStopHookMutation(
	t *testing.T,
	run runruntime.Run,
	outcome generated.AssistantRunState,
	now time.Time,
) (runruntime.Run, runruntime.JournalEvent, runruntime.CommandReceipt) {
	t.Helper()
	var path []generated.AssistantRunState
	switch outcome {
	case generated.AssistantRunStateCompleted:
		path = []generated.AssistantRunState{
			generated.AssistantRunStateOrienting,
			generated.AssistantRunStatePlanning,
			generated.AssistantRunStateExecuting,
			generated.AssistantRunStateObserving,
			generated.AssistantRunStateReflecting,
			generated.AssistantRunStateSynthesizing,
			generated.AssistantRunStateVerifying,
			generated.AssistantRunStateCompleted,
		}
	case generated.AssistantRunStateWaitingUser:
		path = []generated.AssistantRunState{
			generated.AssistantRunStateOrienting,
			generated.AssistantRunStateWaitingUser,
		}
	case generated.AssistantRunStateWaitingApproval,
		generated.AssistantRunStateWaitingExternal:
		path = []generated.AssistantRunState{
			generated.AssistantRunStateOrienting,
			generated.AssistantRunStatePlanning,
			generated.AssistantRunStateExecuting,
			outcome,
		}
	default:
		path = []generated.AssistantRunState{outcome}
	}
	for index, state := range path {
		if err := run.Transition(state, "stop_hook_test", now.Add(time.Duration(index)*time.Second)); err != nil {
			t.Fatalf("transition %s toward %s: %v", state, outcome, err)
		}
	}
	run.JournalSequence++
	event := runruntime.JournalEvent{
		EventID: run.RunID + ":stop-hook:" + outcome.WireName(),
		RunID:   run.RunID, Sequence: run.JournalSequence, Revision: run.Revision,
		Kind: "stop_hook_test", Payload: map[string]any{"outcome": outcome.WireName()},
		CreatedAt: run.UpdatedAt,
	}
	receipt := runruntime.CommandReceipt{
		RunID: run.RunID, CommandID: "stop-hook-" + outcome.WireName(),
		CommandKind: "stop_hook_test", PayloadDigest: mongoStopHookDigest(outcome.WireName()),
		Revision: run.Revision, CreatedAt: run.UpdatedAt,
	}
	return run, event, receipt
}

func assertMongoStopHookCommitFacts(
	t *testing.T,
	database *mongo.Database,
	repository runruntime.Repository,
	run runruntime.Run,
	event runruntime.JournalEvent,
	receipt runruntime.CommandReceipt,
) {
	t.Helper()
	current, err := repository.Load(t.Context(), run.RunID)
	if err != nil || current.Revision != run.Revision || current.State != run.State {
		t.Fatalf("committed Run=%+v want=%+v err=%v", current, run, err)
	}
	assertMongoCount(t, database, "assistant_run_events", bson.M{"_id": event.EventID}, 1)
	assertMongoCount(
		t, database, "assistant_run_command_receipts",
		bson.M{"runId": run.RunID, "commandId": receipt.CommandID}, 1,
	)
	assertMongoCount(t, database, "assistant_run_work_queue", bson.M{"_id": run.RunID}, 0)
	terminalCount := int64(0)
	switch run.State {
	case generated.AssistantRunStateCompleted,
		generated.AssistantRunStateFailed,
		generated.AssistantRunStateCancelled:
		terminalCount = 1
	}
	assertMongoCount(
		t, database, "assistant_run_terminal_outbox", bson.M{"runId": run.RunID}, terminalCount,
	)
	invocationID := runruntime.StableHookInvocationID(
		run.RunID, runruntime.HookOnStop, run.Revision,
	)
	var hookDocument struct {
		ID                   string         `bson:"_id"`
		RunID                string         `bson:"runId"`
		Phase                string         `bson:"phase"`
		Outcome              string         `bson:"outcome"`
		RunRevision          int64          `bson:"runRevision"`
		ProtectedFactsDigest string         `bson:"protectedFactsDigest"`
		Data                 map[string]any `bson:"data"`
	}
	if err := database.Collection("assistant_run_hook_outbox").FindOne(
		t.Context(), bson.M{"_id": invocationID},
	).Decode(&hookDocument); err != nil {
		t.Fatalf("load stop hook intent %s: %v", invocationID, err)
	}
	if hookDocument.ID != invocationID || hookDocument.RunID != run.RunID ||
		hookDocument.Phase != "on_stop" || hookDocument.Outcome != run.State.WireName() ||
		hookDocument.RunRevision != run.Revision ||
		hookDocument.ProtectedFactsDigest != runruntime.ProtectedRunFactsDigest(run) ||
		hookDocument.Data["outcome"] != run.State.WireName() {
		t.Fatalf("stop hook intent=%+v run=%+v", hookDocument, run)
	}
}

func assertMongoCount(
	t *testing.T,
	database *mongo.Database,
	collection string,
	filter bson.M,
	want int64,
) {
	t.Helper()
	got, err := database.Collection(collection).CountDocuments(t.Context(), filter)
	if err != nil || got != want {
		t.Fatalf("%s count=%d want=%d filter=%v err=%v", collection, got, want, filter, err)
	}
}

func mongoStopHookDigest(value string) string {
	digest := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(digest[:])
}

var _ runruntime.Hook = (*mongoStopHookCapture)(nil)
