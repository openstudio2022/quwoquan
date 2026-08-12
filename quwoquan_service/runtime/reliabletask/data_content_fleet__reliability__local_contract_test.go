package reliabletask

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"
)

type captureReadyIndex struct {
	tasks []ReliableAsyncTask
}

func (r *captureReadyIndex) Ensure(context.Context) error { return nil }

func (r *captureReadyIndex) EnqueueReadyOrMerge(
	_ context.Context,
	task ReliableAsyncTask,
) error {
	r.tasks = append(r.tasks, task)
	return nil
}

func (r *captureReadyIndex) Claim(
	context.Context,
	string,
	int64,
	time.Duration,
) ([]ReadyIndexMessage, error) {
	return nil, nil
}

func (r *captureReadyIndex) Ack(context.Context, ReadyIndexMessage) error { return nil }

func dataJob(i int) DataContentJob {
	entity := fmt.Sprintf("entity/地点/景区/%03d", i)
	job := DataContentJob{
		EntityRef:      entity,
		Carrier:        "homepage",
		SourceRevision: fmt.Sprintf("sha256:%064d", i+1),
		JobID:          fmt.Sprintf("job-%03d", i),
		ExecutionID:    "20260719--travel-homepage-coverage--cn-zhejiang--canary-001",
		Ref:            entity,
		Stage:          "author",
		PartitionKey:   entity,
		MaxAttempts:    3,
	}
	return bindDataJob(job)
}

func bindDataJob(job DataContentJob) DataContentJob {
	key, err := job.ExpectedIdempotencyKey()
	if err != nil {
		panic(err)
	}
	job.IdempotencyKey = key
	job.JobSetEnvelopeDigest = "sha256:" + strings.Repeat("e", 64)
	job.JobSetDigest = "sha256:" + strings.Repeat("f", 64)
	job.ActualTaskDigest = job.JobSetDigest
	return job
}

func dataPublishJob(i int) DataContentJob {
	job := dataJob(i)
	job.JobID = fmt.Sprintf("publish-job-%03d", i)
	job.Stage = "publish"
	return bindDataJob(job)
}

func TestDataContentTaskDigestBindsPerJobMaxAttempts(t *testing.T) {
	job := dataJob(1)
	digest, err := DataContentTaskDigest([]DataContentJob{job})
	if err != nil {
		t.Fatal(err)
	}
	const pythonCanonicalDigest = "sha256:dc34c4fcdb4316ce53ae642a595808acc1a61e8bc1d3a8331e6e1c9cd2311edd"
	if digest != pythonCanonicalDigest {
		t.Fatalf("Python/Go canonical task digest drift: %s", digest)
	}
	job.MaxAttempts = 2
	changed, err := DataContentTaskDigest([]DataContentJob{job})
	if err != nil {
		t.Fatal(err)
	}
	if changed == digest {
		t.Fatal("maxAttempts changed without changing the frozen task digest")
	}
}

func TestDataContentFleetIdempotencySurvivesCompletion(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	fleet := DataContentFleet{
		Store:       store,
		ExecutionID: dataJob(1).ExecutionID,
		WorkerID:    "worker-1",
	}
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
		t.Fatalf("same execution identity duplicated outbox: %s != %s", first.OutboxID, second.OutboxID)
	}
	tasks, err := fleet.Dispatch(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(tasks) != 0 {
		t.Fatalf("idempotent replay must not republish completed task: %d", len(tasks))
	}
}

func TestDataContentFleetRetryExecutionDoesNotReusePriorTask(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	original := dataJob(1)
	originalFleet := DataContentFleet{
		Store:       store,
		ExecutionID: original.ExecutionID,
		WorkerID:    "worker-retry-original",
	}
	first, err := originalFleet.Declare(ctx, original)
	if err != nil {
		t.Fatal(err)
	}
	retry := original
	retry.ExecutionID = "20260720--travel-homepage-coverage--cn-zhejiang--canary-002"
	retry.JobID = "job-001-retry"
	retry = bindDataJob(retry)
	retryFleet := DataContentFleet{
		Store:       store,
		ExecutionID: retry.ExecutionID,
		WorkerID:    "worker-retry-next",
	}
	second, err := retryFleet.Declare(ctx, retry)
	if err != nil {
		t.Fatal(err)
	}
	if first.OutboxID == second.OutboxID {
		t.Fatalf(
			"new retry execution reused prior task outbox %q",
			first.OutboxID,
		)
	}

	originalTasks, err := originalFleet.Dispatch(ctx, 10)
	if err != nil || len(originalTasks) != 1 {
		t.Fatalf("original execution dispatch=%d err=%v", len(originalTasks), err)
	}
	retryTasks, err := retryFleet.Dispatch(ctx, 10)
	if err != nil || len(retryTasks) != 1 {
		t.Fatalf("retry execution dispatch=%d err=%v", len(retryTasks), err)
	}
}

