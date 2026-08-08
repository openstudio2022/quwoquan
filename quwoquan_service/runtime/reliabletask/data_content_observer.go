package reliabletask

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	DataContentExecutionObservationSchema  = "quwoquan.reliabletask_execution_observation"
	dataContentExecutionObservationVersion = 3
	dataContentObserverTaskLimit           = int64(100_000)
)

type DataContentExecutionObservationRequest struct {
	ExecutionID             string
	Carrier                 string
	Stage                   string
	RequestBindingDigest    string
	ExecutionEnvelopeDigest string
	JobSetEnvelopeDigest    string
	JobSetDigest            string
	ActualTaskDigest        string
	Campaign                DataContentCampaignBinding
}

type DataContentExecutionObservationTask struct {
	JobID          string `json:"jobId"`
	EntityRef      string `json:"entityRef"`
	Stage          string `json:"stage"`
	SourceRevision string `json:"sourceRevision"`
	Status         string `json:"status"`
	Attempts       int    `json:"attempts"`
	CreatedAt      string `json:"createdAt"`
	UpdatedAt      string `json:"updatedAt"`
	NextAttemptAt  string `json:"nextAttemptAt,omitempty"`
	LeaseState     string `json:"leaseState"`
	LeaseUntil     string `json:"leaseUntil,omitempty"`
	FailureCode    string `json:"failureCode,omitempty"`
}

type DataContentExecutionObservation struct {
	Schema                   string                                `json:"schema"`
	Version                  int                                   `json:"version"`
	ExecutionID              string                                `json:"executionId"`
	Carrier                  string                                `json:"carrier"`
	Stage                    string                                `json:"stage"`
	RequestBindingDigest     string                                `json:"requestBindingDigest"`
	ExecutionEnvelopeDigest  string                                `json:"executionEnvelopeDigest"`
	JobSetEnvelopeDigest     string                                `json:"jobSetEnvelopeDigest"`
	JobSetDigest             string                                `json:"jobSetDigest"`
	ActualTaskDigest         string                                `json:"actualTaskDigest"`
	CampaignBinding          DataContentCampaignBinding            `json:"campaignBinding"`
	ObservedAt               string                                `json:"observedAt"`
	Tasks                    []DataContentExecutionObservationTask `json:"tasks"`
	PendingJobTimestamps     []string                              `json:"pendingJobTimestamps"`
	ReadyJobTimestamps       []string                              `json:"readyJobTimestamps"`
	SuccessfulJobCount       int                                   `json:"successfulJobCount"`
	TerminalJobCount         int                                   `json:"terminalJobCount"`
	ObservationWindowSeconds int                                   `json:"observationWindowSeconds"`
	LatencyMilliseconds      []int64                               `json:"latencyMilliseconds"`
	ProviderThrottleCount    int                                   `json:"providerThrottleCount"`
	StuckJobCount            int                                   `json:"stuckJobCount"`
	RedisEntryCount          int                                   `json:"redisEntryCount"`
	RedisPendingCount        int64                                 `json:"redisPendingCount"`
	ActiveLeaseCount         int                                   `json:"activeLeaseCount"`
	ExpiredLeaseCount        int                                   `json:"expiredLeaseCount"`
	LeaseEvidenceDigest      string                                `json:"leaseEvidenceDigest"`
	ObservationDigest        string                                `json:"observationDigest,omitempty"`
}

type DataContentExecutionObservationStore interface {
	ListDataContentExecutionTasks(
		ctx context.Context,
		executionID string,
	) ([]ReliableAsyncTask, error)
}

type DataContentExecutionReadyObserver interface {
	Observe(ctx context.Context, limit int64) (ReadyIndexObservation, error)
}

type DataContentExecutionObserver struct {
	Store DataContentExecutionObservationStore
	Ready DataContentExecutionReadyObserver
	Now   func() time.Time
}

