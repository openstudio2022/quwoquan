package reliabletask

import (
	"fmt"
	"testing"
	"time"
)

func TestDataContentFleetReportCarriesOneOutcomePerFrozenJob(t *testing.T) {
	completedAt := time.Now().UTC()
	report := BuildDataContentFleetReport(
		[]ReliableAsyncTask{
			{
				TaskID:   "task-succeeded",
				Status:   TaskStatusSucceeded,
				Attempts: 1,
				Payload:  map[string]string{"jobId": "job-succeeded"},
			},
			{
				TaskID:   "task-dead",
				Status:   TaskStatusDead,
				Attempts: 2,
				Payload:  map[string]string{"jobId": "job-dead"},
				LastFailure: &RuntimeFailure{
					Code: "reliabletask.executor_failed",
				},
			},
		},
		completedAt.Add(-2*time.Second),
		completedAt.Add(-time.Second),
		completedAt,
		0,
		0,
		1,
		0,
	)
	if len(report.TaskOutcomes) != 2 {
		t.Fatalf("task outcomes=%d want=2", len(report.TaskOutcomes))
	}
	if got := report.TaskOutcomes[0]; got.JobID != "job-succeeded" ||
		got.Status != TaskStatusSucceeded || got.Attempts != 1 || got.FailureCode != "" {
		t.Fatalf("success outcome=%#v", got)
	}
	if got := report.TaskOutcomes[1]; got.JobID != "job-dead" ||
		got.Status != TaskStatusDead || got.Attempts != 2 ||
		got.FailureCode != "reliabletask.executor_failed" {
		t.Fatalf("dead outcome=%#v", got)
	}
}

// dataQuotaPublishTasks 造一批 publish 任务：前 accepted 个是商用可接受终态，
// 其余是被丢弃的 dead 对象，用来表达"过采 + 配额"的批次形态。
func dataQuotaPublishTasks(total int, accepted int, completed time.Time) []ReliableAsyncTask {
	tasks := make([]ReliableAsyncTask, 0, total)
	for index := 0; index < total; index++ {
		job := dataPublishJob(index)
		key, err := job.ValidateIdentity()
		if err != nil {
			panic(err)
		}
		task := ReliableAsyncTask{
			TaskID:   fmt.Sprintf("publish-task-%03d", index),
			Status:   TaskStatusDead,
			Attempts: 1,
			Payload:  job.payload(key),
		}
		if index < accepted {
			task.Status = TaskStatusSucceeded
			task.Result = DataContentExecutionResult{
				ExecutionID:           job.ExecutionID,
				JobID:                 job.JobID,
				CanonicalObjectRef:    job.Ref,
				CanonicalObjectSHA256: "sha256:" + fmt.Sprintf("%064d", index+1),
				ObjectTransactionID:   fmt.Sprintf("txn-object-%03d", index),
				ResultEnvelopeRef:     "result_envelope.json",
				AcceptanceClass:       DataContentAcceptanceCommercialCanonical,
				CompletedAt:           completed,
			}.document()
		}
		tasks = append(tasks, task)
	}
	return tasks
}

func TestDataContentFleetReportPassesPublishQuotaWithoutFullBatchSuccess(t *testing.T) {
	started := time.Now().UTC().Add(-time.Hour)
	completed := time.Now().UTC()

	report := BuildDataContentFleetReport(
		dataQuotaPublishTasks(10, 8, completed),
		started,
		started,
		completed,
		0,
		0,
		7,
		73,
	)

	if !report.Passed {
		t.Fatalf("publish quota was met but the batch was blocked: %#v", report)
	}
	if report.AcceptedContentThroughputStatus != "MEASURED" {
		t.Fatalf("accepted throughput status=%q want=MEASURED", report.AcceptedContentThroughputStatus)
	}
	if report.CommercialAcceptedCount != 8 ||
		report.Succeeded != 8 ||
		report.Total != 10 ||
		report.RequiredQuota != 7 ||
		report.FinalizedObjectCount != 73 {
		t.Fatalf("quota report drift: %#v", report)
	}
}

func TestDataContentFleetReportBlocksPublishBatchBelowQuota(t *testing.T) {
	started := time.Now().UTC().Add(-time.Hour)
	completed := time.Now().UTC()

	report := BuildDataContentFleetReport(
		dataQuotaPublishTasks(10, 5, completed),
		started,
		started,
		completed,
		0,
		0,
		7,
		5,
	)

	if report.Passed {
		t.Fatalf("publish batch below quota must not pass: %#v", report)
	}
	if report.AcceptedContentThroughputStatus != "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH" {
		t.Fatalf(
			"accepted throughput status=%q want=GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH",
			report.AcceptedContentThroughputStatus,
		)
	}
}

