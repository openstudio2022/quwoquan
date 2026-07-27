package reliabletask

import (
	"encoding/hex"
	"strings"
	"time"
)

type DataContentFleetReport struct {
	Schema                            string                   `json:"schema"`
	Passed                            bool                     `json:"passed"`
	Backend                           string                   `json:"backend"`
	Total                             int                      `json:"total"`
	Succeeded                         int                      `json:"succeeded"`
	StageCompletedCount               int                      `json:"stageCompletedCount"`
	PublishTaskCount                  int                      `json:"publishTaskCount"`
	ObjectTransactionResultCount      int                      `json:"objectTransactionResultCount"`
	CommercialAcceptedCount           int                      `json:"commercialAcceptedCount"`
	ControlPlaneTaskThroughputPerHour float64                  `json:"controlPlaneTaskThroughputPerHour"`
	AcceptedContentThroughputPerHour  float64                  `json:"acceptedContentThroughputPerHour"`
	AcceptedContentThroughputStatus   string                   `json:"acceptedContentThroughputStatus"`
	AutomaticRecoveryRate             float64                  `json:"automaticRecoveryRate"`
	FinalizedWithinStageBudgetRate    float64                  `json:"finalizedWithinStageBudgetRate"`
	DuplicatePublishCount             int                      `json:"duplicatePublishCount"`
	MissingObjectCount                int                      `json:"missingObjectCount"`
	RequiredQuota                     int                      `json:"requiredQuota"`
	FinalizedObjectCount              int                      `json:"finalizedObjectCount"`
	IdempotencyKey                    string                   `json:"idempotencyKey"`
	TaskOutcomes                      []DataContentTaskOutcome `json:"taskOutcomes"`
	CompletedAt                       string                   `json:"completedAt"`
}

// DataContentTaskOutcome is the minimal service-owned completion receipt for
// one frozen Data job. Detailed failure text remains in ReliableTask storage;
// only its stable classification crosses the Data service boundary.
type DataContentTaskOutcome struct {
	JobID       string `json:"jobId"`
	Status      string `json:"status"`
	Attempts    int    `json:"attempts"`
	FailureCode string `json:"failureCode,omitempty"`
}