func (r DataContentExecutionObservationRequest) validate() error {
	r.ExecutionID = strings.TrimSpace(r.ExecutionID)
	r.Carrier = strings.TrimSpace(r.Carrier)
	r.Stage = strings.TrimSpace(r.Stage)
	r.RequestBindingDigest = strings.TrimSpace(r.RequestBindingDigest)
	r.ExecutionEnvelopeDigest = strings.TrimSpace(r.ExecutionEnvelopeDigest)
	r.JobSetEnvelopeDigest = strings.TrimSpace(r.JobSetEnvelopeDigest)
	r.JobSetDigest = strings.TrimSpace(r.JobSetDigest)
	r.ActualTaskDigest = strings.TrimSpace(r.ActualTaskDigest)
	if r.ExecutionID == "" || r.RequestBindingDigest == "" {
		return errors.New("reliabletask observer requires executionId and request binding digest")
	}
	if r.Carrier != "homepage" && r.Carrier != "article" &&
		r.Carrier != "image" && r.Carrier != "video" {
		return fmt.Errorf("reliabletask observer carrier=%q is invalid", r.Carrier)
	}
	if r.Stage != "author" && r.Stage != "publish" {
		return fmt.Errorf("reliabletask observer stage=%q is invalid", r.Stage)
	}
	if !validSHA256Digest(r.RequestBindingDigest) {
		return errors.New("reliabletask observer request binding must be sha256")
	}
	if !validSHA256Digest(r.ExecutionEnvelopeDigest) {
		return errors.New("reliabletask observer execution envelope digest must be sha256")
	}
	if !validSHA256Digest(r.JobSetEnvelopeDigest) ||
		!validSHA256Digest(r.JobSetDigest) ||
		!validSHA256Digest(r.ActualTaskDigest) {
		return errors.New("reliabletask observer job-set bindings must be sha256")
	}
	if err := r.Campaign.Validate(); err != nil {
		return fmt.Errorf("reliabletask observer campaign binding is invalid: %w", err)
	}
	return nil
}

func (o DataContentExecutionObserver) ObserveExecution(
	ctx context.Context,
	request DataContentExecutionObservationRequest,
) (DataContentExecutionObservation, error) {
	if err := request.validate(); err != nil {
		return DataContentExecutionObservation{}, err
	}
	if o.Store == nil || o.Ready == nil {
		return DataContentExecutionObservation{}, errors.New(
			"reliabletask observer requires Mongo store and Redis ready index",
		)
	}
	now := time.Now().UTC()
	if o.Now != nil {
		now = o.Now().UTC()
	}
	tasks, err := o.Store.ListDataContentExecutionTasks(ctx, request.ExecutionID)
	if err != nil {
		return DataContentExecutionObservation{}, fmt.Errorf(
			"read execution-scoped Mongo tasks: %w",
			err,
		)
	}
	if len(tasks) == 0 {
		return DataContentExecutionObservation{}, errors.New(
			"reliabletask observer found no execution-scoped Mongo tasks",
		)
	}
	readySnapshot, err := o.Ready.Observe(ctx, dataContentObserverTaskLimit)
	if err != nil {
		return DataContentExecutionObservation{}, err
	}
	return buildDataContentExecutionObservation(request, tasks, readySnapshot, now)
}

