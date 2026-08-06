package reliabletask

import (
	"context"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

type observationStoreStub struct {
	tasks []ReliableAsyncTask
}

func (s observationStoreStub) ListDataContentExecutionTasks(
	_ context.Context,
	_ string,
) ([]ReliableAsyncTask, error) {
	return append([]ReliableAsyncTask(nil), s.tasks...), nil
}

type readyObservationStub struct {
	snapshot ReadyIndexObservation
}

func (s readyObservationStub) Observe(
	_ context.Context,
	_ int64,
) (ReadyIndexObservation, error) {
	return s.snapshot, nil
}

func observedTask(
	executionID string,
	carrier string,
	jobID string,
	status string,
	createdAt time.Time,
	updatedAt time.Time,
) ReliableAsyncTask {
	sourceRevision := "sha256:" + strings.Repeat("a", 64)
	entityRef := "/entity/地点/景区/observer"
	stage := "author"
	idempotencyKey := executionID + "|" + entityRef + "|" + carrier + "|" +
		sourceRevision + "|" + stage
	return ReliableAsyncTask{
		TaskID:         "runtime-" + jobID,
		TaskType:       DataContentTaskType,
		IdempotencyKey: idempotencyKey,
		Payload: map[string]string{
			"schema":         "quwoquan.object_job",
			"jobId":          jobID,
			"executionId":    executionID,
			"ref":            "objects/" + jobID,
			"stage":          stage,
			"partitionKey":   entityRef,
			"entityRef":      entityRef,
			"carrier":        carrier,
			"sourceRevision": sourceRevision,
			"idempotencyKey": idempotencyKey,
		},
		Status:        status,
		Attempts:      1,
		NextAttemptAt: createdAt,
		CreatedAt:     createdAt,
		UpdatedAt:     updatedAt,
	}
}

func TestDataContentObserverBindsMongoAndRedisToOneExecution(t *testing.T) {
	now := time.Date(2026, 8, 6, 8, 0, 0, 0, time.UTC)
	executionID := "20260806--travel-homepage-m3--china--scale-001"
	readyTask := observedTask(
		executionID,
		"homepage",
		"job-ready",
		TaskStatusReady,
		now.Add(-2*time.Minute),
		now.Add(-time.Minute),
	)
	succeededTask := observedTask(
		executionID,
		"homepage",
		"job-succeeded",
		TaskStatusSucceeded,
		now.Add(-3*time.Minute),
		now.Add(-30*time.Second),
	)
	observer := DataContentExecutionObserver{
		Store: observationStoreStub{tasks: []ReliableAsyncTask{
			readyTask,
			succeededTask,
		}},
		Ready: readyObservationStub{snapshot: ReadyIndexObservation{
			Entries: []ReadyIndexObservationEntry{
				{TaskID: readyTask.TaskID, EnqueuedAt: now.Add(-45 * time.Second)},
				{TaskID: succeededTask.TaskID, EnqueuedAt: now.Add(-2 * time.Minute)},
			},
			PendingCount: 0,
		}},
		Now: func() time.Time { return now },
	}
	request := DataContentExecutionObservationRequest{
		ExecutionID:          executionID,
		Carrier:              "homepage",
		RequestBindingDigest: "sha256:" + strings.Repeat("b", 64),
	}
	observation, err := observer.ObserveExecution(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	if len(observation.Tasks) != 2 || len(observation.ReadyJobTimestamps) != 1 ||
		len(observation.PendingJobTimestamps) != 1 ||
		observation.SuccessfulJobCount != 1 || observation.TerminalJobCount != 1 {
		t.Fatalf("unexpected execution observation: %#v", observation)
	}
	if observation.ReadyJobTimestamps[0] != timestamp(now.Add(-45*time.Second)) {
		t.Fatalf("oldest ready timestamp did not come from Redis: %#v", observation)
	}
	withoutDigest := observation
	withoutDigest.ObservationDigest = ""
	expectedDigest, err := canonicalObservationDigest(withoutDigest)
	if err != nil {
		t.Fatal(err)
	}
	if observation.ObservationDigest != expectedDigest {
		t.Fatalf("observation digest=%s want=%s", observation.ObservationDigest, expectedDigest)
	}
	payload, err := MarshalDataContentExecutionObservation(observation)
	if err != nil {
		t.Fatal(err)
	}
	text := string(payload)
	if !strings.HasPrefix(text, `{"activeLeaseCount":`) {
		t.Fatalf("observation JSON is not canonical: %s", text)
	}
	for _, forbidden := range []string{"leaseToken", "leaseOwner", "mongodb://", "redis://", "password"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("observation leaked forbidden field %q: %s", forbidden, text)
		}
	}
}

func TestDataContentObserverRejectsCrossExecutionRedisEntry(t *testing.T) {
	now := time.Now().UTC()
	executionID := "20260806--travel-image-m3--china--scale-001"
	task := observedTask(executionID, "image", "job-image", TaskStatusReady, now, now)
	observer := DataContentExecutionObserver{
		Store: observationStoreStub{tasks: []ReliableAsyncTask{task}},
		Ready: readyObservationStub{snapshot: ReadyIndexObservation{
			Entries: []ReadyIndexObservationEntry{{
				TaskID:     "runtime-foreign",
				EnqueuedAt: now,
			}},
		}},
		Now: func() time.Time { return now },
	}
	_, err := observer.ObserveExecution(
		context.Background(),
		DataContentExecutionObservationRequest{
			ExecutionID:          executionID,
			Carrier:              "image",
			RequestBindingDigest: "sha256:" + strings.Repeat("c", 64),
		},
	)
	if err == nil || !strings.Contains(err.Error(), "crossed executionId") {
		t.Fatalf("cross execution Redis row was not rejected: %v", err)
	}
}

func TestDataContentObserverRejectsMongoCarrierAndSourceIdentityDrift(t *testing.T) {
	now := time.Now().UTC()
	executionID := "20260806--travel-video-m3--china--scale-001"
	task := observedTask(executionID, "image", "job-video", TaskStatusReady, now, now)
	observer := DataContentExecutionObserver{
		Store: observationStoreStub{tasks: []ReliableAsyncTask{task}},
		Ready: readyObservationStub{},
		Now:   func() time.Time { return now },
	}
	request := DataContentExecutionObservationRequest{
		ExecutionID:          executionID,
		Carrier:              "video",
		RequestBindingDigest: "sha256:" + strings.Repeat("d", 64),
	}
	if _, err := observer.ObserveExecution(context.Background(), request); err == nil ||
		!strings.Contains(err.Error(), "identity drift") {
		t.Fatalf("carrier drift was not rejected: %v", err)
	}

	task = observedTask(executionID, "video", "job-video", TaskStatusReady, now, now)
	task.Payload["sourceRevision"] = "sha256:" + strings.Repeat("e", 64)
	observer.Store = observationStoreStub{tasks: []ReliableAsyncTask{task}}
	if _, err := observer.ObserveExecution(context.Background(), request); err == nil ||
		!strings.Contains(err.Error(), "source identity drift") {
		t.Fatalf("source drift was not rejected: %v", err)
	}
}

func TestRedisReadyIndexObserveDoesNotMutateStream(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	ready, err := NewRedisReadyIndex(RedisReadyIndexConfig{
		Client: client,
		Stream: "reliabletask:data:content:observer-test",
		Group:  "data.content_supply.observer-test",
		Queue:  DataContentQueue,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := ready.Ensure(ctx); err != nil {
		t.Fatal(err)
	}
	task := ReliableAsyncTask{TaskID: "runtime-job", TaskType: DataContentTaskType}
	if err := ready.EnqueueReadyOrMerge(ctx, task); err != nil {
		t.Fatal(err)
	}
	before, err := client.XRead(ctx, map[string]string{ready.stream: "0-0"}, 10, 0)
	if err != nil {
		t.Fatal(err)
	}
	snapshot, err := ready.Observe(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	after, err := client.XRead(ctx, map[string]string{ready.stream: "0-0"}, 10, 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(before) != 1 || len(snapshot.Entries) != 1 || len(after) != 1 ||
		before[0].ID != after[0].ID || snapshot.Entries[0].TaskID != task.TaskID {
		t.Fatalf("read-only observer mutated stream: before=%#v snapshot=%#v after=%#v", before, snapshot, after)
	}
}
