// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package assistant_run_integration

import (
	"errors"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
)

func TestMongoWorkClaimFencesConcurrentExpiredWorkerCommit(t *testing.T) {
	database := requirePublicWebMongo(t)
	resetAssistantRunControlState(t)
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	// Keep the canonical Run clock behind the infrastructure clock so the
	// persisted work item is immediately claimable on any test host.
	commandNow := time.Now().UTC().Add(-time.Minute)
	run, err := newAssistantRunControlService(repository, &commandNow).Start(
		t.Context(),
		runruntime.StartCommand{
			UserID:          "mongo-fence-owner",
			PersonaID:       "mongo-fence-persona",
			SessionID:       "mongo-fence-session",
			ClientRequestID: "mongo-fence-start",
			InputText:       "验证真实 Mongo takeover fencing",
		},
	)
	if err != nil {
		t.Fatalf("start Run: %v", err)
	}
	first, err := repository.ClaimNext(t.Context(), "mongo-worker-old", time.Minute)
	if err != nil {
		t.Fatalf("claim old worker: %v", err)
	}
	if _, err := database.Collection("assistant_run_work_queue").UpdateOne(
		t.Context(),
		bson.M{"_id": run.RunID, "workerId": first.WorkerID, "fencingToken": first.FencingToken},
		bson.M{"$set": bson.M{"expiresAt": time.Now().UTC().Add(-time.Second)}},
	); err != nil {
		t.Fatalf("expire old infrastructure lease: %v", err)
	}
	second, err := repository.ClaimNext(t.Context(), "mongo-worker-current", time.Minute)
	if err != nil {
		t.Fatalf("take over expired claim: %v", err)
	}
	if second.FencingToken != first.FencingToken+1 {
		t.Fatalf("takeover fencingToken=%d want=%d", second.FencingToken, first.FencingToken+1)
	}

	baseline, err := repository.Load(t.Context(), run.RunID)
	if err != nil {
		t.Fatalf("load baseline: %v", err)
	}
	commitAt := time.Now().UTC()
	staleRun, staleEvent := workClaimMongoMutation(
		t, baseline, generated.AssistantRunStateOrienting, "mongo_stale_commit", commitAt,
	)
	winnerRun, winnerEvent := workClaimMongoMutation(
		t, baseline, generated.AssistantRunStateOrienting, "mongo_current_commit", commitAt,
	)
	type commitResult struct {
		name string
		err  error
	}
	start := make(chan struct{})
	results := make(chan commitResult, 2)
	var wait sync.WaitGroup
	for _, candidate := range []struct {
		name  string
		claim runruntime.WorkClaim
		run   runruntime.Run
		event runruntime.JournalEvent
	}{
		{name: "stale", claim: first, run: staleRun, event: staleEvent},
		{name: "winner", claim: second, run: winnerRun, event: winnerEvent},
	} {
		candidate := candidate
		wait.Add(1)
		go func() {
			defer wait.Done()
			<-start
			results <- commitResult{
				name: candidate.name,
				err: repository.CommitClaim(
					t.Context(), candidate.claim, baseline.Revision, candidate.run,
					[]runruntime.JournalEvent{candidate.event}, nil,
				),
			}
		}()
	}
	close(start)
	wait.Wait()
	close(results)
	for result := range results {
		switch result.name {
		case "stale":
			if !errors.Is(result.err, runruntime.ErrExecutionFenced) {
				t.Fatalf("stale concurrent commit error=%v want ErrExecutionFenced", result.err)
			}
		case "winner":
			if result.err != nil {
				t.Fatalf("current concurrent commit: %v", result.err)
			}
		}
	}

	current, err := repository.Load(t.Context(), run.RunID)
	if err != nil || current.Revision != winnerRun.Revision ||
		current.JournalSequence != winnerRun.JournalSequence {
		t.Fatalf("winner Run mismatch: run=%#v err=%v", current, err)
	}
	events, err := repository.EventsAfter(
		t.Context(), run.RunID, baseline.JournalSequence, 10,
	)
	if err != nil || len(events) != 1 || events[0].Kind != "mongo_current_commit" {
		t.Fatalf("winner journal=%#v err=%v", events, err)
	}

	staleRetry, staleRetryEvent := workClaimMongoMutation(
		t, current, generated.AssistantRunStatePlanning, "mongo_stale_retry", commitAt.Add(time.Second),
	)
	if err := repository.CommitClaim(
		t.Context(), first, current.Revision, staleRetry,
		[]runruntime.JournalEvent{staleRetryEvent}, nil,
	); !errors.Is(err, runruntime.ErrExecutionFenced) {
		t.Fatalf("stale retry at winner revision error=%v want ErrExecutionFenced", err)
	}
	var queueState struct {
		WorkerID                 string `bson:"workerId"`
		FencingToken             int64  `bson:"fencingToken"`
		LastCommittedRunRevision int64  `bson:"lastCommittedRunRevision"`
	}
	if err := database.Collection("assistant_run_work_queue").FindOne(
		t.Context(), bson.M{"_id": run.RunID},
	).Decode(&queueState); err != nil {
		t.Fatalf("load claim-bound queue state: %v", err)
	}
	if queueState.WorkerID != second.WorkerID ||
		queueState.FencingToken != second.FencingToken ||
		queueState.LastCommittedRunRevision != winnerRun.Revision {
		t.Fatalf("claim-bound queue state=%#v second=%#v", queueState, second)
	}
}

func workClaimMongoMutation(
	t *testing.T,
	baseline runruntime.Run,
	next generated.AssistantRunState,
	kind string,
	now time.Time,
) (runruntime.Run, runruntime.JournalEvent) {
	t.Helper()
	mutated := baseline
	if err := mutated.Transition(next, "", now); err != nil {
		t.Fatalf("transition to %s: %v", next, err)
	}
	mutated.JournalSequence++
	return mutated, runruntime.JournalEvent{
		EventID:   mutated.RunID + ":" + kind,
		RunID:     mutated.RunID,
		Sequence:  mutated.JournalSequence,
		Revision:  mutated.Revision,
		Kind:      kind,
		CreatedAt: now,
	}
}
