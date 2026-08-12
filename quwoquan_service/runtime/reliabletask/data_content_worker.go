package reliabletask

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"
)

const dataContentResultSchema = "quwoquan.data_content_object_result"

const (
	DataContentAcceptanceCommercialCanonical = "commercial_canonical"
	DataContentAcceptanceResearchCanonical   = "research_canonical"
	DataContentAcceptanceStageCompleted      = "stage_completed"
	DataContentAcceptanceContractFixture     = "contract_fixture"
)

var dataContentPayloadFields = map[string]struct{}{
	"schema":               {},
	"jobId":                {},
	"executionId":          {},
	"ref":                  {},
	"stage":                {},
	"partitionKey":         {},
	"entityRef":            {},
	"carrier":              {},
	"sourceRevision":       {},
	"idempotencyKey":       {},
	"jobSetEnvelopeDigest": {},
	"jobSetDigest":         {},
	"actualTaskDigest":     {},
	"maxAttempts":          {},
	"workerHostSetDigest":  {},
	"workerHostGeneration": {},
	"workerFencingToken":   {},
	"workerHostScopeId":    {},
}

// DataContentWorkItem is the single-track worker input decoded from object_job.
type DataContentWorkItem struct {
	RuntimeTaskID        string `json:"runtimeTaskId"`
	LeaseToken           string `json:"leaseToken"`
	JobID                string `json:"jobId"`
	ExecutionID          string `json:"executionId"`
	Ref                  string `json:"ref"`
	Stage                string `json:"stage"`
	PartitionKey         string `json:"partitionKey"`
	EntityRef            string `json:"entityRef"`
	Carrier              string `json:"carrier"`
	SourceRevision       string `json:"sourceRevision"`
	IdempotencyKey       string `json:"idempotencyKey"`
	JobSetEnvelopeDigest string `json:"jobSetEnvelopeDigest"`
	JobSetDigest         string `json:"jobSetDigest"`
	ActualTaskDigest     string `json:"actualTaskDigest"`
	MaxAttempts          int    `json:"maxAttempts"`
	WorkerHostSetDigest  string `json:"workerHostSetDigest,omitempty"`
	WorkerHostGeneration int    `json:"workerHostGeneration,omitempty"`
	WorkerFencingToken   string `json:"workerFencingToken,omitempty"`
	WorkerHostScopeID    string `json:"workerHostScopeId,omitempty"`
}

