package reliabletask

import (
	"encoding/hex"
	"strings"
	"time"
)

type DataContentFleetReport struct {
	Schema                            string  `json:"schema"`
	Passed                            bool    `json:"passed"`
	Backend                           string  `json:"backend"`
	Total                             int     `json:"total"`
	Succeeded                         int     `json:"succeeded"`
	StageCompletedCount               int     `json:"stageCompletedCount"`
	PublishTaskCount                  int     `json:"publishTaskCount"`
	ObjectTransactionResultCount      int     `json:"objectTransactionResultCount"`
	CommercialAcceptedCount           int     `json:"commercialAcceptedCount"`
	ControlPlaneTaskThroughputPerHour float64 `json:"controlPlaneTaskThroughputPerHour"`
	AcceptedContentThroughputPerHour  float64 `json:"acceptedContentThroughputPerHour"`
	AcceptedContentThroughputStatus   string  `json:"acceptedContentThroughputStatus"`
	AutomaticRecoveryRate             float64 `json:"automaticRecoveryRate"`
	FinalizedWithinStageBudgetRate    float64 `json:"finalizedWithinStageBudgetRate"`
	DuplicatePublishCount             int     `json:"duplicatePublishCount"`
	MissingObjectCount                int     `json:"missingObjectCount"`
	IdempotencyKey                    string  `json:"idempotencyKey"`
	CompletedAt                       string  `json:"completedAt"`
}

func BuildDataContentFleetReport(
	tasks []ReliableAsyncTask,
	startedAt time.Time,
	completedAt time.Time,
	duplicatePublishCount int,
	missingObjectCount int,
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
	}
	total := len(tasks)
	finalizedRate := 0.0
	recoveryRate := 0.0
	if total > 0 {
		finalizedRate = float64(succeeded) / float64(total)
		recoveryRate = finalizedRate
	}
	acceptedStatus := "GATE_BLOCK_NO_COMMERCIAL_BATCH"
	if publishTasks > 0 && commercialAccepted == publishTasks {
		acceptedStatus = "MEASURED"
	} else if publishTasks > 0 {
		acceptedStatus = "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
	}
	return DataContentFleetReport{
		Schema:                            "quwoquan.reliabletask_fleet_report",
		Passed:                            total > 0 && publishTasks > 0 && commercialAccepted == publishTasks && succeeded == total && duplicatePublishCount == 0 && missingObjectCount == 0,
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
		IdempotencyKey:                    "executionId+entity+carrier+sourceRevision+stage",
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