func buildDataContentExecutionObservation(
	request DataContentExecutionObservationRequest,
	tasks []ReliableAsyncTask,
	readySnapshot ReadyIndexObservation,
	now time.Time,
) (DataContentExecutionObservation, error) {
	selected := make([]ReliableAsyncTask, 0, len(tasks))
	stageTaskCount := 0
	for _, task := range tasks {
		stage := strings.TrimSpace(task.Payload["stage"])
		if stage != "author" && stage != "publish" {
			return DataContentExecutionObservation{}, errors.New(
				"reliabletask observer Mongo task stage is invalid",
			)
		}
		if stage == strings.TrimSpace(request.Stage) {
			stageTaskCount++
		}
		if stage == strings.TrimSpace(request.Stage) &&
			strings.TrimSpace(task.Payload["jobSetEnvelopeDigest"]) == strings.TrimSpace(request.JobSetEnvelopeDigest) &&
			strings.TrimSpace(task.Payload["jobSetDigest"]) == strings.TrimSpace(request.JobSetDigest) &&
			strings.TrimSpace(task.Payload["actualTaskDigest"]) == strings.TrimSpace(request.ActualTaskDigest) {
			selected = append(selected, task)
		}
	}
	if len(selected) == 0 {
		if stageTaskCount > 0 {
			return DataContentExecutionObservation{}, errors.New(
				"reliabletask observer stage task job-set identity drift",
			)
		}
		return DataContentExecutionObservation{}, errors.New(
			"reliabletask observer found no stage-scoped Mongo tasks",
		)
	}
	sort.Slice(tasks, func(i, j int) bool {
		return strings.TrimSpace(tasks[i].Payload["jobId"]) <
			strings.TrimSpace(tasks[j].Payload["jobId"])
	})
	sort.Slice(selected, func(i, j int) bool {
		return strings.TrimSpace(selected[i].Payload["jobId"]) <
			strings.TrimSpace(selected[j].Payload["jobId"])
	})
	actualTaskDigest, err := DataContentAsyncTaskDigest(selected)
	if err != nil || actualTaskDigest != strings.TrimSpace(request.ActualTaskDigest) {
		return DataContentExecutionObservation{}, errors.New(
			"reliabletask observer actual task digest drift",
		)
	}
	taskIDs := make(map[string]struct{}, len(tasks))
	selectedTaskIDs := make(map[string]struct{}, len(selected))
	jobIDs := make(map[string]struct{}, len(tasks))
	latestReadyEntry := make(map[string]time.Time, len(readySnapshot.Entries))
	for _, entry := range readySnapshot.Entries {
		previous, exists := latestReadyEntry[entry.TaskID]
		if !exists || entry.EnqueuedAt.After(previous) {
			latestReadyEntry[entry.TaskID] = entry.EnqueuedAt.UTC()
		}
	}
	for _, task := range tasks {
		taskIDs[strings.TrimSpace(task.TaskID)] = struct{}{}
	}
	for _, task := range selected {
		selectedTaskIDs[strings.TrimSpace(task.TaskID)] = struct{}{}
	}
	selectedRedisEntries := 0
	for taskID := range latestReadyEntry {
		if _, exists := taskIDs[taskID]; !exists {
			return DataContentExecutionObservation{}, errors.New(
				"reliabletask observer Redis stream crossed executionId",
			)
		}
		if _, exists := selectedTaskIDs[taskID]; exists {
			selectedRedisEntries++
		}
	}

	rows := make([]DataContentExecutionObservationTask, 0, len(selected))
	pendingTimestamps := make([]string, 0, len(selected))
	readyTimestamps := make([]string, 0, len(selected))
	latencies := make([]int64, 0, len(selected))
	leaseEvidence := make([]map[string]any, 0, len(selected))
	successful := 0
	terminal := 0
	throttled := 0
	stuck := 0
	activeLeases := 0
	expiredLeases := 0
	oldestCreatedAt := now
	for _, task := range selected {
		row, ready, pending, err := observeDataContentTask(
			task,
			request,
			now,
		)
		if err != nil {
			return DataContentExecutionObservation{}, err
		}
		if _, exists := jobIDs[row.JobID]; exists {
			return DataContentExecutionObservation{}, fmt.Errorf(
				"reliabletask observer duplicate jobId=%q",
				row.JobID,
			)
		}
		jobIDs[row.JobID] = struct{}{}
		rows = append(rows, row)
		createdAt := task.CreatedAt.UTC()
		if createdAt.Before(oldestCreatedAt) {
			oldestCreatedAt = createdAt
		}
		if pending {
			pendingTimestamps = append(pendingTimestamps, timestamp(task.UpdatedAt))
		}
		if ready {
			enqueuedAt, exists := latestReadyEntry[strings.TrimSpace(task.TaskID)]
			if !exists {
				return DataContentExecutionObservation{}, fmt.Errorf(
					"reliabletask observer ready job %q is absent from its Redis stream",
					row.JobID,
				)
			}
			readyTimestamps = append(readyTimestamps, timestamp(enqueuedAt))
		}
		if task.Status == TaskStatusSucceeded {
			successful++
		}
		if task.Status == TaskStatusSucceeded || task.Status == TaskStatusDead {
			terminal++
			if !task.UpdatedAt.Before(task.CreatedAt) {
				latencies = append(
					latencies,
					task.UpdatedAt.Sub(task.CreatedAt).Milliseconds(),
				)
			}
		}
		failureText := ""
		if task.LastFailure != nil {
			failureText = strings.ToUpper(
				strings.TrimSpace(task.LastFailure.Code) + " " +
					strings.TrimSpace(task.LastFailure.Message),
			)
		}
		if strings.Contains(failureText, "RATE_LIMIT") ||
			strings.Contains(failureText, "THROTTL") {
			throttled++
		}
		switch row.LeaseState {
		case "active":
			activeLeases++
		case "expired":
			expiredLeases++
			stuck++
		}
		leaseEvidence = append(leaseEvidence, map[string]any{
			"jobId":      row.JobID,
			"status":     row.Status,
			"leaseState": row.LeaseState,
			"leaseUntil": row.LeaseUntil,
		})
	}
	sort.Strings(pendingTimestamps)
	sort.Strings(readyTimestamps)
	sort.Slice(latencies, func(i, j int) bool { return latencies[i] < latencies[j] })
	leaseDigest, err := canonicalObservationDigest(leaseEvidence)
	if err != nil {
		return DataContentExecutionObservation{}, err
	}
	window := int(now.Sub(oldestCreatedAt).Seconds())
	if window < 1 {
		window = 1
	}
	observation := DataContentExecutionObservation{
		Schema:                   DataContentExecutionObservationSchema,
		Version:                  dataContentExecutionObservationVersion,
		ExecutionID:              strings.TrimSpace(request.ExecutionID),
		Carrier:                  strings.TrimSpace(request.Carrier),
		Stage:                    strings.TrimSpace(request.Stage),
		RequestBindingDigest:     strings.TrimSpace(request.RequestBindingDigest),
		ExecutionEnvelopeDigest:  strings.TrimSpace(request.ExecutionEnvelopeDigest),
		JobSetEnvelopeDigest:     strings.TrimSpace(request.JobSetEnvelopeDigest),
		JobSetDigest:             strings.TrimSpace(request.JobSetDigest),
		ActualTaskDigest:         actualTaskDigest,
		CampaignBinding:          request.Campaign,
		ObservedAt:               timestamp(now),
		Tasks:                    rows,
		PendingJobTimestamps:     pendingTimestamps,
		ReadyJobTimestamps:       readyTimestamps,
		SuccessfulJobCount:       successful,
		TerminalJobCount:         terminal,
		ObservationWindowSeconds: window,
		LatencyMilliseconds:      latencies,
		ProviderThrottleCount:    throttled,
		StuckJobCount:            stuck,
		RedisEntryCount:          selectedRedisEntries,
		RedisPendingCount:        int64(activeLeases),
		ActiveLeaseCount:         activeLeases,
		ExpiredLeaseCount:        expiredLeases,
		LeaseEvidenceDigest:      leaseDigest,
	}
	digest, err := canonicalObservationDigest(observation)
	if err != nil {
		return DataContentExecutionObservation{}, err
	}
	observation.ObservationDigest = digest
	return observation, nil
}

