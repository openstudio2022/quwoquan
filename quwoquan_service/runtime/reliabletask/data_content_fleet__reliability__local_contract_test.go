package reliabletask

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"
)

func dataJob(i int) DataContentJob {
	entity := fmt.Sprintf("entity/地点/景区/%03d", i)
	return DataContentJob{
		EntityRef:      entity,
		Carrier:        "homepage",
		SourceRevision: fmt.Sprintf("sha256:%064d", i+1),
		JobID:          fmt.Sprintf("job-%03d", i),
		TaskID:         "data-commercial",
		BatchID:        "fleet-local-contract",
		Ref:            entity,
		Stage:          "author",
		PartitionKey:   entity,
	}
}

func TestDataContentFleetIdempotencySurvivesCompletion(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	fleet := DataContentFleet{Store: store, WorkerID: "worker-1"}
	first, err := fleet.Declare(ctx, dataJob(1))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := fleet.Dispatch(ctx, 10); err != nil {
		t.Fatal(err)
	}
	processed, err := fleet.ProcessOne(ctx, func(context.Context, ReliableAsyncTask) error { return nil })
	if err != nil || !processed {
		t.Fatalf("process failed: processed=%v err=%v", processed, err)
	}
	second, err := fleet.Declare(ctx, dataJob(1))
	if err != nil {
		t.Fatal(err)
	}
	if first.OutboxID != second.OutboxID {
		t.Fatalf("same entity+carrier+sourceRevision duplicated outbox: %s != %s", first.OutboxID, second.OutboxID)
	}
	tasks, err := fleet.Dispatch(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(tasks) != 0 {
		t.Fatalf("idempotent replay must not republish completed task: %d", len(tasks))
	}
}

func TestDataContentFleetLoadRecoveryAndDeadLetter(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	now := time.Now().UTC().Add(time.Minute)
	var mu sync.Mutex
	clock := func() time.Time {
		mu.Lock()
		defer mu.Unlock()
		return now
	}
	advance := func(d time.Duration) {
		mu.Lock()
		now = now.Add(d)
		mu.Unlock()
	}
	fleet := DataContentFleet{
		Store:    store,
		WorkerID: "worker-load",
		LeaseTTL: 20 * time.Millisecond,
		Retry:    RetryPolicy{MaxAttempts: 3, Backoff: []time.Duration{time.Millisecond}},
		Now:      clock,
	}
	const total = 100
	for i := 0; i < total; i++ {
		if _, err := fleet.Declare(ctx, dataJob(i)); err != nil {
			t.Fatal(err)
		}
	}
	if tasks, err := fleet.Dispatch(ctx, total); err != nil || len(tasks) != total {
		t.Fatalf("dispatch total=%d err=%v", len(tasks), err)
	}
	attempts := map[string]int{}
	completed := 0
	for completed < total {
		processed, err := fleet.ProcessOne(ctx, func(_ context.Context, task ReliableAsyncTask) error {
			attempts[task.TaskID]++
			// 5 个对象首轮失败后自动恢复；1 个对象持续失败进入 DLQ。
			if attempts[task.TaskID] == 1 && len(attempts) <= 5 {
				return errors.New("transient")
			}
			if task.AggregateID == dataJob(99).EntityRef {
				return errors.New("permanent")
			}
			completed++
			return nil
		})
		if err != nil {
			t.Fatal(err)
		}
		if !processed {
			advance(10 * time.Millisecond)
		}
		dead, err := store.ListDeadTasks(ctx, []string{DataContentTaskType}, 10)
		if err != nil {
			t.Fatal(err)
		}
		if len(dead) == 1 {
			break
		}
	}
	dead, err := store.ListDeadTasks(ctx, []string{DataContentTaskType}, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(dead) != 1 {
		t.Fatalf("expected one dead task, got %d", len(dead))
	}
	recovered := total - len(dead)
	if float64(recovered)/total < 0.95 {
		t.Fatalf("automatic recovery below 95%%: %d/%d", recovered, total)
	}
	if err := store.RecoverDeadTask(ctx, dead[0].TaskID, clock()); err != nil {
		t.Fatal(err)
	}
	processed, err := fleet.ProcessOne(ctx, func(context.Context, ReliableAsyncTask) error {
		completed++
		return nil
	})
	if err != nil || !processed || completed != total {
		t.Fatalf("DLQ recovery failed: processed=%v completed=%d err=%v", processed, completed, err)
	}
}

func TestDataContentJobRequiresStableIdentity(t *testing.T) {
	if _, err := (DataContentJob{EntityRef: "e", Carrier: "homepage"}).IdempotencyKey(); err == nil {
		t.Fatal("missing sourceRevision must fail closed")
	}
}