func TestDataContentFleetReportAcceptsIdempotentFinalizedObjectsTowardQuota(t *testing.T) {
	started := time.Now().UTC().Add(-time.Hour)
	completed := time.Now().UTC()

	// Resume after objects already sit in canonical publish: jobs may be dead
	// while finalizedObjectCount still meets the commercial quota.
	report := BuildDataContentFleetReport(
		dataQuotaPublishTasks(5, 0, completed),
		started,
		started,
		completed,
		0,
		0,
		3,
		5,
	)

	if !report.Passed {
		t.Fatalf("idempotent finalized objects must meet publish quota: %#v", report)
	}
	if report.AcceptedContentThroughputStatus != "MEASURED" {
		t.Fatalf(
			"accepted throughput status=%q want=MEASURED",
			report.AcceptedContentThroughputStatus,
		)
	}
	if report.CommercialAcceptedCount != 0 || report.FinalizedObjectCount != 5 {
		t.Fatalf("idempotent quota report drift: %#v", report)
	}
}

func TestDataContentFleetReportGatesPublishQuotaOnDuplicateAndMissingObjects(t *testing.T) {
	started := time.Now().UTC().Add(-time.Hour)
	completed := time.Now().UTC()

	duplicated := BuildDataContentFleetReport(
		dataQuotaPublishTasks(10, 8, completed), started, started, completed, 1, 0, 7, 8,
	)
	missing := BuildDataContentFleetReport(
		dataQuotaPublishTasks(10, 8, completed), started, started, completed, 0, 1, 7, 8,
	)

	if duplicated.Passed || missing.Passed {
		t.Fatalf(
			"quota gate ignored batch integrity: duplicated=%#v missing=%#v",
			duplicated,
			missing,
		)
	}
}

func TestDataContentFleetReportAppliesQuotaToAuthorBatch(t *testing.T) {
	started := time.Now().UTC().Add(-time.Hour)
	completed := time.Now().UTC()
	authorTasks := func(total int, succeeded int) []ReliableAsyncTask {
		tasks := make([]ReliableAsyncTask, 0, total)
		for index := 0; index < total; index++ {
			job := dataJob(index)
			key, err := job.ValidateIdentity()
			if err != nil {
				t.Fatal(err)
			}
			status := TaskStatusDead
			if index < succeeded {
				status = TaskStatusSucceeded
			}
			tasks = append(tasks, ReliableAsyncTask{
				TaskID:  fmt.Sprintf("author-task-%03d", index),
				Status:  status,
				Payload: job.payload(key),
			})
		}
		return tasks
	}

	met := BuildDataContentFleetReport(authorTasks(10, 8), started, started, completed, 0, 0, 7, 8)
	unmet := BuildDataContentFleetReport(authorTasks(10, 5), started, started, completed, 0, 0, 7, 5)

	if !met.Passed {
		t.Fatalf("author quota was met but the batch was blocked: %#v", met)
	}
	if unmet.Passed {
		t.Fatalf("author batch below quota must not pass: %#v", unmet)
	}
	for _, report := range []DataContentFleetReport{met, unmet} {
		if report.PublishTaskCount != 0 ||
			report.AcceptedContentThroughputStatus != "GATE_BLOCK_NO_COMMERCIAL_BATCH" {
			t.Fatalf("author batch commercial status drift: %#v", report)
		}
	}
}

func TestDataContentFleetReportSeparatesEndToEndFromFleetWallClock(t *testing.T) {
	executionCreatedAt := time.Date(2026, 7, 27, 0, 0, 0, 0, time.UTC)
	fleetStartedAt := executionCreatedAt.Add(3 * time.Hour)
	canonicalFinalizedAt := fleetStartedAt.Add(time.Hour)

	report := BuildDataContentFleetReport(
		dataQuotaPublishTasks(8, 8, canonicalFinalizedAt),
		executionCreatedAt,
		fleetStartedAt,
		canonicalFinalizedAt,
		0,
		0,
		8,
		8,
	)

	if report.FleetWallClockMilliseconds != int64(time.Hour/time.Millisecond) ||
		report.EndToEndWallClockMilliseconds != int64(4*time.Hour/time.Millisecond) {
		t.Fatalf("wall-clock windows drift: %#v", report)
	}
	if report.FleetAcceptedThroughputPerHour != 8 ||
		report.EndToEndAcceptedThroughputPerHour != 2 {
		t.Fatalf("fleet/e2e throughput was not separated: %#v", report)
	}
	if report.CanonicalFinalizedAt == nil ||
		*report.CanonicalFinalizedAt != canonicalFinalizedAt.Format(time.RFC3339Nano) {
		t.Fatalf("canonical finalize timestamp drift: %#v", report)
	}
}
