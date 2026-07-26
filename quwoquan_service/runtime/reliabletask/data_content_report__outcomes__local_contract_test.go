package reliabletask

import (
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
		completedAt.Add(-time.Second),
		completedAt,
		0,
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
