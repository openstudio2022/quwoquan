package reliabletask

import (
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

type DataContentFleetReport struct {
	Schema                             string                   `json:"schema"`
	ExecutionID                        string                   `json:"executionId"`
	Stage                              string                   `json:"stage"`
	JobSetEnvelopeDigest               string                   `json:"jobSetEnvelopeDigest"`
	JobSetDigest                       string                   `json:"jobSetDigest"`
	ActualTaskDigest                   string                   `json:"actualTaskDigest"`
	Passed                             bool                     `json:"passed"`
	Backend                            string                   `json:"backend"`
	Total                              int                      `json:"total"`
	Succeeded                          int                      `json:"succeeded"`
	StageCompletedCount                int                      `json:"stageCompletedCount"`
	PublishTaskCount                   int                      `json:"publishTaskCount"`
	ObjectTransactionResultCount       int                      `json:"objectTransactionResultCount"`
	ResearchAcceptedCount              int                      `json:"researchAcceptedCount"`
	CommercialAcceptedCount            int                      `json:"commercialAcceptedCount"`
	FleetControlPlaneThroughputPerHour float64                  `json:"fleetControlPlaneThroughputPerHour"`
	FleetAcceptedThroughputPerHour     float64                  `json:"fleetAcceptedThroughputPerHour"`
	EndToEndAcceptedThroughputPerHour  float64                  `json:"endToEndAcceptedThroughputPerHour"`
	AcceptedContentThroughputStatus    string                   `json:"acceptedContentThroughputStatus"`
	RecoveryEligibleCount              int                      `json:"recoveryEligibleCount"`
	AutomaticRecoveredCount            int                      `json:"automaticRecoveredCount"`
	ManualRecoveredCount               int                      `json:"manualRecoveredCount"`
	AutomaticRecoveryStatus            string                   `json:"automaticRecoveryStatus"`
	AutomaticRecoveryRate              float64                  `json:"automaticRecoveryRate"`
	FirstAttemptSuccessRate            float64                  `json:"firstAttemptSuccessRate"`
	FinalizedWithinStageBudgetRate     float64                  `json:"finalizedWithinStageBudgetRate"`
	DuplicatePublishCount              int                      `json:"duplicatePublishCount"`
	MissingObjectCount                 int                      `json:"missingObjectCount"`
	RequiredQuota                      int                      `json:"requiredQuota"`
	FinalizedObjectCount               int                      `json:"finalizedObjectCount"`
	IdempotencyKey                     string                   `json:"idempotencyKey"`
	FleetPeakConcurrentWorkers         int                      `json:"fleetPeakConcurrentWorkers"`
	FleetWaveCount                     int                      `json:"fleetWaveCount,omitempty"`
	FleetBatchDeadlineEpochSeconds     int64                    `json:"fleetBatchDeadlineEpochSeconds,omitempty"`
	TaskOutcomes                       []DataContentTaskOutcome `json:"taskOutcomes"`
	ExecutionCreatedAt                 string                   `json:"executionCreatedAt"`
	FleetStartedAt                     string                   `json:"fleetStartedAt"`
	CanonicalFinalizedAt               *string                  `json:"canonicalFinalizedAt"`
	FleetWallClockMilliseconds         int64                    `json:"fleetWallClockMilliseconds"`
	EndToEndWallClockMilliseconds      int64                    `json:"endToEndWallClockMilliseconds"`
	CompletedAt                        string                   `json:"completedAt"`
}

// BindDataContentFleetReport binds one measured run to the exact attempt that
// froze it. fleetWaveCount and fleetBatchDeadlineEpochSeconds come from the
// frozen execution policy rather than from this run, so a report that cannot
// name both is not a report at all: reliabletask_fleet_report.schema.json
// validates them whenever they are carried, and a run may not publish a peak
// without the frozen cap and deadline it was measured against.
func BindDataContentFleetReport(
	report DataContentFleetReport,
	executionID string,
	stage string,
	jobSetEnvelopeDigest string,
	jobSetDigest string,
	actualTaskDigest string,
	fleetWaveCount int,
	fleetBatchDeadlineEpochSeconds int64,
) (DataContentFleetReport, error) {
	if strings.TrimSpace(executionID) == "" ||
		(strings.TrimSpace(stage) != "author" && strings.TrimSpace(stage) != "publish") ||
		!validSHA256Digest(jobSetEnvelopeDigest) ||
		!validSHA256Digest(jobSetDigest) ||
		!validSHA256Digest(actualTaskDigest) {
		return DataContentFleetReport{}, fmt.Errorf(
			"data content fleet report attempt binding is invalid",
		)
	}
	if fleetWaveCount < 1 {
		return DataContentFleetReport{}, fmt.Errorf(
			"data content fleet report fleetWaveCount=%d is not a frozen wave count",
			fleetWaveCount,
		)
	}
	if fleetBatchDeadlineEpochSeconds < 1 {
		return DataContentFleetReport{}, fmt.Errorf(
			"data content fleet report fleetBatchDeadlineEpochSeconds=%d is not a frozen absolute deadline",
			fleetBatchDeadlineEpochSeconds,
		)
	}
	report.ExecutionID = strings.TrimSpace(executionID)
	report.Stage = strings.TrimSpace(stage)
	report.JobSetEnvelopeDigest = strings.TrimSpace(jobSetEnvelopeDigest)
	report.JobSetDigest = strings.TrimSpace(jobSetDigest)
	report.ActualTaskDigest = strings.TrimSpace(actualTaskDigest)
	report.FleetWaveCount = fleetWaveCount
	report.FleetBatchDeadlineEpochSeconds = fleetBatchDeadlineEpochSeconds
	return report, nil
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
// batch passes once lifecycle-accepted canonical objects reach requiredQuota, an
// author batch once succeeded tasks reach it. Objects below the quota line are
// discarded by the caller, so a batch is oversampled instead of retried.
// finalizedObjectCount is an observation of on-disk finished objects and never
// participates in the gate, and neither does peakConcurrentWorkers: the latter
// is the measured process peak of this run, taken from
// DataContentConcurrencyObserver, and is a required caller input so an
// unobserved run cannot silently report a peak of zero.
func BuildDataContentFleetReport(
	tasks []ReliableAsyncTask,
	executionCreatedAt time.Time,
	startedAt time.Time,
	completedAt time.Time,
	duplicatePublishCount int,
	missingObjectCount int,
	requiredQuota int,
	finalizedObjectCount int,
	peakConcurrentWorkers int,
) DataContentFleetReport {
	if completedAt.Before(startedAt) {
		completedAt = startedAt
	}
	fleetElapsed := completedAt.Sub(startedAt)
	fleetElapsedHours := fleetElapsed.Hours()
	if fleetElapsedHours <= 0 {
		fleetElapsedHours = time.Nanosecond.Hours()
	}
	succeeded := 0
	stageCompleted := 0
	publishTasks := 0
	transactionResults := 0
	researchAccepted := 0
	// reliabletask_fleet_report.schema.json requires commercialAcceptedCount,
	// but no acceptance class in data_content_worker_response.schema.json means
	// commercial acceptance, so no batch can raise this above zero today.
	commercialAccepted := 0
	recoveryEligible := 0
	automaticRecovered := 0
	manualRecovered := 0
	firstAttemptSucceeded := 0
	var canonicalFinalizedAt time.Time
	outcomes := make([]DataContentTaskOutcome, 0, len(tasks))
	for _, task := range tasks {
		if task.Payload["stage"] == "publish" {
			publishTasks++
		}
		if task.Status == TaskStatusSucceeded {
			succeeded++
			if task.Attempts <= 1 {
				firstAttemptSucceeded++
			}
		}
		if task.Attempts > 1 || task.LastFailure != nil {
			recoveryEligible++
			if task.Status == TaskStatusSucceeded {
				if strings.TrimSpace(task.Result["recoveryMode"]) == "manual" {
					manualRecovered++
				} else {
					automaticRecovered++
				}
			}
		}
		if task.Status == TaskStatusSucceeded && dataContentResultStageCompleted(task) {
			stageCompleted++
		}
		if task.Status == TaskStatusSucceeded && dataContentObjectTransactionResultRecorded(task) {
			transactionResults++
		}
		if task.Status == TaskStatusSucceeded && dataContentResultResearchAccepted(task) {
			acceptedAt, err := time.Parse(time.RFC3339Nano, task.Result["completedAt"])
			if err == nil &&
				!executionCreatedAt.IsZero() &&
				acceptedAt.After(executionCreatedAt) {
				researchAccepted++
				if canonicalFinalizedAt.IsZero() || acceptedAt.After(canonicalFinalizedAt) {
					canonicalFinalizedAt = acceptedAt
				}
			}
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
	firstAttemptSuccessRate := 0.0
	recoveryStatus := "NOT_EXERCISED"
	if total > 0 {
		finalizedRate = float64(succeeded) / float64(total)
		firstAttemptSuccessRate = float64(firstAttemptSucceeded) / float64(total)
	}
	if recoveryEligible > 0 {
		recoveryRate = float64(automaticRecovered) / float64(recoveryEligible)
		recoveryStatus = "MEASURED"
	}
	canonicalAccepted := researchAccepted + commercialAccepted
	quotaMet := canonicalAccepted >= requiredQuota
	acceptedStatus := "GATE_BLOCK_NO_COMMERCIAL_BATCH"
	if publishTasks > 0 && quotaMet {
		acceptedStatus = "MEASURED"
	} else if publishTasks > 0 {
		acceptedStatus = "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
	}
	passed := false
	if total > 0 && publishTasks > 0 {
		passed = quotaMet &&
			duplicatePublishCount == 0 &&
			missingObjectCount == 0
	} else if total > 0 {
		passed = succeeded >= requiredQuota && missingObjectCount == 0
	}
	fleetAcceptedThroughput := float64(canonicalAccepted) / fleetElapsedHours
	endToEndAcceptedThroughput := 0.0
	endToEndWallClock := time.Duration(0)
	var canonicalFinalizedAtText *string
	if !canonicalFinalizedAt.IsZero() {
		endToEndWallClock = canonicalFinalizedAt.Sub(executionCreatedAt)
		endToEndHours := endToEndWallClock.Hours()
		if endToEndHours > 0 {
			endToEndAcceptedThroughput = float64(canonicalAccepted) / endToEndHours
		}
		value := canonicalFinalizedAt.UTC().Format(time.RFC3339Nano)
		canonicalFinalizedAtText = &value
	}
	return DataContentFleetReport{
		Schema:                             "quwoquan.reliabletask_fleet_report",
		Passed:                             passed,
		Backend:                            "mongodb+redis",
		Total:                              total,
		Succeeded:                          succeeded,
		StageCompletedCount:                stageCompleted,
		PublishTaskCount:                   publishTasks,
		ObjectTransactionResultCount:       transactionResults,
		ResearchAcceptedCount:              researchAccepted,
		CommercialAcceptedCount:            commercialAccepted,
		FleetControlPlaneThroughputPerHour: float64(succeeded) / fleetElapsedHours,
		FleetAcceptedThroughputPerHour:     fleetAcceptedThroughput,
		EndToEndAcceptedThroughputPerHour:  endToEndAcceptedThroughput,
		AcceptedContentThroughputStatus:    acceptedStatus,
		RecoveryEligibleCount:              recoveryEligible,
		AutomaticRecoveredCount:            automaticRecovered,
		ManualRecoveredCount:               manualRecovered,
		AutomaticRecoveryStatus:            recoveryStatus,
		AutomaticRecoveryRate:              recoveryRate,
		FirstAttemptSuccessRate:            firstAttemptSuccessRate,
		FinalizedWithinStageBudgetRate:     finalizedRate,
		DuplicatePublishCount:              duplicatePublishCount,
		MissingObjectCount:                 missingObjectCount,
		RequiredQuota:                      requiredQuota,
		FinalizedObjectCount:               finalizedObjectCount,
		IdempotencyKey:                     "executionId+entity+carrier+sourceRevision+stage",
		FleetPeakConcurrentWorkers:         peakConcurrentWorkers,
		TaskOutcomes:                       outcomes,
		ExecutionCreatedAt:                 executionCreatedAt.UTC().Format(time.RFC3339Nano),
		FleetStartedAt:                     startedAt.UTC().Format(time.RFC3339Nano),
		CanonicalFinalizedAt:               canonicalFinalizedAtText,
		FleetWallClockMilliseconds:         fleetElapsed.Milliseconds(),
		EndToEndWallClockMilliseconds:      endToEndWallClock.Milliseconds(),
		CompletedAt:                        completedAt.UTC().Format(time.RFC3339Nano),
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

func dataContentResultResearchAccepted(task ReliableAsyncTask) bool {
	result := task.Result
	return dataContentObjectTransactionResultRecorded(task) &&
		result["status"] == "accepted" &&
		result["acceptanceClass"] == DataContentAcceptanceCanonicalPool &&
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