func DecodeDataContentWorkItem(task ReliableAsyncTask) (DataContentWorkItem, error) {
	if task.TaskType != DataContentTaskType {
		return DataContentWorkItem{}, fmt.Errorf(
			"reliabletask data worker taskType=%q",
			task.TaskType,
		)
	}
	for key := range task.Payload {
		if _, ok := dataContentPayloadFields[key]; !ok {
			return DataContentWorkItem{}, fmt.Errorf(
				"reliabletask data worker payload field %q is not allowed",
				key,
			)
		}
	}
	if strings.TrimSpace(task.Payload["schema"]) != "quwoquan.object_job" {
		return DataContentWorkItem{}, fmt.Errorf(
			"reliabletask data worker payload schema is invalid",
		)
	}
	hostFieldCount := 0
	for _, field := range []string{
		"workerHostSetDigest", "workerHostGeneration",
		"workerFencingToken", "workerHostScopeId",
	} {
		if strings.TrimSpace(task.Payload[field]) != "" {
			hostFieldCount++
		}
	}
	if hostFieldCount != 0 && hostFieldCount != 4 {
		return DataContentWorkItem{}, fmt.Errorf(
			"reliabletask data worker host fence is incomplete",
		)
	}
	hostGeneration := 0
	if hostFieldCount == 4 {
		var err error
		hostGeneration, err = strconv.Atoi(
			strings.TrimSpace(task.Payload["workerHostGeneration"]),
		)
		if err != nil || hostGeneration < 1 {
			return DataContentWorkItem{}, fmt.Errorf(
				"reliabletask data worker host generation is invalid",
			)
		}
	}
	maxAttempts, err := strconv.Atoi(strings.TrimSpace(task.Payload["maxAttempts"]))
	if err != nil || maxAttempts < 1 {
		return DataContentWorkItem{}, fmt.Errorf(
			"reliabletask data worker maxAttempts is invalid",
		)
	}
	item := DataContentWorkItem{
		RuntimeTaskID:        strings.TrimSpace(task.TaskID),
		LeaseToken:           strings.TrimSpace(task.LeaseToken),
		JobID:                strings.TrimSpace(task.Payload["jobId"]),
		ExecutionID:          strings.TrimSpace(task.Payload["executionId"]),
		Ref:                  strings.TrimSpace(task.Payload["ref"]),
		Stage:                strings.TrimSpace(task.Payload["stage"]),
		PartitionKey:         strings.TrimSpace(task.Payload["partitionKey"]),
		EntityRef:            strings.TrimSpace(task.Payload["entityRef"]),
		Carrier:              strings.TrimSpace(task.Payload["carrier"]),
		SourceRevision:       strings.TrimSpace(task.Payload["sourceRevision"]),
		IdempotencyKey:       strings.TrimSpace(task.Payload["idempotencyKey"]),
		JobSetEnvelopeDigest: strings.TrimSpace(task.Payload["jobSetEnvelopeDigest"]),
		JobSetDigest:         strings.TrimSpace(task.Payload["jobSetDigest"]),
		ActualTaskDigest:     strings.TrimSpace(task.Payload["actualTaskDigest"]),
		MaxAttempts:          maxAttempts,
		WorkerHostSetDigest:  strings.TrimSpace(task.Payload["workerHostSetDigest"]),
		WorkerHostGeneration: hostGeneration,
		WorkerFencingToken:   strings.TrimSpace(task.Payload["workerFencingToken"]),
		WorkerHostScopeID:    strings.TrimSpace(task.Payload["workerHostScopeId"]),
	}
	job := DataContentJob{
		EntityRef:            item.EntityRef,
		Carrier:              item.Carrier,
		SourceRevision:       item.SourceRevision,
		JobID:                item.JobID,
		ExecutionID:          item.ExecutionID,
		Ref:                  item.Ref,
		Stage:                item.Stage,
		PartitionKey:         item.PartitionKey,
		IdempotencyKey:       item.IdempotencyKey,
		JobSetEnvelopeDigest: item.JobSetEnvelopeDigest,
		JobSetDigest:         item.JobSetDigest,
		ActualTaskDigest:     item.ActualTaskDigest,
		MaxAttempts:          item.MaxAttempts,
	}
	if hostFieldCount == 4 {
		job.WorkerFence = &DataContentWorkerFence{
			HostSetDigest: item.WorkerHostSetDigest,
			Generation:    item.WorkerHostGeneration,
			FencingToken:  item.WorkerFencingToken,
			HostScopeID:   item.WorkerHostScopeID,
		}
	}
	expectedKey, err := job.ValidateIdentity()
	if err != nil {
		return DataContentWorkItem{}, err
	}
	if item.RuntimeTaskID == "" || item.LeaseToken == "" {
		return DataContentWorkItem{}, fmt.Errorf(
			"reliabletask data worker requires runtime task and lease identity",
		)
	}
	if item.IdempotencyKey != expectedKey ||
		task.IdempotencyKey != expectedKey ||
		task.AggregateID != item.EntityRef ||
		task.PartitionKey != item.PartitionKey {
		return DataContentWorkItem{}, fmt.Errorf(
			"reliabletask data worker identity binding mismatch",
		)
	}
	return item, nil
}

// DataContentExecutionResult is written under the same fenced Mongo task before
// the task may transition to succeeded. Accepted means the executor completed
// the real object transaction, not merely an Agent or control-plane call.
type DataContentExecutionResult struct {
	ExecutionID           string    `json:"executionId"`
	JobID                 string    `json:"jobId"`
	CanonicalObjectRef    string    `json:"canonicalObjectRef,omitempty"`
	CanonicalObjectSHA256 string    `json:"canonicalObjectSha256,omitempty"`
	ObjectTransactionID   string    `json:"objectTransactionId,omitempty"`
	PoolDeliveryIntentID  string    `json:"poolDeliveryIntentId,omitempty"`
	ResultEnvelopeRef     string    `json:"resultEnvelopeRef"`
	AcceptanceClass       string    `json:"acceptanceClass"`
	CompletedAt           time.Time `json:"completedAt"`
}

