package application

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/runtime/reliabletask"
)

type ExternalInteractionService struct {
	store      reliabletask.Store
	dispatcher reliabletask.ExternalInteractionDispatcher
	worker     reliabletask.ExternalInteractionWorker
	now        func() time.Time
}

func NewExternalInteractionService(
	store reliabletask.Store,
	providers map[string]reliabletask.ExternalProvider,
	callback reliabletask.ExternalInteractionCallbackSender,
) *ExternalInteractionService {
	if store == nil {
		store = reliabletask.NewMemoryStore()
	}
	now := func() time.Time { return time.Now().UTC() }
	return &ExternalInteractionService{
		store: store,
		dispatcher: reliabletask.ExternalInteractionDispatcher{
			Writer: reliabletask.NewTaskOutboxWriter(store),
			Now:    now,
		},
		worker: reliabletask.ExternalInteractionWorker{
			Worker: reliabletask.Worker{
				Store:     store,
				TaskTypes: []string{reliabletask.TaskTypeForExternalInteraction(reliabletask.ExternalInteractionOperationSmsOTP), reliabletask.TaskTypeForExternalInteraction(reliabletask.ExternalInteractionOperationPush)},
				WorkerID:  "integration-external-worker",
				LeaseTTL:  30 * time.Second,
				Retry:     reliabletask.DefaultRetryPolicy(),
				Now:       now,
			},
			Providers: providers,
			Policies: map[string]reliabletask.ProviderPolicy{
				reliabletask.ExternalInteractionOperationSmsOTP: {
					Providers:   []string{"mock_sms"},
					Timeout:     2 * time.Second,
					RetryPolicy: reliabletask.DefaultRetryPolicy(),
				},
				reliabletask.ExternalInteractionOperationPush: {
					Providers:   []string{"mock_push"},
					Timeout:     2 * time.Second,
					RetryPolicy: reliabletask.DefaultRetryPolicy(),
				},
			},
			Ledger:   providerAttemptLedger(store),
			Callback: callback,
			Now:      now,
		},
		now: now,
	}
}

func (s *ExternalInteractionService) Submit(ctx context.Context, req reliabletask.ExternalInteractionRequest) (reliabletask.ExternalInteractionAccepted, error) {
	return s.dispatcher.Submit(ctx, req)
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
	ledger := providerAttemptLedger(s.store)
	if ledger == nil {
		return nil, nil
	}
	return ledger.ListProviderAttempts(ctx, requestID)
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
	recovery, ok := s.store.(reliabletask.DLQRecoveryStore)
	if !ok {
		return nil
	}
	return recovery.RecoverDeadTask(ctx, taskID, s.now())
}

func (s *ExternalInteractionService) CleanupRetention(ctx context.Context, policy reliabletask.RetentionPolicy) (reliabletask.RetentionCleanupResult, error) {
	cleanup, ok := s.store.(reliabletask.RetentionCleanupStore)
	if !ok {
		return reliabletask.RetentionCleanupResult{}, nil
	}
	return cleanup.CleanupReliableTaskRetention(ctx, policy, s.now())
}

func (s *ExternalInteractionService) Metrics(ctx context.Context) (reliabletask.MetricsSnapshot, error) {
	metrics, ok := s.store.(reliabletask.MetricsStore)
	if !ok {
		return reliabletask.MetricsSnapshot{}, nil
	}
	return metrics.ReliableTaskMetrics(ctx)
}

type MockSMSProvider struct{}

func (MockSMSProvider) Send(ctx context.Context, req reliabletask.ExternalInteractionRequest, task reliabletask.ReliableAsyncTask) (reliabletask.ExternalInteractionResult, error) {
	_ = ctx
	if task.Payload["forceProviderFailure"] == "true" {
		return reliabletask.ExternalInteractionResult{
			RequestID:       req.RequestID,
			Operation:       req.Operation,
			Status:          reliabletask.ExternalInteractionStatusFailed,
			Provider:        "mock_sms",
			NormalizedError: "mock_sms_forced_failure",
			Retryable:       task.Payload["forceRetryable"] != "false",
		}, fmt.Errorf("mock sms provider failure")
	}
	return reliabletask.ExternalInteractionResult{
		RequestID:         req.RequestID,
		Operation:         req.Operation,
		Status:            reliabletask.ExternalInteractionStatusDelivered,
		Provider:          "mock_sms",
		ProviderRequestID: "mock-sms-" + req.RequestID,
		Retryable:         false,
	}, nil
}

type MockPushProvider struct{}

func (MockPushProvider) Send(ctx context.Context, req reliabletask.ExternalInteractionRequest, task reliabletask.ReliableAsyncTask) (reliabletask.ExternalInteractionResult, error) {
	_ = ctx
	_ = task
	return reliabletask.ExternalInteractionResult{
		RequestID:         req.RequestID,
		Operation:         req.Operation,
		Status:            reliabletask.ExternalInteractionStatusDelivered,
		Provider:          "mock_push",
		ProviderRequestID: "mock-push-" + req.RequestID,
		Retryable:         false,
	}, nil
}

type HTTPCallbackSender struct {
	Client *http.Client
	Secret string
}

func (s HTTPCallbackSender) SendExternalInteractionResult(ctx context.Context, result reliabletask.ExternalInteractionResult) error {
	if strings.TrimSpace(result.RequestID) == "" || strings.TrimSpace(result.CallbackURL) == "" {
		return nil
	}
	callbackURL := strings.TrimSpace(result.CallbackURL)
	if strings.HasPrefix(callbackURL, "https://") {
		return s.post(ctx, callbackURL, result)
	}
	return nil
}

func (s HTTPCallbackSender) post(ctx context.Context, callbackURL string, result reliabletask.ExternalInteractionResult) error {
	client := s.Client
	if client == nil {
		client = http.DefaultClient
	}
	body, err := json.Marshal(map[string]any{
		"requestId":         result.RequestID,
		"operation":         result.Operation,
		"status":            result.Status,
		"provider":          result.Provider,
		"providerMessageId": result.ProviderRequestID,
		"normalizedError":   result.NormalizedError,
		"retryable":         result.Retryable,
		"timestamp":         result.OccurredAt.Format(time.RFC3339),
	})
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, callbackURL, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if s.Secret != "" {
		req.Header.Set("X-QWQ-Callback-Signature", s.Secret)
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("callback status %d", resp.StatusCode)
	}
	return nil
}

func providerAttemptLedger(store reliabletask.Store) reliabletask.ProviderAttemptLedgerStore {
	ledger, _ := store.(reliabletask.ProviderAttemptLedgerStore)
	return ledger
}