// BuildDataContentFleetReport projects one batch onto a quota gate: a publish
// batch passes once commercially accepted objects reach requiredQuota, an
// author batch once succeeded tasks reach it. Objects below the quota line are
// discarded by the caller, so a batch is oversampled instead of retried.
// finalizedObjectCount is an observation of on-disk finished objects and never
// participates in the gate.
func BuildDataContentFleetReport(
	tasks []ReliableAsyncTask,
	startedAt time.Time,
	completedAt time.Time,
	duplicatePublishCount int,
	missingObjectCount int,
	requiredQuota int,
	finalizedObjectCount int,
) DataContentFleetReport {
	if completedAt.Before(startedAt) {
		completedAt = startedAt
	}
	elapsedHours := completedAt.Sub(startedAt).Hours()
	if elapsedHours <= 0 {
		elapsedHours = time.Nanosecond.Hours()
	}
	succeeded := 0
	stageCompleted := 0
	publishTasks := 0
	transactionResults := 0
	commercialAccepted := 0
	outcomes := make([]DataContentTaskOutcome, 0, len(tasks))
	for _, task := range tasks {
		if task.Payload["stage"] == "publish" {
			publishTasks++
		}
		if task.Status == TaskStatusSucceeded {
			succeeded++
		}
		if task.Status == TaskStatusSucceeded && dataContentResultStageCompleted(task) {
			stageCompleted++
		}
		if task.Status == TaskStatusSucceeded && dataContentObjectTransactionResultRecorded(task) {
			transactionResults++
		}
		if task.Status == TaskStatusSucceeded && dataContentResultCommerciallyAccepted(task) {
			commercialAccepted++
		}
		failureCode := ""
		if task.LastFailure != nil {
			failureCode = strings.TrimSpace(task.LastFailure.Code)
		}
		outcomes = append(outcomes, DataContentTaskOutcome{
			JobID:       task.Payload["jobId"],
			Status:      task.Status,
			Attempts:    task.Attempts,
			FailureCode: failureCode,
		})
	}
	total := len(tasks)
	finalizedRate := 0.0
	recoveryRate := 0.0
	if total > 0 {
		finalizedRate = float64(succeeded) / float64(total)
		recoveryRate = finalizedRate
	}
	acceptedStatus := "GATE_BLOCK_NO_COMMERCIAL_BATCH"
	if publishTasks > 0 && commercialAccepted >= requiredQuota {
		acceptedStatus = "MEASURED"
	} else if publishTasks > 0 {
		acceptedStatus = "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
	}
	passed := false
	if total > 0 && publishTasks > 0 {
		passed = commercialAccepted >= requiredQuota &&
			duplicatePublishCount == 0 &&
			missingObjectCount == 0
	} else if total > 0 {
		passed = succeeded >= requiredQuota && missingObjectCount == 0
	}
	return DataContentFleetReport{
		Schema:                            "quwoquan.reliabletask_fleet_report",
		Passed:                            passed,
		Backend:                           "mongodb+redis",
		Total:                             total,
		Succeeded:                         succeeded,
		StageCompletedCount:               stageCompleted,
		PublishTaskCount:                  publishTasks,
		ObjectTransactionResultCount:      transactionResults,
		CommercialAcceptedCount:           commercialAccepted,
		ControlPlaneTaskThroughputPerHour: float64(succeeded) / elapsedHours,
		AcceptedContentThroughputPerHour:  float64(commercialAccepted) / elapsedHours,
		AcceptedContentThroughputStatus:   acceptedStatus,
		AutomaticRecoveryRate:             recoveryRate,
		FinalizedWithinStageBudgetRate:    finalizedRate,
		DuplicatePublishCount:             duplicatePublishCount,
		MissingObjectCount:                missingObjectCount,
		RequiredQuota:                     requiredQuota,
		FinalizedObjectCount:              finalizedObjectCount,
		IdempotencyKey:                    "executionId+entity+carrier+sourceRevision+stage",
		TaskOutcomes:                      outcomes,
		CompletedAt:                       completedAt.UTC().Format(time.RFC3339Nano),
	}
}

func dataContentResultRecorded(task ReliableAsyncTask) bool {
	result := task.Result
	_, completedAtErr := time.Parse(time.RFC3339Nano, result["completedAt"])
	return result["schema"] == dataContentResultSchema &&
		result["executionId"] != "" &&
		result["executionId"] == task.Payload["executionId"] &&
		result["jobId"] != "" &&
		result["jobId"] == task.Payload["jobId"] &&
		result["resultEnvelopeRef"] != "" &&
		result["acceptanceClass"] != "" &&
		completedAtErr == nil
}

func dataContentResultStageCompleted(task ReliableAsyncTask) bool {
	result := task.Result
	return dataContentResultRecorded(task) &&
		result["status"] == "stage_completed" &&
		result["acceptanceClass"] == DataContentAcceptanceStageCompleted &&
		task.Payload["stage"] != "publish"
}

func dataContentObjectTransactionResultRecorded(task ReliableAsyncTask) bool {
	result := task.Result
	return dataContentResultRecorded(task) &&
		task.Payload["stage"] == "publish" &&
		result["canonicalObjectRef"] != "" &&
		result["objectTransactionId"] != ""
}

func dataContentResultCommerciallyAccepted(task ReliableAsyncTask) bool {
	result := task.Result
	return dataContentObjectTransactionResultRecorded(task) &&
		result["status"] == "accepted" &&
		result["acceptanceClass"] == DataContentAcceptanceCommercialCanonical &&
		validDataContentSHA256(result["canonicalObjectSha256"])
}

func validDataContentSHA256(value string) bool {
	raw := strings.TrimPrefix(strings.TrimSpace(value), "sha256:")
	if !strings.HasPrefix(strings.TrimSpace(value), "sha256:") || len(raw) != 64 {
		return false
	}
	_, err := hex.DecodeString(raw)
	return err == nil
}
