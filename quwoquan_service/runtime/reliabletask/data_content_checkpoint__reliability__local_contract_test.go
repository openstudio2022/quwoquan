package reliabletask

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"
)

func succeededCheckpointTasks(count int) []ReliableAsyncTask {
	tasks := make([]ReliableAsyncTask, 0, count)
	for index := 0; index < count; index++ {
		tasks = append(tasks, ReliableAsyncTask{
			Status: TaskStatusSucceeded,
			Payload: map[string]string{
				"partitionKey": "0",
				"jobId":        fmt.Sprintf("job-%04d", index),
			},
		})
	}
	return tasks
}

func TestDataContentCheckpointCadenceUsesFirstReachedThreshold(t *testing.T) {
	epoch := time.Date(2026, 8, 8, 0, 0, 0, 0, time.UTC)
	tracker := NewDataContentCheckpointTracker(epoch)
	digest := "sha256:" + strings.Repeat("a", 64)
	due, err := tracker.Due(
		"execution-1", "publish", digest, succeededCheckpointTasks(99),
		100, 900*time.Second, epoch.Add(899*time.Second), false,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(due) != 0 {
		t.Fatalf("checkpoint flushed before either threshold: %+v", due)
	}
	due, err = tracker.Due(
		"execution-1", "publish", digest, succeededCheckpointTasks(99),
		100, 900*time.Second, epoch.Add(900*time.Second), false,
	)
	if err != nil || len(due) != 1 || due[0].CompletedCount != 99 {
		t.Fatalf("time threshold checkpoint=%+v err=%v", due, err)
	}

	tracker = NewDataContentCheckpointTracker(epoch)
	due, err = tracker.Due(
		"execution-1", "publish", digest, succeededCheckpointTasks(100),
		100, 900*time.Second, epoch.Add(time.Second), false,
	)
	if err != nil || len(due) != 1 || due[0].CompletedCount != 100 {
		t.Fatalf("object threshold checkpoint=%+v err=%v", due, err)
	}
}

func TestDataContentCheckpointCadenceFlushesTerminalResidualOnce(t *testing.T) {
	epoch := time.Date(2026, 8, 8, 0, 0, 0, 0, time.UTC)
	tracker := NewDataContentCheckpointTracker(epoch)
	digest := "sha256:" + strings.Repeat("a", 64)
	tasks := succeededCheckpointTasks(7)
	due, err := tracker.Due(
		"execution-1", "publish", digest, tasks,
		100, 900*time.Second, epoch.Add(time.Second), true,
	)
	if err != nil || len(due) != 1 {
		t.Fatalf("terminal checkpoint=%+v err=%v", due, err)
	}
	tracker.Commit(due[0])
	due, err = tracker.Due(
		"execution-1", "publish", digest, tasks,
		100, 900*time.Second, epoch.Add(2*time.Second), true,
	)
	if err != nil || len(due) != 0 {
		t.Fatalf("terminal checkpoint must be idempotent: %+v err=%v", due, err)
	}
}

func TestDataContentCheckpointRejectsStaleJobSetFence(t *testing.T) {
	store := NewMemoryStore()
	checkpoint := DataContentPartitionCheckpoint{
		ExecutionID:    "execution-1",
		Stage:          "publish",
		PartitionKey:   "0",
		JobSetDigest:   "sha256:" + strings.Repeat("a", 64),
		CursorJobID:    "job-0100",
		CompletedCount: 100,
		FlushedAt:      time.Now().UTC(),
	}
	if err := store.FlushDataContentPartitionCheckpoint(context.Background(), checkpoint); err != nil {
		t.Fatal(err)
	}
	checkpoint.JobSetDigest = "sha256:" + strings.Repeat("b", 64)
	checkpoint.CursorJobID = "job-0200"
	checkpoint.CompletedCount = 200
	if err := store.FlushDataContentPartitionCheckpoint(context.Background(), checkpoint); err == nil ||
		!strings.Contains(err.Error(), "STALE_FENCE") {
		t.Fatalf("stale job-set fence was not rejected: %v", err)
	}
}
