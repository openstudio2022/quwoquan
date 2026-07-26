package reliabletask

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

const (
	ExternalInteractionOperationSmsOTP      = "sms_otp.send"
	ExternalInteractionOperationPush        = "push_delivery.send"
	ExternalInteractionOperationOneTapPhone = "one_tap_phone.resolve"
	ExternalInteractionOperationWebhook     = "webhook.deliver"

	ExternalInteractionStatusAccepted        = "accepted"
	ExternalInteractionStatusPendingDispatch = "pending_dispatch"
	ExternalInteractionStatusSentUnconfirmed = "sent_unconfirmed"
	ExternalInteractionStatusDelivered       = "delivered"
	ExternalInteractionStatusFailed          = "failed"
	ExternalInteractionStatusDeadLetter      = "dead_letter"

	ExternalInteractionTaskPrefix = "integration."
)

type ExternalInteractionRequest struct {
	RequestID      string
	Operation      string
	Tenant         string
	Env            string
	IdempotencyKey string
	PayloadRef     string
	PayloadDigest  string
	Sensitivity    string
	ExpiresAt      time.Time
	Payload        map[string]string
}

type ExternalInteractionAccepted struct {
	RequestID  string    `json:"requestId"`
	Status     string    `json:"status"`
	AcceptedAt time.Time `json:"acceptedAt"`
}

type ExternalInteractionResult struct {
	RequestID         string
	Operation         string
	Status            string
	Provider          string
	ProviderRequestID string
	NormalizedError   string
	Retryable         bool
	OccurredAt        time.Time
}

type ProviderPolicy struct {
	Providers   []string
	Timeout     time.Duration
	RetryPolicy RetryPolicy
}

type ProviderAttemptRecord struct {
	AttemptID             string            `bson:"_id" json:"attemptId"`
	RequestID             string            `bson:"requestId" json:"requestId"`
	TaskID                string            `bson:"taskId" json:"taskId"`
	Operation             string            `bson:"operation" json:"operation"`
	Provider              string            `bson:"provider" json:"provider"`
	ProviderRequestID     string            `bson:"providerRequestId,omitempty" json:"providerRequestId,omitempty"`
	ProviderRequestDigest string            `bson:"providerRequestDigest" json:"providerRequestDigest"`
	MaskedRecipient       string            `bson:"maskedRecipient,omitempty" json:"maskedRecipient,omitempty"`
	LatencyMs             int64             `bson:"latencyMs" json:"latencyMs"`
	Status                string            `bson:"status" json:"status"`
	NormalizedError       string            `bson:"normalizedError,omitempty" json:"normalizedError,omitempty"`
	Retryable             bool              `bson:"retryable" json:"retryable"`
	RecoveryAction        string            `bson:"recoveryAction" json:"recoveryAction"`
	Attributes            map[string]string `bson:"attributes,omitempty" json:"attributes,omitempty"`
	CreatedAt             time.Time         `bson:"createdAt" json:"createdAt"`
}

type ExternalInteractionResultOutboxRecord struct {
	EventID               string     `bson:"_id" json:"eventId"`
	RequestID             string     `bson:"requestId" json:"requestId"`
	Operation             string     `bson:"operation" json:"operation"`
	ResultStatus          string     `bson:"resultStatus" json:"resultStatus"`
	Provider              string     `bson:"provider" json:"provider"`
	ProviderRequestDigest string     `bson:"providerRequestDigest" json:"providerRequestDigest"`
	NormalizedError       string     `bson:"normalizedError,omitempty" json:"normalizedError,omitempty"`
	RecoveryAction        string     `bson:"recoveryAction" json:"recoveryAction"`
	OccurredAt            time.Time  `bson:"occurredAt" json:"occurredAt"`
	DeliveryStatus        string     `bson:"deliveryStatus" json:"deliveryStatus"`
	LeaseOwner            string     `bson:"leaseOwner,omitempty" json:"leaseOwner,omitempty"`
	LeaseExpiresAt        *time.Time `bson:"leaseExpiresAt,omitempty" json:"leaseExpiresAt,omitempty"`
	PublishedAt           *time.Time `bson:"publishedAt,omitempty" json:"publishedAt,omitempty"`
	CreatedAt             time.Time  `bson:"createdAt" json:"createdAt"`
	UpdatedAt             time.Time  `bson:"updatedAt" json:"updatedAt"`
}

const (
	ExternalInteractionResultOutboxPending    = "pending"
	ExternalInteractionResultOutboxPublishing = "publishing"
	ExternalInteractionResultOutboxPublished  = "published"
)

type ProviderAttemptLedgerStore interface {
	RecordProviderAttempt(ctx context.Context, record ProviderAttemptRecord) (ProviderAttemptRecord, error)
	ListProviderAttempts(ctx context.Context, requestID string) ([]ProviderAttemptRecord, error)
}

