// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-003
package assistant_run_integration

import (
	"context"
	"errors"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
)

const durableSubtaskMongoInputDigest = "sha256:ec0438d0c4a9ac5ce08f97d5cf42f89e11f2fdf3c911a98af694030da068cb9c"

func TestDurableSubtaskRecoversExpiredMongoClaimWithoutRepeatingTerminalWork(
	t *testing.T,
) {
	database := requirePublicWebMongo(t)
	for _, collection := range []string{
		"assistant_runs",
		"assistant_run_events",
		"assistant_run_command_receipts",
		"assistant_run_worker_leases",
		"assistant_run_work_queue",
		"assistant_run_terminal_outbox",
	} {
		if _, err := database.Collection(collection).DeleteMany(
			t.Context(),
			map[string]any{},
		); err != nil {
			t.Fatalf("reset %s: %v", collection, err)
		}
	}
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	startedAt := time.Date(2026, 8, 4, 14, 0, 0, 0, time.UTC)
	run := persistDurableSubtaskMongoRun(t, repository, startedAt)
	currentTime := startedAt.Add(time.Second)
	storeA := orchestration.NewRepositoryDurableSubtaskStore(
		repository,
		func() time.Time { return currentTime },
	)
	request := orchestration.DurableSubtaskRequest{
		RunID:       run.RunID,
		TaskID:      durableSubtaskMongoTaskID(run.RunID),
		OwnerAgent:  "subagent:travel_companion",
		InputDigest: durableSubtaskMongoInputDigest,
	}
	first, terminal, err := storeA.Claim(
		t.Context(),
		request,
		"worker-a",
		30*time.Second,
	)
	if err != nil || terminal != nil {
		t.Fatalf("first Claim() claim=%#v terminal=%#v err=%v", first, terminal, err)
	}
	if _, _, err := storeA.Claim(
		t.Context(),
		request,
		"worker-b",
		30*time.Second,
	); !errors.Is(err, runruntime.ErrLeaseConflict) {
		t.Fatalf("unexpired duplicate claim error=%v", err)
	}

	// A new process owns a new store instance and takes over only after the
	// persisted lease expires. No worker-local state participates in recovery.
	currentTime = first.LeaseExpiresAt.Add(time.Millisecond)
	storeB := orchestration.NewRepositoryDurableSubtaskStore(
		repository,
		func() time.Time { return currentTime },
	)
	second, terminal, err := storeB.Claim(
		t.Context(),
		request,
		"worker-b",
		30*time.Second,
	)
	if err != nil || terminal != nil {
		t.Fatalf("takeover Claim() claim=%#v terminal=%#v err=%v", second, terminal, err)
	}
	if second.Attempt != first.Attempt+1 ||
		second.FencingToken != first.FencingToken+1 {
		t.Fatalf("takeover did not advance claim: first=%#v second=%#v", first, second)
	}
	if err := storeB.Heartbeat(
		t.Context(),
		second,
		30*time.Second,
	); err != nil {
		t.Fatalf("Heartbeat() error=%v", err)
	}
	currentTime = currentTime.Add(time.Second)
	receipt, err := storeB.Finish(
		t.Context(),
		second,
		orchestration.DurableSubtaskResult{
			Outcome: orchestration.DurableSubtaskCompleted,
			Summary: "旅行子任务证据已完成",
			Payload: map[string]any{
				"finalText":      "旅行子任务证据已完成",
				"referenceCount": 3,
			},
		},
	)
	if err != nil {
		t.Fatalf("Finish() error=%v", err)
	}
	if receipt.Attempt != second.Attempt ||
		receipt.FencingToken != second.FencingToken ||
		receipt.ResultArtifactRef == "" {
		t.Fatalf("terminal receipt is incomplete: %#v", receipt)
	}

	storeAfterRestart := orchestration.NewRepositoryDurableSubtaskStore(
		repository,
		func() time.Time { return currentTime.Add(time.Minute) },
	)
	coordinator := orchestration.NewDurableSubtaskCoordinator(
		storeAfterRestart,
		"worker-c",
		30*time.Second,
		10*time.Second,
	)
	var repeatedWork atomic.Int64
	recovered, err := coordinator.Execute(
		t.Context(),
		request,
		func(
			context.Context,
			orchestration.DurableSubtaskClaim,
		) (orchestration.DurableSubtaskResult, error) {
			repeatedWork.Add(1)
			return orchestration.DurableSubtaskResult{}, nil
		},
	)
	if err != nil || repeatedWork.Load() != 0 ||
		recovered.ReceiptRef != receipt.ReceiptRef {
		t.Fatalf(
			"terminal recovery repeated work=%d receipt=%#v err=%v",
			repeatedWork.Load(),
			recovered,
			err,
		)
	}

	persisted, err := repository.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatalf("load persisted Run: %v", err)
	}
	task := persisted.TaskGraph.Tasks[1]
	if task.Status != generated.AssistantTaskStatusCompleted ||
		task.Attempt != second.Attempt ||
		task.FencingToken != second.FencingToken ||
		task.TerminalReceiptRef != receipt.ReceiptRef {
		t.Fatalf("persisted child task mismatch: %#v", task)
	}
	terminalItems := 0
	for _, item := range persisted.Items {
		if strings.HasPrefix(item.ItemID, "subtask-terminal:") {
			terminalItems++
		}
	}
	if terminalItems != 1 {
		t.Fatalf("terminal RunItems=%d want exactly one", terminalItems)
	}
	events, err := repository.EventsAfter(t.Context(), run.RunID, 0, 100)
	if err != nil {
		t.Fatalf("EventsAfter() error=%v", err)
	}
	if len(events) != 6 {
		t.Fatalf("journal events=%d want start/process/claim/takeover/heartbeat/terminal", len(events))
	}
	for index, event := range events {
		if event.Sequence != int64(index+1) {
			t.Fatalf("journal sequence[%d]=%d", index, event.Sequence)
		}
	}
}

