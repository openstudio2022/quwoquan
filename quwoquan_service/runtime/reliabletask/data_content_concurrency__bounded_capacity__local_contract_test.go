// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-009.t2
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-011.t1
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-011.t2
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-011.t5

package reliabletask

import (
	"context"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// boundedCapacityRun drives workUnitCount object executions through an observed
// executor that admits at most concurrencyCeiling of them at a time. Every unit
// gets its own terminal outcome, and one unit fails so the released slot has to
// be taken by the next pending unit instead of being lost.
type boundedCapacityRun struct {
	peak      int
	completed int
	failed    int
	distinct  int
}

func runBoundedDataContentCapacity(
	t *testing.T,
	workUnitCount int,
	concurrencyCeiling int,
) boundedCapacityRun {
	t.Helper()
	observer := &DataContentConcurrencyObserver{}
	var live atomic.Int64
	var breached atomic.Bool
	var failed atomic.Int64
	var completed atomic.Int64
	arrived := make(chan struct{}, workUnitCount)
	release := make(chan struct{})
	var mutex sync.Mutex
	seen := make(map[string]struct{}, workUnitCount)
	executor := observer.Observe(DataContentExecutorFunc(func(
		_ context.Context,
		item DataContentWorkItem,
	) (DataContentExecutionResult, error) {
		if live.Add(1) > int64(concurrencyCeiling) {
			breached.Store(true)
		}
		defer live.Add(-1)
		mutex.Lock()
		seen[item.JobID] = struct{}{}
		mutex.Unlock()
		arrived <- struct{}{}
		<-release
		// One unit fails so the ceiling is exercised by a released slot rather
		// than by a run where every unit succeeds on its first attempt.
		if strings.HasSuffix(item.JobID, "-000") {
			failed.Add(1)
			return DataContentExecutionResult{}, errors.New("one bounded work unit failed")
		}
		completed.Add(1)
		return DataContentExecutionResult{
			ExecutionID:       item.ExecutionID,
			JobID:             item.JobID,
			ResultEnvelopeRef: "result_envelope.json",
			AcceptanceClass:   DataContentAcceptanceStageCompleted,
			CompletedAt:       time.Now().UTC(),
		}, nil
	}))

	slots := make(chan struct{}, concurrencyCeiling)
	var group sync.WaitGroup
	for index := 0; index < workUnitCount; index++ {
		group.Add(1)
		go func(ordinal int) {
			defer group.Done()
			slots <- struct{}{}
			defer func() { <-slots }()
			job := dataJob(ordinal)
			key, err := job.ValidateIdentity()
			if err != nil {
				t.Error(err)
				return
			}
			item, err := DecodeDataContentWorkItem(ReliableAsyncTask{
				TaskID:         "bounded-task",
				TaskType:       DataContentTaskType,
				AggregateID:    job.EntityRef,
				IdempotencyKey: key,
				PartitionKey:   job.PartitionKey,
				Payload:        job.payload(key),
				LeaseToken:     "bounded-lease",
			})
			if err != nil {
				t.Error(err)
				return
			}
			//nolint:errcheck // the failing unit's error is counted, not asserted here.
			executor.ExecuteDataContentObject(context.Background(), item)
		}(index)
	}

	// Wait until the ceiling is actually saturated before releasing anyone, so
	// the measured peak is the real simultaneous peak rather than a lucky one.
	for waiting := 0; waiting < concurrencyCeiling; waiting++ {
		select {
		case <-arrived:
		case <-time.After(5 * time.Second):
			close(release)
			group.Wait()
			t.Fatalf("only %d of %d slots were occupied", waiting, concurrencyCeiling)
		}
	}
	if observed := observer.Peak(); observed != concurrencyCeiling {
		close(release)
		group.Wait()
		t.Fatalf("saturated peak=%d want=%d", observed, concurrencyCeiling)
	}
	close(release)
	group.Wait()
	if breached.Load() {
		t.Fatalf("more than %d work units ran at the same time", concurrencyCeiling)
	}
	return boundedCapacityRun{
		peak:      observer.Peak(),
		completed: int(completed.Load()),
		failed:    int(failed.Load()),
		distinct:  len(seen),
	}
}

// TestDataContentConcurrencyObserverBoundsPeakWithoutDroppingWorkUnits pins the
// separation of work-unit count from concurrency ceiling: raising the unit count
// only raises the wave count, and no unit is dropped, skipped or merged.
func TestDataContentConcurrencyObserverBoundsPeakWithoutDroppingWorkUnits(t *testing.T) {
	for _, test := range []struct {
		name               string
		workUnitCount      int
		concurrencyCeiling int
		waveCount          int
	}{
		{name: "units_equal_ceiling", workUnitCount: 8, concurrencyCeiling: 8, waveCount: 1},
		{name: "units_above_ceiling", workUnitCount: 24, concurrencyCeiling: 8, waveCount: 3},
		{name: "serial_ceiling", workUnitCount: 5, concurrencyCeiling: 1, waveCount: 5},
	} {
		t.Run(test.name, func(t *testing.T) {
			run := runBoundedDataContentCapacity(
				t,
				test.workUnitCount,
				test.concurrencyCeiling,
			)
			if run.peak != test.concurrencyCeiling {
				t.Fatalf("peak=%d want=%d", run.peak, test.concurrencyCeiling)
			}
			if run.distinct != test.workUnitCount ||
				run.completed+run.failed != test.workUnitCount {
				t.Fatalf(
					"distinct=%d completed=%d failed=%d want %d work units",
					run.distinct, run.completed, run.failed, test.workUnitCount,
				)
			}
			if run.failed != 1 {
				t.Fatalf("failed=%d want exactly one released slot", run.failed)
			}
			expectedWaveCount := (test.workUnitCount + test.concurrencyCeiling - 1) /
				test.concurrencyCeiling
			if expectedWaveCount != test.waveCount {
				t.Fatalf("wave count=%d want=%d", expectedWaveCount, test.waveCount)
			}
		})
	}
}

// TestDataContentFleetReportCarriesMeasuredPeakUnderFrozenCeiling binds the
// measured peak to the frozen wave count and absolute deadline it was measured
// against, which is the only shape in which a peak is reviewable.
func TestDataContentFleetReportCarriesMeasuredPeakUnderFrozenCeiling(t *testing.T) {
	const workUnitCount = 24
	const concurrencyCeiling = 8
	const frozenDeadline = int64(1_893_456_000)
	run := runBoundedDataContentCapacity(t, workUnitCount, concurrencyCeiling)
	completedAt := time.Now().UTC()
	digest := "sha256:" + strings.Repeat("b", 64)
	waveCount := (workUnitCount + concurrencyCeiling - 1) / concurrencyCeiling
	bound, err := BindDataContentFleetReport(
		BuildDataContentFleetReport(
			dataQuotaPublishTasks(workUnitCount, workUnitCount, completedAt),
			completedAt.Add(-2*time.Second),
			completedAt.Add(-time.Second),
			completedAt,
			0,
			0,
			workUnitCount,
			workUnitCount,
			run.peak,
		),
		"20260808--travel-image-m1--china--scale-001",
		"publish",
		digest,
		digest,
		digest,
		waveCount,
		frozenDeadline,
	)
	if err != nil {
		t.Fatal(err)
	}
	if bound.FleetPeakConcurrentWorkers != concurrencyCeiling ||
		bound.FleetPeakConcurrentWorkers > concurrencyCeiling ||
		bound.FleetWaveCount != waveCount ||
		bound.FleetBatchDeadlineEpochSeconds != frozenDeadline {
		t.Fatalf("measured capacity binding drift: %#v", bound)
	}
}

// TestDataContentFleetReportCapacityObservationsDoNotChangeOutcomes keeps the
// concurrency, wave and time observations descriptive: the same object evidence
// must produce the same admission verdict no matter how many workers ran.
func TestDataContentFleetReportCapacityObservationsDoNotChangeOutcomes(t *testing.T) {
	const workUnitCount = 4
	completedAt := time.Now().UTC()
	tasks := dataQuotaPublishTasks(workUnitCount, workUnitCount, completedAt)
	build := func(peak int) DataContentFleetReport {
		return BuildDataContentFleetReport(
			tasks,
			completedAt.Add(-2*time.Second),
			completedAt.Add(-time.Second),
			completedAt,
			0,
			0,
			workUnitCount,
			workUnitCount,
			peak,
		)
	}
	serial := build(1)
	saturated := build(workUnitCount)
	if serial.Passed != saturated.Passed ||
		serial.Succeeded != saturated.Succeeded ||
		serial.ResearchAcceptedCount != saturated.ResearchAcceptedCount ||
		serial.ObjectTransactionResultCount != saturated.ObjectTransactionResultCount ||
		serial.AcceptedContentThroughputStatus != saturated.AcceptedContentThroughputStatus {
		t.Fatalf(
			"peak observation changed the admission verdict: serial=%#v saturated=%#v",
			serial,
			saturated,
		)
	}
	if serial.FleetPeakConcurrentWorkers == saturated.FleetPeakConcurrentWorkers {
		t.Fatal("peak observation was not recorded per run")
	}
}
