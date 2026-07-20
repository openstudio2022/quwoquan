package application

import (
	"context"
	"fmt"
	"reflect"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/generated"
)

type ExternalInteractionStore interface {
	reliabletask.Store
	reliabletask.ProviderAttemptLedgerStore
	reliabletask.DLQRecoveryStore
	reliabletask.RetentionCleanupStore
	reliabletask.MetricsStore
	FindLatestTaskOutboxByAggregateID(
		ctx context.Context,
		aggregateID string,
	) (reliabletask.TaskOutboxRecord, bool, error)
}

type ExternalInteractionService struct {
	store      ExternalInteractionStore
	dispatcher reliabletask.ExternalInteractionDispatcher
	worker     reliabletask.ExternalInteractionWorker
	policies   map[string]reliabletask.ProviderPolicy
	references otpseal.ReferenceStore
	now        func() time.Time
}

func NewExternalInteractionService(
	store ExternalInteractionStore,
	providers map[string]reliabletask.ExternalProvider,
	policies map[string]reliabletask.ProviderPolicy,
	callback reliabletask.ExternalInteractionCallbackSender,
	referenceStores ...otpseal.ReferenceStore,
) (*ExternalInteractionService, error) {
	if isNilDependency(store) {
		return nil, fmt.Errorf("external interaction store is required")
	}
	if len(providers) == 0 {
		return nil, fmt.Errorf("external interaction providers are required")
	}
	if len(policies) == 0 {
		return nil, fmt.Errorf("external interaction provider policies are required")
	}
	if isNilDependency(callback) {
		return nil, fmt.Errorf("external interaction callback sender is required")
	}
	var references otpseal.ReferenceStore
	if len(referenceStores) > 0 {
		references = referenceStores[0]
	}
	if _, smsEnabled := policies[reliabletask.ExternalInteractionOperationSmsOTP]; smsEnabled &&
		isNilDependency(references) {
		return nil, fmt.Errorf("otp code reference store is required for sms_otp.send")
	}
	taskTypes := make([]string, 0, len(policies))
	normalizedPolicies := make(map[string]reliabletask.ProviderPolicy, len(policies))
	for operation, policy := range policies {
		operation = strings.TrimSpace(operation)
		if !supportedExternalOperation(operation) {
			return nil, fmt.Errorf("external interaction operation %q is not supported", operation)
		}
		if len(policy.Providers) == 0 {
			return nil, fmt.Errorf("external interaction operation %s has no provider policy", operation)
		}
		if policy.Timeout <= 0 {
			return nil, fmt.Errorf("external interaction operation %s timeout must be positive", operation)
		}
		normalizedProviders := make([]string, 0, len(policy.Providers))
		for _, rawProviderName := range policy.Providers {
			providerName := strings.TrimSpace(rawProviderName)
			if providerName == "" {
				return nil, fmt.Errorf("external interaction operation %s has an empty provider name", operation)
			}
			if strings.Contains(strings.ToLower(providerName), "mock") {
				return nil, fmt.Errorf(
					"external interaction operation %s cannot use mock provider %s",
					operation,
					providerName,
				)
			}
			if isNilDependency(providers[providerName]) {
				return nil, fmt.Errorf(
					"external interaction provider %s for operation %s is unavailable",
					providerName,
					operation,
				)
			}
			normalizedProviders = append(normalizedProviders, providerName)
		}
		policy.Providers = normalizedProviders
		if policy.RetryPolicy.MaxAttempts <= 0 {
			return nil, fmt.Errorf(
				"external interaction operation %s retry policy is required",
				operation,
			)
		}
		normalizedPolicies[operation] = policy
		taskTypes = append(taskTypes, reliabletask.TaskTypeForExternalInteraction(operation))
	}
	sort.Strings(taskTypes)
	now := func() time.Time { return time.Now().UTC() }
	return &ExternalInteractionService{
		store: store,
		dispatcher: reliabletask.ExternalInteractionDispatcher{
			Writer:           reliabletask.NewTaskOutboxWriter(store),
			TaskPayloadAllow: externalInteractionTaskPayloadAllowlist(),
			Now:              now,
		},
		worker: reliabletask.ExternalInteractionWorker{
			Worker: reliabletask.Worker{
				Store:     store,
				TaskTypes: taskTypes,
				WorkerID:  "integration-external-worker",
				LeaseTTL:  30 * time.Second,
				Retry:     reliabletask.DefaultRetryPolicy(),
				Now:       now,
			},
			Providers: providers,
			Policies:  normalizedPolicies,
			Ledger:    store,
			Callback:  callback,
			Now:       now,
		},
		policies:   normalizedPolicies,
		now:        now,
		references: references,
	}, nil
}