func observeDataContentTask(
	task ReliableAsyncTask,
	request DataContentExecutionObservationRequest,
	now time.Time,
) (DataContentExecutionObservationTask, bool, bool, error) {
	if task.TaskType != DataContentTaskType ||
		strings.TrimSpace(task.Payload["schema"]) != "quwoquan.object_job" ||
		strings.TrimSpace(task.Payload["executionId"]) != strings.TrimSpace(request.ExecutionID) ||
		strings.TrimSpace(task.Payload["carrier"]) != strings.TrimSpace(request.Carrier) {
		return DataContentExecutionObservationTask{}, false, false, errors.New(
			"reliabletask observer Mongo task identity drift",
		)
	}
	if strings.TrimSpace(task.Payload["executionEnvelopeDigest"]) !=
		strings.TrimSpace(request.ExecutionEnvelopeDigest) {
		return DataContentExecutionObservationTask{}, false, false, errors.New(
			"reliabletask observer Mongo task execution envelope identity drift",
		)
	}
	if strings.TrimSpace(task.Payload["jobSetEnvelopeDigest"]) !=
		strings.TrimSpace(request.JobSetEnvelopeDigest) ||
		strings.TrimSpace(task.Payload["jobSetDigest"]) !=
			strings.TrimSpace(request.JobSetDigest) ||
		strings.TrimSpace(task.Payload["actualTaskDigest"]) !=
			strings.TrimSpace(request.ActualTaskDigest) {
		return DataContentExecutionObservationTask{}, false, false, errors.New(
			"reliabletask observer Mongo task job-set identity drift",
		)
	}
	generation, generationErr := strconv.Atoi(
		strings.TrimSpace(task.Payload["campaignGeneration"]),
	)
	taskCampaign := DataContentCampaignBinding{
		RootExecutionID:     task.Payload["campaignRootExecutionId"],
		RunID:               task.Payload["campaignRunId"],
		Generation:          generation,
		FencingToken:        task.Payload["campaignFencingToken"],
		PlanDigest:          task.Payload["campaignPlanDigest"],
		SourceRevision:      task.Payload["campaignSourceRevision"],
		SourceDigest:        task.Payload["campaignSourceDigest"],
		EntityCatalogDigest: task.Payload["campaignEntityCatalogDigest"],
	}
	if generationErr != nil ||
		taskCampaign != request.Campaign ||
		taskCampaign.Validate() != nil {
		return DataContentExecutionObservationTask{}, false, false, errors.New(
			"reliabletask observer Mongo task campaign generation/source identity drift",
		)
	}
	job := DataContentJob{
		EntityRef:            task.Payload["entityRef"],
		Carrier:              task.Payload["carrier"],
		SourceRevision:       task.Payload["sourceRevision"],
		JobID:                task.Payload["jobId"],
		ExecutionID:          task.Payload["executionId"],
		Ref:                  task.Payload["ref"],
		Stage:                task.Payload["stage"],
		PartitionKey:         task.Payload["partitionKey"],
		IdempotencyKey:       task.Payload["idempotencyKey"],
		JobSetEnvelopeDigest: task.Payload["jobSetEnvelopeDigest"],
		JobSetDigest:         task.Payload["jobSetDigest"],
		ActualTaskDigest:     task.Payload["actualTaskDigest"],
	}
	expectedKey, err := job.ValidateIdentity()
	if err != nil || strings.TrimSpace(task.IdempotencyKey) != expectedKey {
		return DataContentExecutionObservationTask{}, false, false, errors.New(
			"reliabletask observer Mongo task source identity drift",
		)
	}
	if task.CreatedAt.IsZero() || task.UpdatedAt.IsZero() || task.UpdatedAt.Before(task.CreatedAt) {
		return DataContentExecutionObservationTask{}, false, false, errors.New(
			"reliabletask observer Mongo task timestamps are invalid",
		)
	}
	if task.Status != TaskStatusReady && task.Status != TaskStatusProcessing &&
		task.Status != TaskStatusRetryWait && task.Status != TaskStatusSucceeded &&
		task.Status != TaskStatusDead {
		return DataContentExecutionObservationTask{}, false, false, fmt.Errorf(
			"reliabletask observer Mongo task status=%q is invalid",
			task.Status,
		)
	}
	leaseState := "none"
	if task.Status == TaskStatusProcessing && !task.LeaseUntil.IsZero() {
		leaseState = "active"
		if !task.LeaseUntil.After(now) {
			leaseState = "expired"
		}
	}
	ready := task.Status == TaskStatusReady ||
		(task.Status == TaskStatusRetryWait && !task.NextAttemptAt.After(now)) ||
		(task.Status == TaskStatusProcessing && leaseState == "expired")
	pending := task.Status == TaskStatusReady || task.Status == TaskStatusProcessing ||
		task.Status == TaskStatusRetryWait
	row := DataContentExecutionObservationTask{
		JobID:          strings.TrimSpace(job.JobID),
		EntityRef:      strings.TrimSpace(job.EntityRef),
		Stage:          strings.TrimSpace(job.Stage),
		SourceRevision: strings.TrimSpace(job.SourceRevision),
		Status:         task.Status,
		Attempts:       task.Attempts,
		CreatedAt:      timestamp(task.CreatedAt),
		UpdatedAt:      timestamp(task.UpdatedAt),
		LeaseState:     leaseState,
	}
	if !task.NextAttemptAt.IsZero() {
		row.NextAttemptAt = timestamp(task.NextAttemptAt)
	}
	if !task.LeaseUntil.IsZero() {
		row.LeaseUntil = timestamp(task.LeaseUntil)
	}
	if task.LastFailure != nil {
		row.FailureCode = strings.TrimSpace(task.LastFailure.Code)
	}
	return row, ready, pending, nil
}

func validSHA256Digest(value string) bool {
	value = strings.TrimSpace(value)
	raw := strings.TrimPrefix(value, "sha256:")
	if !strings.HasPrefix(value, "sha256:") || len(raw) != 64 {
		return false
	}
	_, err := hex.DecodeString(raw)
	return err == nil
}

func ValidSHA256Digest(value string) bool {
	return validSHA256Digest(value)
}

func timestamp(value time.Time) string {
	return value.UTC().Format(time.RFC3339Nano)
}

func canonicalObservationJSON(value any) ([]byte, error) {
	payload, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	var document any
	decoder := json.NewDecoder(strings.NewReader(string(payload)))
	decoder.UseNumber()
	if err := decoder.Decode(&document); err != nil {
		return nil, err
	}
	return json.Marshal(document)
}

func canonicalObservationDigest(value any) (string, error) {
	payload, err := canonicalObservationJSON(value)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

// MarshalDataContentExecutionObservation emits one compact, sorted-key JSON
// value suitable for the Data process boundary. No URI, credential, lease
// token, or worker identity is present in the public observation type.
func MarshalDataContentExecutionObservation(
	observation DataContentExecutionObservation,
) ([]byte, error) {
	return canonicalObservationJSON(observation)
}