// ProviderAttemptResultOutboxStore atomically records one immutable provider
// attempt and its separately mutable result-relay outbox row. A transport retry
// must never invoke the provider again.
type ProviderAttemptResultOutboxStore interface {
	ProviderAttemptLedgerStore
	RecordProviderAttemptWithResultOutbox(
		ctx context.Context,
		record ProviderAttemptRecord,
	) (ProviderAttemptRecord, error)
}

type ExternalProvider interface {
	Send(ctx context.Context, request ExternalInteractionRequest, task ReliableAsyncTask) (ExternalInteractionResult, error)
}

type ExternalInteractionDispatcher struct {
	Writer           TaskOutboxWriter
	TaskPayloadAllow []string
	Now              func() time.Time
}

func (d ExternalInteractionDispatcher) Submit(ctx context.Context, req ExternalInteractionRequest) (ExternalInteractionAccepted, error) {
	if d.Writer.Store == nil {
		return ExternalInteractionAccepted{}, ErrStoreRequired
	}
	if err := req.Validate(); err != nil {
		return ExternalInteractionAccepted{}, err
	}
	now := time.Now().UTC()
	if d.Now != nil {
		now = d.Now().UTC()
	}
	payload := req.TaskPayload()
	allow := d.TaskPayloadAllow
	if len(allow) == 0 {
		allow = DefaultExternalInteractionPayloadAllowlist()
	}
	if _, err := d.Writer.AddTask(ctx, DeclareTaskRequest{
		TaskType:        TaskTypeForExternalInteraction(req.Operation),
		OwnerDomain:     "integration",
		AggregateType:   "external_interaction",
		AggregateID:     req.RequestID,
		DedupeKey:       req.Operation + ":" + req.IdempotencyKey,
		IdempotencyKey:  req.IdempotencyKey,
		PartitionKey:    req.IdempotencyKey,
		Payload:         payload,
		PayloadAllow:    allow,
		Trigger:         "external_interaction.accepted",
		StartAt:         now,
		MaxDelayUntil:   req.ExpiresAt,
		MergeWindow:     time.Minute,
		CreatedByModule: "integration.external_interaction.dispatcher",
	}); err != nil {
		return ExternalInteractionAccepted{}, err
	}
	return ExternalInteractionAccepted{
		RequestID:  req.RequestID,
		Status:     ExternalInteractionStatusAccepted,
		AcceptedAt: now,
	}, nil
}

type ExternalInteractionWorker struct {
	Worker    Worker
	Providers map[string]ExternalProvider
	Policies  map[string]ProviderPolicy
	Ledger    ProviderAttemptResultOutboxStore
	Now       func() time.Time
}

func (w ExternalInteractionWorker) ProcessOne(ctx context.Context) (bool, error) {
	return w.Worker.ProcessOne(ctx, w.handleTask)
}

func (w ExternalInteractionWorker) handleTask(ctx context.Context, task ReliableAsyncTask) error {
	req := ExternalInteractionRequestFromTask(task)
	policy := w.policyForOperation(req.Operation)
	providers := policy.Providers
	if len(providers) == 0 {
		providers = []string{strings.TrimPrefix(task.TaskType, ExternalInteractionTaskPrefix)}
	}
	var lastErr error
	for _, providerName := range providers {
		provider := w.Providers[providerName]
		if provider == nil {
			lastErr = fmt.Errorf("external provider %s unavailable", providerName)
			continue
		}
		start := w.now()
		result, err := provider.Send(ctx, req, task)
		latency := w.now().Sub(start)
		if result.RequestID == "" {
			result.RequestID = req.RequestID
		}
		if result.Operation == "" {
			result.Operation = req.Operation
		}
		if result.Provider == "" {
			result.Provider = providerName
		}
		if result.OccurredAt.IsZero() {
			result.OccurredAt = w.now()
		}
		if err != nil && result.Status == "" {
			result.Status = ExternalInteractionStatusFailed
		}
		if err != nil && result.NormalizedError == "" {
			result.NormalizedError = err.Error()
		}
		if err == nil && result.Status == "" {
			result.Status = ExternalInteractionStatusSentUnconfirmed
		}
		// Provider synchronous responses prove acceptance only. Terminal device
		// delivery is a separate Notification presentation fact.
		if result.Status == ExternalInteractionStatusDelivered {
			result.Status = ExternalInteractionStatusSentUnconfirmed
		}
		record := ProviderAttemptRecord{
			AttemptID:         NewRecordID("attempt"),
			RequestID:         req.RequestID,
			TaskID:            task.TaskID,
			Operation:         req.Operation,
			Provider:          result.Provider,
			ProviderRequestID: result.ProviderRequestID,
			ProviderRequestDigest: ProviderRequestDigest(
				result.ProviderRequestID,
			),
			MaskedRecipient: task.Payload["maskedRecipient"],
			LatencyMs:       latency.Milliseconds(),
			Status:          result.Status,
			NormalizedError: result.NormalizedError,
			Retryable:       result.Retryable,
			RecoveryAction:  providerRecoveryAction(result),
			Attributes:      map[string]string{"idempotencyKey": req.IdempotencyKey},
			CreatedAt:       result.OccurredAt.UTC(),
		}
		if w.Ledger != nil {
			if _, ledgerErr := w.Ledger.RecordProviderAttemptWithResultOutbox(
				ctx,
				record,
			); ledgerErr != nil {
				return ledgerErr
			}
		}
		if err != nil {
			lastErr = err
			if !result.Retryable {
				break
			}
			continue
		}
		if result.Status == ExternalInteractionStatusFailed {
			lastErr = fmt.Errorf(
				"external provider %s rejected request",
				result.Provider,
			)
			if result.Retryable {
				continue
			}
			break
		}
		return nil
	}
	if lastErr == nil {
		lastErr = fmt.Errorf("external interaction %s has no provider", req.Operation)
	}
	return lastErr
}