func TestDataContentFleetEnqueuesOnlyHostAssignedPartitions(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	ready := &captureReadyIndex{}
	first := dataJob(41)
	second := dataJob(42)
	fleet := DataContentFleet{
		Store: store, ExecutionID: first.ExecutionID, Ready: ready,
		AllowedPartitions: map[string]struct{}{first.PartitionKey: {}},
	}
	if _, err := fleet.Declare(ctx, first); err != nil {
		t.Fatal(err)
	}
	if _, err := fleet.Declare(ctx, second); err != nil {
		t.Fatal(err)
	}
	dispatched, err := fleet.Dispatch(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(dispatched) != 1 || len(ready.tasks) != 1 || ready.tasks[0].PartitionKey != first.PartitionKey {
		t.Fatalf("host claimed cross-partition work: dispatched=%#v ready=%#v", dispatched, ready.tasks)
	}
	ready.tasks = nil
	count, err := fleet.ReconcileReadyIndex(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 || len(ready.tasks) != 1 || ready.tasks[0].PartitionKey != first.PartitionKey {
		t.Fatalf("host reconciled cross-partition work: count=%d ready=%#v", count, ready.tasks)
	}
}

func TestDataContentWorkerFenceRevokesLiveOldGenerationLease(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	oldFence := DataContentWorkerFence{
		HostSetDigest: "sha256:" + strings.Repeat("1", 64), Generation: 1,
		FencingToken: "sha256:" + strings.Repeat("2", 64), HostScopeID: "worker-old",
	}
	job := dataJob(51)
	job.WorkerFence = &oldFence
	fleet := DataContentFleet{Store: store, ExecutionID: job.ExecutionID}
	if _, err := fleet.Declare(ctx, job); err != nil {
		t.Fatal(err)
	}
	tasks, err := fleet.Dispatch(ctx, 10)
	if err != nil || len(tasks) != 1 {
		t.Fatalf("dispatch: tasks=%#v err=%v", tasks, err)
	}
	oldTask, err := store.ClaimReadyTaskByIDWithFence(
		ctx, tasks[0].TaskID, "old-worker", time.Minute, time.Now().UTC(), oldFence.payload(),
	)
	if err != nil || oldTask == nil {
		t.Fatalf("old claim: task=%#v err=%v", oldTask, err)
	}
	newFence := DataContentWorkerFence{
		HostSetDigest: "sha256:" + strings.Repeat("3", 64), Generation: 2,
		FencingToken: "sha256:" + strings.Repeat("4", 64), HostScopeID: "worker-new",
	}
	if ok, err := store.AdvanceDataContentTaskFence(ctx, tasks[0].TaskID, newFence, time.Now().UTC()); err != nil || !ok {
		t.Fatalf("advance fence: ok=%v err=%v", ok, err)
	}
	if err := store.CompleteTask(ctx, oldTask.TaskID, oldTask.LeaseToken); err == nil {
		t.Fatal("revoked old generation lease completed task")
	}
	stale, err := store.ClaimReadyTaskByIDWithFence(
		ctx, tasks[0].TaskID, "old-worker", time.Minute, time.Now().UTC(), oldFence.payload(),
	)
	if err != nil || stale != nil {
		t.Fatalf("old generation reclaimed: task=%#v err=%v", stale, err)
	}
	fresh, err := store.ClaimReadyTaskByIDWithFence(
		ctx, tasks[0].TaskID, "new-worker", time.Minute, time.Now().UTC(), newFence.payload(),
	)
	if err != nil || fresh == nil {
		t.Fatalf("new generation claim: task=%#v err=%v", fresh, err)
	}
}

func TestDecodeDataContentWorkItemCarriesExactWorkerHostFence(t *testing.T) {
	job := dataJob(52)
	job.WorkerFence = &DataContentWorkerFence{
		HostSetDigest: "sha256:" + strings.Repeat("5", 64), Generation: 3,
		FencingToken: "sha256:" + strings.Repeat("6", 64), HostScopeID: "worker-host-a",
	}
	task := ReliableAsyncTask{
		TaskID:         "runtime-task-52",
		TaskType:       DataContentTaskType,
		AggregateID:    job.EntityRef,
		IdempotencyKey: job.IdempotencyKey,
		PartitionKey:   job.PartitionKey,
		Payload:        job.payload(job.IdempotencyKey),
		LeaseToken:     "lease-52",
	}
	item, err := DecodeDataContentWorkItem(task)
	if err != nil {
		t.Fatal(err)
	}
	if item.WorkerHostSetDigest != job.WorkerFence.HostSetDigest ||
		item.WorkerHostGeneration != job.WorkerFence.Generation ||
		item.WorkerFencingToken != job.WorkerFence.FencingToken ||
		item.WorkerHostScopeID != job.WorkerFence.HostScopeID {
		t.Fatalf("worker host fence transit drift: %#v", item)
	}
	delete(task.Payload, "workerFencingToken")
	if _, err := DecodeDataContentWorkItem(task); err == nil ||
		!strings.Contains(err.Error(), "host fence is incomplete") {
		t.Fatalf("incomplete worker host fence was accepted: %v", err)
	}
}

func TestDataContentFleetAuditedRecoveryReleasesNewLease(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	fleet := DataContentFleet{
		Store:       store,
		ExecutionID: dataPublishJob(3).ExecutionID,
		WorkerID:    "worker-recovery",
		Retry:       RetryPolicy{MaxAttempts: 1},
	}
	job := dataPublishJob(3)
	job.MaxAttempts = 1
	if _, err := fleet.Declare(ctx, job); err != nil {
		t.Fatal(err)
	}
	if _, err := fleet.Dispatch(ctx, 1); err != nil {
		t.Fatal(err)
	}
	if processed, err := fleet.ProcessOne(ctx, func(context.Context, ReliableAsyncTask) error {
		return errors.New("canonical target was present before audited cleanup")
	}); err != nil || !processed {
		t.Fatalf("expected terminal publish failure: processed=%v err=%v", processed, err)
	}
	recovered, err := fleet.RecoverAuditedDeadJobs(ctx, []DataContentJob{job})
	if err != nil || recovered != 1 {
		t.Fatalf("audited dead-task recovery=%d err=%v", recovered, err)
	}
	if processed, err := fleet.ProcessOne(ctx, func(context.Context, ReliableAsyncTask) error {
		return nil
	}); err != nil || !processed {
		t.Fatalf("recovered task did not receive a new lease: processed=%v err=%v", processed, err)
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
		Store:       store,
		ExecutionID: dataJob(1).ExecutionID,
		WorkerID:    "worker-load",
		LeaseTTL:    20 * time.Millisecond,
		Retry:       RetryPolicy{MaxAttempts: 2, Backoff: []time.Duration{time.Millisecond}},
		Now:         clock,
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
	if attempts[dead[0].TaskID] != 3 {
		t.Fatalf(
			"per-job maxAttempts=3 must allow the third execution despite fleet default=2: attempts=%d",
			attempts[dead[0].TaskID],
		)
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
	if _, err := (DataContentJob{EntityRef: "e", Carrier: "homepage"}).ExpectedIdempotencyKey(); err == nil {
		t.Fatal("missing sourceRevision must fail closed")
	}
	job := dataJob(1)
	job.ExecutionID = ""
	if _, err := job.ExpectedIdempotencyKey(); err == nil {
		t.Fatal("missing executionId must fail closed")
	}
	job = dataJob(1)
	job.IdempotencyKey = "mismatched-key"
	if _, err := job.ValidateIdentity(); err == nil {
		t.Fatal("mismatched declared idempotencyKey must fail closed")
	}
}

func TestDataContentJobIdempotencySeparatesObjectStages(t *testing.T) {
	author := dataJob(1)
	publish := author
	publish.JobID = "job-publish-001"
	publish.Stage = "publish"

	authorKey, err := author.ExpectedIdempotencyKey()
	if err != nil {
		t.Fatal(err)
	}
	publishKey, err := publish.ExpectedIdempotencyKey()
	if err != nil {
		t.Fatal(err)
	}
	if authorKey == publishKey {
		t.Fatalf("author and publish stages share idempotency key %q", authorKey)
	}
	if !strings.HasSuffix(authorKey, "|author") ||
		!strings.HasSuffix(publishKey, "|publish") {
		t.Fatalf("stage missing from idempotency keys: author=%q publish=%q", authorKey, publishKey)
	}
}

func TestDataContentFleetRenewsLeaseWhileObjectWorkerRuns(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	fleet := DataContentFleet{
		Store:       store,
		ExecutionID: dataJob(1).ExecutionID,
		WorkerID:    "worker-long-running",
		LeaseTTL:    30 * time.Millisecond,
	}
	if _, err := fleet.Declare(ctx, dataJob(1)); err != nil {
		t.Fatal(err)
	}
	if _, err := fleet.Dispatch(ctx, 1); err != nil {
		t.Fatal(err)
	}
	started := make(chan struct{})
	release := make(chan struct{})
	result := make(chan error, 1)
	go func() {
		processed, err := fleet.ProcessOne(ctx, func(workerCtx context.Context, _ ReliableAsyncTask) error {
			close(started)
			select {
			case <-release:
				return nil
			case <-workerCtx.Done():
				return workerCtx.Err()
			}
		})
		if !processed && err == nil {
			err = errors.New("long-running task was not processed")
		}
		result <- err
	}()
	<-started
	time.Sleep(75 * time.Millisecond)
	claimed, err := store.ClaimReadyTask(
		ctx,
		[]string{DataContentTaskType},
		"competing-worker",
		30*time.Millisecond,
		time.Now().UTC(),
	)
	if err != nil {
		t.Fatal(err)
	}
	if claimed != nil {
		t.Fatalf("renewed task was reclaimed by competing worker: %s", claimed.TaskID)
	}
	close(release)
	if err := <-result; err != nil {
		t.Fatal(err)
	}
}

func TestDataContentFleetRejectsStaleLeaseFence(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	fleet := DataContentFleet{Store: store, ExecutionID: dataJob(1).ExecutionID}
	if _, err := fleet.Declare(ctx, dataJob(1)); err != nil {
		t.Fatal(err)
	}
	if _, err := fleet.Dispatch(ctx, 1); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	first, err := store.ClaimReadyTask(
		ctx,
		[]string{DataContentTaskType},
		"worker-stale",
		20*time.Millisecond,
		now,
	)
	if err != nil || first == nil {
		t.Fatalf("first claim failed: task=%v err=%v", first, err)
	}
	second, err := store.ClaimReadyTaskByID(
		ctx,
		first.TaskID,
		"worker-current",
		time.Second,
		now.Add(21*time.Millisecond),
	)
	if err != nil || second == nil {
		t.Fatalf("reclaim failed: task=%v err=%v", second, err)
	}
	if second.LeaseToken == first.LeaseToken {
		t.Fatal("reclaim must issue a new fencing token")
	}
	if _, err := store.RenewTaskLease(
		ctx,
		first.TaskID,
		first.LeaseToken,
		time.Second,
		now.Add(22*time.Millisecond),
	); !errors.Is(err, ErrLeaseMismatch) {
		t.Fatalf("stale renewal error=%v want=%v", err, ErrLeaseMismatch)
	}
	if err := store.CompleteTask(ctx, first.TaskID, first.LeaseToken); !errors.Is(err, ErrLeaseMismatch) {
		t.Fatalf("stale completion error=%v want=%v", err, ErrLeaseMismatch)
	}
}

func TestDataContentFleetReconcilesLostReadyIndexFromStoreTruth(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	fleet := DataContentFleet{Store: store, ExecutionID: dataJob(1).ExecutionID}
	if _, err := fleet.Declare(ctx, dataJob(1)); err != nil {
		t.Fatal(err)
	}
	if tasks, err := fleet.Dispatch(ctx, 1); err != nil || len(tasks) != 1 {
		t.Fatalf("dispatch tasks=%d err=%v", len(tasks), err)
	}
	ready := &captureReadyIndex{}
	fleet.Ready = ready
	count, err := fleet.ReconcileReadyIndex(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 || len(ready.tasks) != 1 {
		t.Fatalf("reconciled=%d indexed=%d want=1", count, len(ready.tasks))
	}
	if ready.tasks[0].TaskType != DataContentTaskType {
		t.Fatalf("reconciled task type=%q", ready.tasks[0].TaskType)
	}
}

func TestDataContentFleetScopesDispatchAndReadyRebuildToExecution(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	current := dataJob(1)
	foreign := dataJob(2)
	foreign.ExecutionID = "20260720--travel-homepage-coverage--cn-sichuan--scale-001"
	foreign.JobID = "job-foreign"
	foreign = bindDataJob(foreign)
	ready := &captureReadyIndex{}
	currentFleet := DataContentFleet{
		Store:       store,
		ExecutionID: current.ExecutionID,
		Ready:       ready,
	}
	foreignFleet := DataContentFleet{
		Store:       store,
		ExecutionID: foreign.ExecutionID,
	}
	if _, err := currentFleet.Declare(ctx, current); err != nil {
		t.Fatal(err)
	}
	if _, err := foreignFleet.Declare(ctx, foreign); err != nil {
		t.Fatal(err)
	}
	if tasks, err := currentFleet.Dispatch(ctx, 10); err != nil || len(tasks) != 1 {
		t.Fatalf("current execution dispatch=%d err=%v", len(tasks), err)
	}
	if count, err := currentFleet.ReconcileReadyIndex(ctx, 10); err != nil || count != 1 {
		t.Fatalf("current execution reconcile=%d err=%v", count, err)
	}
	for _, task := range ready.tasks {
		if task.Payload["executionId"] != current.ExecutionID {
			t.Fatalf("ready index leaked foreign execution task: %#v", task.Payload)
		}
	}
	if foreignOutbox := store.outboxByDedupe[foreign.IdempotencyKey]; store.outboxes[foreignOutbox].Status != TaskOutboxStatusPending {
		t.Fatalf("foreign execution outbox status=%s want=%s", store.outboxes[foreignOutbox].Status, TaskOutboxStatusPending)
	}
	if tasks, err := foreignFleet.Dispatch(ctx, 10); err != nil || len(tasks) != 1 {
		t.Fatalf("foreign execution dispatch=%d err=%v", len(tasks), err)
	}
}

func TestDataContentFleetWritesAcceptedObjectTransactionResultBeforeCompletion(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	publishJob := dataPublishJob(1)
	verified := false
	fleet := DataContentFleet{
		Store:       store,
		ExecutionID: publishJob.ExecutionID,
		WorkerID:    "content-object-worker",
		LeaseTTL:    time.Second,
		ResultVerifier: DataContentResultVerifierFunc(func(
			_ context.Context,
			item DataContentWorkItem,
			result DataContentExecutionResult,
		) error {
			verified = item.JobID == publishJob.JobID &&
				result.ObjectTransactionID == "txn-object-001"
			return nil
		}),
	}
	if _, err := fleet.Declare(ctx, publishJob); err != nil {
		t.Fatal(err)
	}
	tasks, err := fleet.Dispatch(ctx, 1)
	if err != nil || len(tasks) != 1 {
		t.Fatalf("dispatch tasks=%d err=%v", len(tasks), err)
	}
	processed, err := fleet.ProcessOneContent(
		ctx,
		DataContentExecutorFunc(func(
			_ context.Context,
			item DataContentWorkItem,
		) (DataContentExecutionResult, error) {
			if item.ExecutionID != publishJob.ExecutionID ||
				item.JobID != publishJob.JobID ||
				item.Ref != publishJob.Ref {
				t.Fatalf("decoded work item drift: %#v", item)
			}
			return DataContentExecutionResult{
				ExecutionID:           item.ExecutionID,
				JobID:                 item.JobID,
				CanonicalObjectRef:    item.Ref,
				CanonicalObjectSHA256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				ObjectTransactionID:   "txn-object-001",
				PoolDeliveryIntentID:  "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
				ResultEnvelopeRef:     "posts/homepage/result_envelope.json",
				AcceptanceClass:       DataContentAcceptanceCommercialCanonical,
				CompletedAt:           time.Now().UTC(),
			}, nil
		}),
	)
	if err != nil || !processed {
		t.Fatalf("process content object processed=%v err=%v", processed, err)
	}
	stored := store.tasks[tasks[0].TaskID]
	if stored.Status != TaskStatusSucceeded {
		t.Fatalf("task status=%s want=%s", stored.Status, TaskStatusSucceeded)
	}
	if !verified {
		t.Fatal("commercial result evidence verifier was not invoked")
	}
	if stored.Result["status"] != "accepted" ||
		stored.Result["objectTransactionId"] != "txn-object-001" ||
		stored.Result["canonicalObjectRef"] != publishJob.Ref {
		t.Fatalf("task result was not transaction-bound: %#v", stored.Result)
	}
}

func TestDataContentFleetRejectsCommercialResultWithoutEvidenceVerifier(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	job := dataPublishJob(1)
	job.MaxAttempts = 1
	fleet := DataContentFleet{
		Store:       store,
		ExecutionID: job.ExecutionID,
		WorkerID:    "content-object-worker",
		Retry:       RetryPolicy{MaxAttempts: 1},
	}
	if _, err := fleet.Declare(ctx, job); err != nil {
		t.Fatal(err)
	}
	tasks, err := fleet.Dispatch(ctx, 1)
	if err != nil || len(tasks) != 1 {
		t.Fatalf("dispatch tasks=%d err=%v", len(tasks), err)
	}
	processed, err := fleet.ProcessOneContent(
		ctx,
		DataContentExecutorFunc(func(
			_ context.Context,
			item DataContentWorkItem,
		) (DataContentExecutionResult, error) {
			return DataContentExecutionResult{
				ExecutionID:           item.ExecutionID,
				JobID:                 item.JobID,
				CanonicalObjectRef:    item.Ref,
				CanonicalObjectSHA256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				ObjectTransactionID:   "txn-unverified",
				PoolDeliveryIntentID:  "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
				ResultEnvelopeRef:     "result_envelope.json",
				AcceptanceClass:       DataContentAcceptanceCommercialCanonical,
				CompletedAt:           time.Now().UTC(),
			}, nil
		}),
	)
	if err != nil || !processed {
		t.Fatalf("process unverified commercial result processed=%v err=%v", processed, err)
	}
	task := store.tasks[tasks[0].TaskID]
	if task.Status != TaskStatusDead ||
		task.LastFailure == nil ||
		!strings.Contains(task.LastFailure.Message, "requires evidence verifier") {
		t.Fatalf("unverified commercial result was not rejected: %#v", task)
	}
}

func TestDataContentFleetRecordsAuthorStageWithoutCommercialAcceptance(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	job := dataJob(1)
	fleet := DataContentFleet{
		Store:       store,
		ExecutionID: job.ExecutionID,
		WorkerID:    "content-author-worker",
		LeaseTTL:    time.Second,
	}
	if _, err := fleet.Declare(ctx, job); err != nil {
		t.Fatal(err)
	}
	tasks, err := fleet.Dispatch(ctx, 1)
	if err != nil || len(tasks) != 1 {
		t.Fatalf("dispatch tasks=%d err=%v", len(tasks), err)
	}
	processed, err := fleet.ProcessOneContent(
		ctx,
		DataContentExecutorFunc(func(
			_ context.Context,
			item DataContentWorkItem,
		) (DataContentExecutionResult, error) {
			return DataContentExecutionResult{
				ExecutionID:       item.ExecutionID,
				JobID:             item.JobID,
				ResultEnvelopeRef: "posts/article/result_envelope.json",
				AcceptanceClass:   DataContentAcceptanceStageCompleted,
				CompletedAt:       time.Now().UTC(),
			}, nil
		}),
	)
	if err != nil || !processed {
		t.Fatalf("process author stage processed=%v err=%v", processed, err)
	}
	stored := store.tasks[tasks[0].TaskID]
	if stored.Result["status"] != "stage_completed" ||
		stored.Result["canonicalObjectRef"] != "" ||
		stored.Result["objectTransactionId"] != "" {
		t.Fatalf("author stage result was misclassified: %#v", stored.Result)
	}
	report := BuildDataContentFleetReport(
		[]ReliableAsyncTask{stored},
		time.Now().UTC().Add(-2*time.Hour),
		time.Now().UTC().Add(-time.Hour),
		time.Now().UTC(),
		0,
		0,
		1,
		0,
	)
	if report.StageCompletedCount != 1 ||
		report.PublishTaskCount != 0 ||
		report.CommercialAcceptedCount != 0 ||
		report.AcceptedContentThroughputStatus != "GATE_BLOCK_NO_COMMERCIAL_BATCH" {
		t.Fatalf("author stage was misreported as commercial: %#v", report)
	}
	if !report.Passed {
		t.Fatalf("author stage quota was met but the batch did not pass: %#v", report)
	}
}

func TestDataContentResultRejectsCommercialAcceptanceBeforePublish(t *testing.T) {
	job := dataJob(1)
	item := DataContentWorkItem{
		JobID:       job.JobID,
		ExecutionID: job.ExecutionID,
		Stage:       job.Stage,
	}
	result := DataContentExecutionResult{
		ExecutionID:           job.ExecutionID,
		JobID:                 job.JobID,
		CanonicalObjectRef:    job.Ref,
		CanonicalObjectSHA256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ObjectTransactionID:   "txn-author-must-not-accept",
		ResultEnvelopeRef:     "result_envelope.json",
		AcceptanceClass:       DataContentAcceptanceCommercialCanonical,
		CompletedAt:           time.Now().UTC(),
	}
	if err := result.validate(item); err == nil ||
		!strings.Contains(err.Error(), "requires publish stage") {
		t.Fatalf("author stage commercial acceptance error=%v", err)
	}
}

func TestDataContentResultAcceptsResearchCanonicalPublishWithoutCommercialCount(t *testing.T) {
	job := dataPublishJob(1)
	item := DataContentWorkItem{
		JobID:       job.JobID,
		ExecutionID: job.ExecutionID,
		Stage:       job.Stage,
	}
	completed := time.Now().UTC()
	result := DataContentExecutionResult{
		ExecutionID:           job.ExecutionID,
		JobID:                 job.JobID,
		CanonicalObjectRef:    job.Ref,
		CanonicalObjectSHA256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ObjectTransactionID:   "txn-research-object-001",
		PoolDeliveryIntentID:  "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		ResultEnvelopeRef:     "result_envelope.json",
		AcceptanceClass:       DataContentAcceptanceResearchCanonical,
		CompletedAt:           completed,
	}
	if err := result.validate(item); err != nil {
		t.Fatalf("research canonical result rejected: %v", err)
	}
	key, err := job.ValidateIdentity()
	if err != nil {
		t.Fatal(err)
	}
	researchTask := ReliableAsyncTask{
		TaskID:  "research-publish",
		Status:  TaskStatusSucceeded,
		Payload: job.payload(key),
		Result:  result.document(),
	}
	report := BuildDataContentFleetReport(
		[]ReliableAsyncTask{researchTask},
		completed.Add(-2*time.Hour),
		completed.Add(-time.Hour),
		completed,
		0,
		0,
		1,
		1,
	)
	if !report.Passed ||
		report.Succeeded != 1 ||
		report.ObjectTransactionResultCount != 1 ||
		report.ResearchAcceptedCount != 1 ||
		report.FinalizedObjectCount != 1 ||
		report.CommercialAcceptedCount != 0 ||
		report.EndToEndAcceptedThroughputPerHour <= 0 {
		t.Fatalf("research canonical report drift: %#v", report)
	}
}

func TestDataContentFleetRejectsControlPlaneOnlySuccess(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	publishJob := dataPublishJob(1)
	publishJob.MaxAttempts = 1
	fleet := DataContentFleet{
		Store:       store,
		ExecutionID: publishJob.ExecutionID,
		WorkerID:    "content-object-worker",
		Retry:       RetryPolicy{MaxAttempts: 1},
	}
	if _, err := fleet.Declare(ctx, publishJob); err != nil {
		t.Fatal(err)
	}
	tasks, err := fleet.Dispatch(ctx, 1)
	if err != nil || len(tasks) != 1 {
		t.Fatalf("dispatch tasks=%d err=%v", len(tasks), err)
	}
	processed, err := fleet.ProcessOneContent(
		ctx,
		DataContentExecutorFunc(func(
			_ context.Context,
			item DataContentWorkItem,
		) (DataContentExecutionResult, error) {
			return DataContentExecutionResult{
				ExecutionID:        item.ExecutionID,
				JobID:              item.JobID,
				CanonicalObjectRef: item.Ref,
				ResultEnvelopeRef:  "result_envelope.json",
				AcceptanceClass:    DataContentAcceptanceCommercialCanonical,
				CompletedAt:        time.Now().UTC(),
			}, nil
		}),
	)
	if err != nil || !processed {
		t.Fatalf("invalid result should be a handled task failure: processed=%v err=%v", processed, err)
	}
	stored := store.tasks[tasks[0].TaskID]
	if stored.Status != TaskStatusDead {
		t.Fatalf("control-plane-only result status=%s want=%s", stored.Status, TaskStatusDead)
	}
	if len(stored.Result) != 0 {
		t.Fatalf("invalid accepted result persisted: %#v", stored.Result)
	}
}

func TestDataContentFleetReportSeparatesAcceptedFromControlPlaneThroughput(t *testing.T) {
	started := time.Now().UTC().Add(-time.Hour)
	completed := time.Now().UTC()
	job := dataJob(1)
	key, err := job.ValidateIdentity()
	if err != nil {
		t.Fatal(err)
	}
	controlOnly := ReliableAsyncTask{
		TaskID:  "control-only",
		Status:  TaskStatusSucceeded,
		Payload: job.payload(key),
	}
	blocked := BuildDataContentFleetReport(
		[]ReliableAsyncTask{controlOnly},
		started,
		started,
		completed,
		0,
		0,
		1,
		0,
	)
	if blocked.CommercialAcceptedCount != 0 ||
		blocked.EndToEndAcceptedThroughputPerHour != 0 ||
		blocked.AcceptedContentThroughputStatus != "GATE_BLOCK_NO_COMMERCIAL_BATCH" {
		t.Fatalf("control-plane completion was misreported as accepted: %#v", blocked)
	}
	fixture := controlOnly
	fixture.Result = DataContentExecutionResult{
		ExecutionID:         dataJob(1).ExecutionID,
		JobID:               dataJob(1).JobID,
		CanonicalObjectRef:  dataJob(1).Ref,
		ObjectTransactionID: "txn-fixture-001",
		ResultEnvelopeRef:   "fixture/result_envelope.json",
		AcceptanceClass:     DataContentAcceptanceContractFixture,
		CompletedAt:         completed,
	}.document()
	fixtureOnly := BuildDataContentFleetReport(
		[]ReliableAsyncTask{fixture},
		started,
		started,
		completed,
		0,
		0,
		1,
		0,
	)
	if fixtureOnly.ObjectTransactionResultCount != 0 ||
		fixtureOnly.CommercialAcceptedCount != 0 ||
		fixtureOnly.EndToEndAcceptedThroughputPerHour != 0 ||
		fixtureOnly.AcceptedContentThroughputStatus != "GATE_BLOCK_NO_COMMERCIAL_BATCH" {
		t.Fatalf("contract fixture was misreported as commercial throughput: %#v", fixtureOnly)
	}
	publishJob := dataPublishJob(1)
	publishKey, err := publishJob.ValidateIdentity()
	if err != nil {
		t.Fatal(err)
	}
	accepted := ReliableAsyncTask{
		TaskID:  "commercial-publish",
		Status:  TaskStatusSucceeded,
		Payload: publishJob.payload(publishKey),
	}
	accepted.Result = DataContentExecutionResult{
		ExecutionID:           publishJob.ExecutionID,
		JobID:                 publishJob.JobID,
		CanonicalObjectRef:    publishJob.Ref,
		CanonicalObjectSHA256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ObjectTransactionID:   "txn-object-001",
		PoolDeliveryIntentID:  "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		ResultEnvelopeRef:     "result_envelope.json",
		AcceptanceClass:       DataContentAcceptanceCommercialCanonical,
		CompletedAt:           completed,
	}.document()
	measured := BuildDataContentFleetReport(
		[]ReliableAsyncTask{accepted},
		started,
		started,
		completed,
		0,
		0,
		1,
		0,
	)
	if !measured.Passed ||
		measured.PublishTaskCount != 1 ||
		measured.ObjectTransactionResultCount != 1 ||
		measured.CommercialAcceptedCount != 1 ||
		measured.EndToEndAcceptedThroughputPerHour <= 0 ||
		measured.AcceptedContentThroughputStatus != "MEASURED" {
		t.Fatalf("accepted object throughput was not measured: %#v", measured)
	}
}

func TestDataContentFleetReportRejectsUnboundOrMalformedCommercialEvidence(t *testing.T) {
	started := time.Now().UTC().Add(-time.Hour)
	completed := time.Now().UTC()
	job := dataPublishJob(1)
	key, err := job.ValidateIdentity()
	if err != nil {
		t.Fatal(err)
	}
	task := ReliableAsyncTask{
		TaskID:  "invalid-commercial-evidence",
		Status:  TaskStatusSucceeded,
		Payload: job.payload(key),
		Result: DataContentExecutionResult{
			ExecutionID:           job.ExecutionID,
			JobID:                 "different-job",
			CanonicalObjectRef:    job.Ref,
			CanonicalObjectSHA256: invalidSHA256Fixture("sha256:not-a-digest"),
			ObjectTransactionID:   "txn-invalid-001",
			PoolDeliveryIntentID:  "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
			ResultEnvelopeRef:     "result_envelope.json",
			AcceptanceClass:       DataContentAcceptanceCommercialCanonical,
			CompletedAt:           completed,
		}.document(),
	}

	report := BuildDataContentFleetReport(
		[]ReliableAsyncTask{task},
		started,
		started,
		completed,
		0,
		0,
		1,
		0,
	)
	if report.Passed ||
		report.ObjectTransactionResultCount != 0 ||
		report.CommercialAcceptedCount != 0 ||
		report.EndToEndAcceptedThroughputPerHour != 0 {
		t.Fatalf("invalid commercial evidence was accepted: %#v", report)
	}
}

func invalidSHA256Fixture(value string) string {
	return value
}