func (s *ExternalInteractionService) Submit(ctx context.Context, req reliabletask.ExternalInteractionRequest) (reliabletask.ExternalInteractionAccepted, error) {
	if _, enabled := s.policies[req.Operation]; !enabled {
		return reliabletask.ExternalInteractionAccepted{}, fmt.Errorf(
			"external interaction operation %s is disabled",
			req.Operation,
		)
	}
	if req.Operation == reliabletask.ExternalInteractionOperationPush {
		if err := ValidatePushDeliveryRequest(req); err != nil {
			return reliabletask.ExternalInteractionAccepted{},
				generated.AppErrorFromPushDeliveryInvalidRequest(err.Error())
		}
	}
	if req.Operation != reliabletask.ExternalInteractionOperationSmsOTP {
		return s.dispatcher.Submit(ctx, req)
	}
	if isNilDependency(s.references) {
		return reliabletask.ExternalInteractionAccepted{}, fmt.Errorf("otp code reference store is required")
	}
	payload := reliabletask.CloneStringMap(req.Payload)
	codeRef := strings.TrimSpace(payload["codeRef"])
	challengeID := strings.TrimSpace(payload["challengeId"])
	if codeRef == "" || challengeID == "" {
		return reliabletask.ExternalInteractionAccepted{}, fmt.Errorf("sms otp codeRef and challengeId are required")
	}
	if err := s.references.Put(ctx, otpseal.StoredReference{
		RequestID:   req.RequestID,
		ChallengeID: challengeID,
		CodeRef:     codeRef,
		ExpiresAt:   req.ExpiresAt,
	}); err != nil {
		return reliabletask.ExternalInteractionAccepted{}, fmt.Errorf("store otp code reference: %w", err)
	}
	delete(payload, "codeRef")
	req.Payload = payload
	accepted, err := s.dispatcher.Submit(ctx, req)
	if err != nil {
		_ = s.references.Delete(ctx, req.RequestID, challengeID)
		return reliabletask.ExternalInteractionAccepted{}, err
	}
	return accepted, nil
}

func (s *ExternalInteractionService) DispatchDue(ctx context.Context, limit int) error {
	_, err := reliabletask.Dispatcher{
		Store: s.store,
		Now:   s.now,
	}.DispatchDue(ctx, limit)
	return err
}

func (s *ExternalInteractionService) ProcessOne(ctx context.Context) (bool, error) {
	return s.worker.ProcessOne(ctx)
}

func (s *ExternalInteractionService) ListAttempts(ctx context.Context, requestID string) ([]reliabletask.ProviderAttemptRecord, error) {
	return s.store.ListProviderAttempts(ctx, requestID)
}

// ExternalInteractionRequestState 是 GetExternalInteractionRequest 的归一化
// 只读切片：状态从最新 provider attempt 派生，无 attempt 时回落到受理态。
type ExternalInteractionRequestState struct {
	RequestID string `json:"requestId"`
	Operation string `json:"operation"`
	Status    string `json:"status"`
	UpdatedAt string `json:"updatedAt"`
}