func ProviderRequestDigest(providerRequestID string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(providerRequestID)))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func providerRecoveryAction(result ExternalInteractionResult) string {
	if result.Retryable {
		return "retry"
	}
	if result.Status == ExternalInteractionStatusFailed {
		return "escalate"
	}
	return "none"
}

func (w ExternalInteractionWorker) policyForOperation(operation string) ProviderPolicy {
	if w.Policies == nil {
		return ProviderPolicy{RetryPolicy: DefaultRetryPolicy()}
	}
	policy := w.Policies[operation]
	if policy.RetryPolicy.MaxAttempts <= 0 {
		policy.RetryPolicy = DefaultRetryPolicy()
	}
	return policy
}

func (w ExternalInteractionWorker) now() time.Time {
	if w.Now != nil {
		return w.Now().UTC()
	}
	return time.Now().UTC()
}

func (r ExternalInteractionRequest) Validate() error {
	if strings.TrimSpace(r.RequestID) == "" {
		return fmt.Errorf("requestId is required")
	}
	if strings.TrimSpace(r.Operation) == "" {
		return fmt.Errorf("operation is required")
	}
	if strings.TrimSpace(r.IdempotencyKey) == "" {
		return fmt.Errorf("idempotencyKey is required")
	}
	if r.ExpiresAt.IsZero() {
		return fmt.Errorf("expiresAt is required")
	}
	switch r.Operation {
	case ExternalInteractionOperationSmsOTP,
		ExternalInteractionOperationPush,
		ExternalInteractionOperationOneTapPhone,
		ExternalInteractionOperationWebhook:
		return nil
	default:
		return fmt.Errorf("unsupported external interaction operation %s", r.Operation)
	}
}

func (r ExternalInteractionRequest) TaskPayload() map[string]string {
	payload := CloneStringMap(r.Payload)
	payload["requestId"] = r.RequestID
	payload["operation"] = r.Operation
	payload["tenant"] = r.Tenant
	payload["env"] = r.Env
	payload["idempotencyKey"] = r.IdempotencyKey
	payload["payloadRef"] = r.PayloadRef
	payload["payloadDigest"] = r.PayloadDigest
	payload["sensitivity"] = r.Sensitivity
	payload["expiresAt"] = r.ExpiresAt.UTC().Format(time.RFC3339)
	return payload
}

func ExternalInteractionRequestFromTask(task ReliableAsyncTask) ExternalInteractionRequest {
	expiresAt, _ := time.Parse(time.RFC3339, task.Payload["expiresAt"])
	payload := CloneStringMap(task.Payload)
	return ExternalInteractionRequest{
		RequestID:      task.Payload["requestId"],
		Operation:      task.Payload["operation"],
		Tenant:         task.Payload["tenant"],
		Env:            task.Payload["env"],
		IdempotencyKey: task.Payload["idempotencyKey"],
		PayloadRef:     task.Payload["payloadRef"],
		PayloadDigest:  task.Payload["payloadDigest"],
		Sensitivity:    task.Payload["sensitivity"],
		ExpiresAt:      expiresAt,
		Payload:        payload,
	}
}

func TaskTypeForExternalInteraction(operation string) string {
	return ExternalInteractionTaskPrefix + strings.TrimSpace(operation)
}

func DefaultExternalInteractionPayloadAllowlist() []string {
	return []string{
		"requestId",
		"operation",
		"tenant",
		"env",
		"idempotencyKey",
		"payloadRef",
		"payloadDigest",
		"sensitivity",
		"expiresAt",
		"challengeId",
		"phoneHash",
		"maskedRecipient",
		"templateId",
		"notificationId",
		"recipientId",
		"providerHint",
		"deeplink",
	}
}