func (r DataContentExecutionResult) validate(item DataContentWorkItem) error {
	if strings.TrimSpace(r.ExecutionID) != item.ExecutionID ||
		strings.TrimSpace(r.JobID) != item.JobID {
		return fmt.Errorf("reliabletask data result execution/job binding mismatch")
	}
	for _, field := range []struct {
		name  string
		value string
	}{
		{name: "resultEnvelopeRef", value: r.ResultEnvelopeRef},
		{name: "acceptanceClass", value: r.AcceptanceClass},
	} {
		if strings.TrimSpace(field.value) == "" {
			return fmt.Errorf("reliabletask data result requires %s", field.name)
		}
	}
	switch r.AcceptanceClass {
	case DataContentAcceptanceCommercialCanonical,
		DataContentAcceptanceResearchCanonical:
		if item.Stage != "publish" {
			return fmt.Errorf(
				"reliabletask canonical data result requires publish stage",
			)
		}
		for _, field := range []struct {
			name  string
			value string
		}{
			{name: "canonicalObjectRef", value: r.CanonicalObjectRef},
			{name: "objectTransactionId", value: r.ObjectTransactionID},
			{name: "poolDeliveryIntentId", value: r.PoolDeliveryIntentID},
		} {
			if strings.TrimSpace(field.value) == "" {
				return fmt.Errorf(
					"reliabletask canonical data result requires %s",
					field.name,
				)
			}
		}
		if !validDataContentSHA256(r.CanonicalObjectSHA256) {
			return fmt.Errorf(
				"reliabletask canonical data result requires canonicalObjectSha256",
			)
		}
		if !validDataContentSHA256(r.PoolDeliveryIntentID) {
			return fmt.Errorf(
				"reliabletask canonical data result requires valid poolDeliveryIntentId",
			)
		}
	case DataContentAcceptanceStageCompleted:
		if item.Stage == "publish" {
			return fmt.Errorf(
				"reliabletask publish stage cannot report stage_completed",
			)
		}
	case DataContentAcceptanceContractFixture:
	default:
		return fmt.Errorf(
			"reliabletask data result acceptanceClass=%q is invalid",
			r.AcceptanceClass,
		)
	}
	if r.CompletedAt.IsZero() {
		return fmt.Errorf("reliabletask data result requires completedAt")
	}
	return nil
}

func (r DataContentExecutionResult) document() map[string]string {
	status := "contract_fixture"
	switch r.AcceptanceClass {
	case DataContentAcceptanceCommercialCanonical,
		DataContentAcceptanceResearchCanonical:
		status = "accepted"
	case DataContentAcceptanceStageCompleted:
		status = "stage_completed"
	}
	return map[string]string{
		"schema":                dataContentResultSchema,
		"status":                status,
		"executionId":           strings.TrimSpace(r.ExecutionID),
		"jobId":                 strings.TrimSpace(r.JobID),
		"canonicalObjectRef":    strings.TrimSpace(r.CanonicalObjectRef),
		"canonicalObjectSha256": strings.TrimSpace(r.CanonicalObjectSHA256),
		"objectTransactionId":   strings.TrimSpace(r.ObjectTransactionID),
		"poolDeliveryIntentId":  strings.TrimSpace(r.PoolDeliveryIntentID),
		"resultEnvelopeRef":     strings.TrimSpace(r.ResultEnvelopeRef),
		"acceptanceClass":       strings.TrimSpace(r.AcceptanceClass),
		"completedAt":           r.CompletedAt.UTC().Format(time.RFC3339Nano),
	}
}

type DataContentExecutor interface {
	ExecuteDataContentObject(
		ctx context.Context,
		item DataContentWorkItem,
	) (DataContentExecutionResult, error)
}

type DataContentExecutorFunc func(
	context.Context,
	DataContentWorkItem,
) (DataContentExecutionResult, error)

func (fn DataContentExecutorFunc) ExecuteDataContentObject(
	ctx context.Context,
	item DataContentWorkItem,
) (DataContentExecutionResult, error) {
	return fn(ctx, item)
}

func (f DataContentFleet) ProcessOneContent(
	ctx context.Context,
	executor DataContentExecutor,
) (bool, error) {
	if executor == nil {
		return false, fmt.Errorf("reliabletask data content executor is required")
	}
	return f.ProcessOne(ctx, func(workerCtx context.Context, task ReliableAsyncTask) error {
		item, err := DecodeDataContentWorkItem(task)
		if err != nil {
			return err
		}
		result, err := executor.ExecuteDataContentObject(workerCtx, item)
		if err != nil {
			return err
		}
		if err := result.validate(item); err != nil {
			return err
		}
		if (result.AcceptanceClass == DataContentAcceptanceCommercialCanonical ||
			result.AcceptanceClass == DataContentAcceptanceResearchCanonical) &&
			f.ResultVerifier == nil {
			return fmt.Errorf(
				"reliabletask canonical data result requires evidence verifier",
			)
		}
		if f.ResultVerifier != nil {
			if err := f.ResultVerifier.VerifyDataContentResult(
				workerCtx,
				item,
				result,
			); err != nil {
				return err
			}
		}
		now := time.Now().UTC()
		if f.Now != nil {
			now = f.Now().UTC()
		}
		return f.Store.RecordTaskResult(
			workerCtx,
			task.TaskID,
			task.LeaseToken,
			result.document(),
			now,
		)
	})
}