func (s *ExternalInteractionService) GetRequest(
	ctx context.Context,
	requestID string,
) (ExternalInteractionRequestState, bool, error) {
	requestID = strings.TrimSpace(requestID)
	if requestID == "" {
		return ExternalInteractionRequestState{}, false, fmt.Errorf("requestId is required")
	}
	attempts, err := s.store.ListProviderAttempts(ctx, requestID)
	if err != nil {
		return ExternalInteractionRequestState{}, false, err
	}
	if len(attempts) > 0 {
		latest := attempts[0]
		for _, attempt := range attempts[1:] {
			if attempt.CreatedAt.After(latest.CreatedAt) {
				latest = attempt
			}
		}
		return ExternalInteractionRequestState{
			RequestID: requestID,
			Operation: latest.Operation,
			Status:    string(latest.Status),
			UpdatedAt: latest.CreatedAt.UTC().Format(time.RFC3339),
		}, true, nil
	}
	task, found, err := s.store.FindLatestTaskOutboxByAggregateID(ctx, requestID)
	if err != nil {
		return ExternalInteractionRequestState{}, false, err
	}
	if !found {
		return ExternalInteractionRequestState{}, false, nil
	}
	return ExternalInteractionRequestState{
		RequestID: requestID,
		Operation: strings.TrimPrefix(task.TaskType, "external_interaction."),
		Status:    string(reliabletask.ExternalInteractionStatusAccepted),
		UpdatedAt: task.UpdatedAt.UTC().Format(time.RFC3339),
	}, true, nil
}

type ExternalDeadLetter struct {
	RequestID  string `json:"requestId"`
	Operation  string `json:"operation"`
	Provider   string `json:"provider"`
	FinalError string `json:"finalError"`
	Retryable  bool   `json:"retryable"`
	CreatedAt  string `json:"createdAt"`
}

func (s *ExternalInteractionService) ListDeadLetters(ctx context.Context, requestID string) ([]ExternalDeadLetter, error) {
	attempts, err := s.ListAttempts(ctx, requestID)
	if err != nil {
		return nil, err
	}
	out := make([]ExternalDeadLetter, 0)
	for _, attempt := range attempts {
		if attempt.Status != reliabletask.ExternalInteractionStatusFailed || attempt.Retryable {
			continue
		}
		out = append(out, ExternalDeadLetter{
			RequestID:  attempt.RequestID,
			Operation:  attempt.Operation,
			Provider:   attempt.Provider,
			FinalError: attempt.NormalizedError,
			Retryable:  attempt.Retryable,
			CreatedAt:  attempt.CreatedAt.Format(time.RFC3339),
		})
	}
	return out, nil
}

func (s *ExternalInteractionService) RecoverDeadTask(ctx context.Context, taskID string) error {
	return s.store.RecoverDeadTask(ctx, taskID, s.now())
}

func (s *ExternalInteractionService) CleanupRetention(ctx context.Context, policy reliabletask.RetentionPolicy) (reliabletask.RetentionCleanupResult, error) {
	return s.store.CleanupReliableTaskRetention(ctx, policy, s.now())
}

func (s *ExternalInteractionService) Metrics(ctx context.Context) (reliabletask.MetricsSnapshot, error) {
	return s.store.ReliableTaskMetrics(ctx)
}

func supportedExternalOperation(operation string) bool {
	switch operation {
	case reliabletask.ExternalInteractionOperationSmsOTP,
		reliabletask.ExternalInteractionOperationPush,
		reliabletask.ExternalInteractionOperationOneTapPhone,
		reliabletask.ExternalInteractionOperationWebhook:
		return true
	default:
		return false
	}
}

func externalInteractionTaskPayloadAllowlist() []string {
	allow := append(
		[]string{},
		reliabletask.DefaultExternalInteractionPayloadAllowlist()...,
	)
	return append(
		allow,
		"action",
		"endpointRef",
		"deliveryKey",
		"callId",
		"targetPersonaId",
		"callType",
		"callerName",
		"sourceLabel",
		"trustRelation",
		"occurredAt",
	)
}

func isNilDependency(value any) bool {
	if value == nil {
		return true
	}
	reflected := reflect.ValueOf(value)
	switch reflected.Kind() {
	case reflect.Chan,
		reflect.Func,
		reflect.Interface,
		reflect.Map,
		reflect.Pointer,
		reflect.Slice:
		return reflected.IsNil()
	default:
		return false
	}
}