func persistDurableSubtaskMongoRun(
	t *testing.T,
	repository runruntime.Repository,
	now time.Time,
) runruntime.Run {
	t.Helper()
	graph, err := runruntime.NewTaskGraph([]runruntime.TaskNode{{
		TaskID: "task_root",
		Goal:   "完成可恢复的旅行研究",
	}})
	if err != nil {
		t.Fatalf("NewTaskGraph() error=%v", err)
	}
	run, err := runruntime.NewRun(
		"run-durable-subtask-mongo",
		generated.AssistantReasoningProfileDeep,
		runruntime.DefinitionOfDone{
			Outcome:                  "完成可恢复的旅行研究",
			VerificationRequirements: []string{"child_terminal_receipt"},
			FrozenAt:                 now,
		},
		graph,
		now,
	)
	if err != nil {
		t.Fatalf("NewRun() error=%v", err)
	}
	if err := run.BindIdentity(
		"account-durable-subtask",
		"persona-durable-subtask",
		"session-durable-subtask",
		"request-durable-subtask",
		"trace-durable-subtask",
		"规划一次可恢复旅行",
	); err != nil {
		t.Fatalf("BindIdentity() error=%v", err)
	}
	if err := run.BindExecutionInput(
		"answer",
		"sha256:da30e2f7034bb12d5cbb2933ab4550a33af7bc0a8f58e484b259724a2a51416e",
		"travel_companion",
		"travel",
		nil,
		nil,
		nil,
	); err != nil {
		t.Fatalf("BindExecutionInput() error=%v", err)
	}
	if err := run.BindSkillPackage(
		"quwoquan.official",
		"sha256:74b8ab4b291e0bb69f3c41e349f3e0e0d87d1aa986aac5427e007d51592939a9",
	); err != nil {
		t.Fatalf("BindSkillPackage() error=%v", err)
	}
	run.JournalSequence = 1
	if err := repository.Commit(
		t.Context(),
		0,
		run,
		[]runruntime.JournalEvent{{
			EventID:   run.RunID + ":1",
			RunID:     run.RunID,
			Sequence:  1,
			Revision:  run.Revision,
			Kind:      "run_accepted",
			Payload:   map[string]any{"status": run.State.WireName()},
			CreatedAt: now,
		}},
		nil,
	); err != nil {
		t.Fatalf("commit initial Run: %v", err)
	}
	loaded, err := repository.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatalf("load initial Run: %v", err)
	}
	expectedRevision := loaded.Revision
	if err := loaded.TaskGraph.Add(runruntime.TaskNode{
		TaskID:     durableSubtaskMongoTaskID(run.RunID),
		Goal:       "检索并核验旅行路线",
		OwnerAgent: "subagent:travel_companion",
	}); err != nil {
		t.Fatalf("add child task: %v", err)
	}
	if err := loaded.TaskGraph.Start(durableSubtaskMongoTaskID(run.RunID)); err != nil {
		t.Fatalf("start child task: %v", err)
	}
	if err := loaded.BeginItem(
		"subagent:travel:executing",
		generated.AssistantRunItemKindSubagent,
		durableSubtaskMongoTaskID(run.RunID),
		"检索并核验旅行路线",
		map[string]any{"status": "active"},
		now.Add(time.Millisecond),
	); err != nil {
		t.Fatalf("begin child process item: %v", err)
	}
	loaded.JournalSequence++
	if err := repository.Commit(
		t.Context(),
		expectedRevision,
		loaded,
		[]runruntime.JournalEvent{{
			EventID:   loaded.RunID + ":2",
			RunID:     loaded.RunID,
			Sequence:  loaded.JournalSequence,
			Revision:  loaded.Revision,
			Kind:      "process_append",
			Payload:   map[string]any{"status": loaded.State.WireName()},
			CreatedAt: now.Add(time.Millisecond),
		}},
		nil,
	); err != nil {
		t.Fatalf("commit child process item: %v", err)
	}
	return loaded
}

func durableSubtaskMongoTaskID(runID string) string {
	return "run:" + runID + ":goal:1:task:subagent:travel:executing"
}
