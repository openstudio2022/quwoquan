package integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"hash/fnv"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	serviceclients "quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	rerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/notification-service/internal/application"
	notification "quwoquan_service/services/notification-service/internal/domain/notification"
)

const integrationResponseBodyLimit = 1 << 20

type ExternalInteractionDeliveryConfig struct {
	BaseURL     string
	Credentials rtauth.ServiceAuthorizationProvider
	Environment string
	Timeout     time.Duration
}

type ExternalInteractionDeliveryAdapter struct {
	endpoint    string
	credentials rtauth.ServiceAuthorizationProvider
	environment string
	timeout     time.Duration
	client      *http.Client
}

type DeliveryError struct {
	Code           string
	StatusCode     int
	RecoveryAction failures.RecoveryAction
	RequestID      string
	TraceID        string
	Cause          error
}

func (e *DeliveryError) Error() string {
	if e == nil {
		return ""
	}
	if e.StatusCode > 0 {
		return fmt.Sprintf(
			"notification integration delivery failed with %s (status=%d recoveryAction=%s requestId=%s traceId=%s)",
			e.Code,
			e.StatusCode,
			e.RecoveryAction,
			e.RequestID,
			e.TraceID,
		)
	}
	return fmt.Sprintf(
		"notification integration delivery failed with %s (recoveryAction=%s requestId=%s traceId=%s)",
		e.Code,
		e.RecoveryAction,
		e.RequestID,
		e.TraceID,
	)
}

func (e *DeliveryError) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Cause
}

func NewExternalInteractionDeliveryAdapter(
	cfg ExternalInteractionDeliveryConfig,
	client *http.Client,
) (*ExternalInteractionDeliveryAdapter, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(cfg.BaseURL), "/")
	parsed, err := url.Parse(baseURL)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" ||
		parsed.User != nil {
		return nil, fmt.Errorf("notification integration base URL must be absolute http or https")
	}
	if cfg.Credentials == nil {
		return nil, fmt.Errorf("notification integration service credentials are required")
	}
	environment := strings.TrimSpace(cfg.Environment)
	if !validEnvironment(environment) {
		return nil, fmt.Errorf("notification integration environment must be alpha|beta|gamma|prod")
	}
	if cfg.Timeout <= 0 {
		return nil, fmt.Errorf("notification integration timeout must be positive")
	}
	if client == nil {
		return nil, fmt.Errorf("notification integration observed HTTP client is required")
	}
	return &ExternalInteractionDeliveryAdapter{
		endpoint:    baseURL + serviceclients.IntegrationExternalRequestsPath,
		credentials: cfg.Credentials,
		environment: environment,
		timeout:     cfg.Timeout,
		client:      client,
	}, nil
}

func (a *ExternalInteractionDeliveryAdapter) Deliver(
	ctx context.Context,
	notification reliabletask.NotificationOutboxRecord,
	recipientID string,
) (int64, error) {
	if a == nil || a.client == nil {
		return 0, &DeliveryError{
			Code:           serviceclients.IntegrationInternalErrorCode,
			RecoveryAction: failures.RecoveryActionSurface,
			Cause:          errors.New("notification integration delivery adapter is not initialized"),
		}
	}
	if strings.TrimSpace(notification.NotificationID) == "" ||
		strings.TrimSpace(recipientID) == "" {
		return 0, &DeliveryError{
			Code:           serviceclients.IntegrationInternalErrorCode,
			RecoveryAction: failures.RecoveryActionSurface,
			Cause:          errors.New("delivery job id and recipientId are required"),
		}
	}
	if notification.EventType != application.NotificationPushRequestedEvent {
		return 0, &DeliveryError{
			Code:           serviceclients.IntegrationUnsupportedOperationCode,
			RecoveryAction: failures.RecoveryActionSurface,
			Cause: fmt.Errorf(
				"notification event type %s is not an external push request",
				notification.EventType,
			),
		}
	}

	requestID := externalRequestID(notification.NotificationID, recipientID)
	payload := map[string]string{
		"jobId":          notification.NotificationID,
		"notificationId": notification.SubjectNotificationID,
		"recipientId":    recipientID,
	}
	copyAllowed(payload, notification.Payload, "providerHint")
	copyAllowed(payload, notification.Payload, "deeplink")
	bodyPayload := externalInteractionRequest{
		RequestID:      requestID,
		Operation:      reliabletask.ExternalInteractionOperationPush,
		Tenant:         "quwoquan",
		Environment:    a.environment,
		IdempotencyKey: requestID,
		CallbackEvent:  "PushDeliverySucceeded",
		PayloadRef:     "notification-delivery-job:" + notification.NotificationID,
		PayloadDigest:  notificationDigest(notification, recipientID),
		Sensitivity:    "private",
		ExpiresAt:      time.Now().UTC().Add(5 * time.Minute).Format(time.RFC3339),
		Payload:        payload,
	}
	accepted, err := a.submit(ctx, bodyPayload)
	if err != nil {
		return 0, err
	}
	return acceptedSequence(accepted.RequestID), nil
}

func (a *ExternalInteractionDeliveryAdapter) SubmitIncomingCall(
	ctx context.Context,
	job notification.IncomingCallDeliveryJob,
) (string, error) {
	return a.submitIncomingCallPush(ctx, job, "ring")
}

func (a *ExternalInteractionDeliveryAdapter) SubmitIncomingCallCancellation(
	ctx context.Context,
	job notification.IncomingCallDeliveryJob,
) (string, error) {
	return a.submitIncomingCallPush(ctx, job, "cancel")
}

func (a *ExternalInteractionDeliveryAdapter) submitIncomingCallPush(
	ctx context.Context,
	job notification.IncomingCallDeliveryJob,
	action string,
) (string, error) {
	if a == nil || a.client == nil {
		return "", &DeliveryError{
			Code:           serviceclients.IntegrationInternalErrorCode,
			RecoveryAction: failures.RecoveryActionSurface,
			Cause:          errors.New("notification integration delivery adapter is not initialized"),
		}
	}
	if strings.TrimSpace(job.ID) == "" ||
		strings.TrimSpace(job.DestinationRef) == "" ||
		strings.TrimSpace(job.DeliveryKey) == "" ||
		strings.TrimSpace(job.CallID) == "" ||
		strings.TrimSpace(job.TargetPersonaID) == "" ||
		job.ExpiresAt.IsZero() {
		return "", &DeliveryError{
			Code:           serviceclients.IntegrationInternalErrorCode,
			RecoveryAction: failures.RecoveryActionSurface,
			Cause:          errors.New("incoming call delivery job is incomplete"),
		}
	}
	occurredAt := job.CreatedAt.UTC()
	callbackEvent := "IncomingCallPushDeliveryResult"
	if action == "cancel" {
		if job.CancellationOccurredAt == nil ||
			strings.TrimSpace(job.CancellationEventID) == "" {
			return "", &DeliveryError{
				Code:           serviceclients.IntegrationInternalErrorCode,
				RecoveryAction: failures.RecoveryActionSurface,
				Cause:          errors.New("incoming call cancellation job is incomplete"),
			}
		}
		occurredAt = job.CancellationOccurredAt.UTC()
		callbackEvent = "IncomingCallCancellationPushDeliveryResult"
	}
	requestID := incomingCallExternalRequestID(
		job.DeliveryKey,
		job.DestinationRef,
		action,
	)
	payload := map[string]string{
		"action":          action,
		"endpointRef":     job.DestinationRef,
		"deliveryKey":     job.DeliveryKey,
		"callId":          job.CallID,
		"targetPersonaId": job.TargetPersonaID,
		"callType":        job.CallType,
		"callerName":      job.CallerName,
		"sourceLabel":     job.SourceLabel,
		"trustRelation":   job.TrustRelation,
		"expiresAt":       job.ExpiresAt.UTC().Format(time.RFC3339),
		"occurredAt":      occurredAt.Format(time.RFC3339),
	}
	bodyPayload := externalInteractionRequest{
		RequestID:      requestID,
		Operation:      reliabletask.ExternalInteractionOperationPush,
		Tenant:         "quwoquan",
		Environment:    a.environment,
		IdempotencyKey: requestID,
		CallbackEvent:  callbackEvent,
		PayloadRef:     "incoming-call-delivery-job:" + job.ID,
		PayloadDigest:  incomingCallDigest(job, action, occurredAt),
		Sensitivity:    "private",
		ExpiresAt:      job.ExpiresAt.UTC().Format(time.RFC3339),
		Payload:        payload,
	}
	accepted, err := a.submit(ctx, bodyPayload)
	if err != nil {
		return "", err
	}
	return accepted.RequestID, nil
}

func (a *ExternalInteractionDeliveryAdapter) submit(
	ctx context.Context,
	bodyPayload externalInteractionRequest,
) (reliabletask.ExternalInteractionAccepted, error) {
	requestID := bodyPayload.RequestID
	body, err := json.Marshal(bodyPayload)
	if err != nil {
		return reliabletask.ExternalInteractionAccepted{}, &DeliveryError{
			Code:           serviceclients.IntegrationInternalErrorCode,
			RecoveryAction: failures.RecoveryActionSurface,
			RequestID:      requestID,
			Cause:          err,
		}
	}
	requestCtx, cancel := context.WithTimeout(ctx, a.timeout)
	defer cancel()
	authorization, err := a.credentials.AuthorizationHeader(requestCtx)
	if err != nil {
		return reliabletask.ExternalInteractionAccepted{}, &DeliveryError{
			Code:           serviceclients.IntegrationInternalErrorCode,
			RecoveryAction: failures.RecoveryActionRetry,
			RequestID:      requestID,
			Cause:          fmt.Errorf("issue integration service credential: %w", err),
		}
	}
	request, err := http.NewRequestWithContext(
		requestCtx,
		http.MethodPost,
		a.endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		return reliabletask.ExternalInteractionAccepted{}, &DeliveryError{
			Code:           serviceclients.IntegrationInternalErrorCode,
			RecoveryAction: failures.RecoveryActionSurface,
			RequestID:      requestID,
			Cause:          err,
		}
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", requestID)
	request.Header.Set("X-QWQ-Request-ID", requestID)

	response, err := a.client.Do(request)
	if err != nil {
		code := serviceclients.IntegrationProviderRejectedCode
		if isTimeout(err) {
			code = serviceclients.IntegrationProviderTimeoutCode
		}
		return reliabletask.ExternalInteractionAccepted{}, &DeliveryError{
			Code:           code,
			RecoveryAction: failures.RecoveryActionRetry,
			RequestID:      requestID,
			Cause:          err,
		}
	}
	defer response.Body.Close()
	raw, readErr := io.ReadAll(io.LimitReader(response.Body, integrationResponseBodyLimit))
	if readErr != nil {
		return reliabletask.ExternalInteractionAccepted{}, &DeliveryError{
			Code:           serviceclients.IntegrationProviderRejectedCode,
			StatusCode:     response.StatusCode,
			RecoveryAction: failures.RecoveryActionRetry,
			RequestID:      requestID,
			Cause:          readErr,
		}
	}
	if response.StatusCode != http.StatusAccepted {
		return reliabletask.ExternalInteractionAccepted{},
			decodeRemoteFailure(response.StatusCode, raw, requestID)
	}
	var accepted reliabletask.ExternalInteractionAccepted
	if err := json.Unmarshal(raw, &accepted); err != nil {
		return reliabletask.ExternalInteractionAccepted{}, &DeliveryError{
			Code:           serviceclients.IntegrationProviderRejectedCode,
			StatusCode:     response.StatusCode,
			RecoveryAction: failures.RecoveryActionRetry,
			RequestID:      requestID,
			Cause:          err,
		}
	}
	if strings.TrimSpace(accepted.RequestID) == "" ||
		accepted.RequestID != requestID ||
		accepted.Status != reliabletask.ExternalInteractionStatusAccepted {
		return reliabletask.ExternalInteractionAccepted{}, &DeliveryError{
			Code:           serviceclients.IntegrationProviderRejectedCode,
			StatusCode:     response.StatusCode,
			RecoveryAction: failures.RecoveryActionRetry,
			RequestID:      requestID,
			Cause:          errors.New("integration response is missing a valid accepted request"),
		}
	}
	return accepted, nil
}

type externalInteractionRequest struct {
	RequestID      string            `json:"requestId"`
	Operation      string            `json:"operation"`
	Tenant         string            `json:"tenant"`
	Environment    string            `json:"env"`
	IdempotencyKey string            `json:"idempotencyKey"`
	CallbackEvent  string            `json:"callbackEvent"`
	PayloadRef     string            `json:"payloadRef"`
	PayloadDigest  string            `json:"payloadDigest"`
	Sensitivity    string            `json:"sensitivity"`
	ExpiresAt      string            `json:"expiresAt"`
	Payload        map[string]string `json:"payload"`
}

func decodeRemoteFailure(status int, raw []byte, fallbackRequestID string) error {
	var response rerrors.ErrorResponse
	decodeErr := json.Unmarshal(raw, &response)
	code := strings.TrimSpace(response.Code)
	if code == "" {
		code = serviceclients.IntegrationProviderRejectedCode
	}
	return &DeliveryError{
		Code:           code,
		StatusCode:     status,
		RecoveryAction: recoveryActionFromRemote(response.Recovery.Action, status),
		RequestID:      firstNonEmpty(response.RequestID, fallbackRequestID),
		TraceID:        strings.TrimSpace(response.TraceID),
		Cause:          decodeErr,
	}
}

func externalRequestID(notificationID string, recipientID string) string {
	sum := sha256.Sum256([]byte(notificationID + "\x00" + recipientID))
	return "notification-" + hex.EncodeToString(sum[:16])
}

func notificationDigest(
	notification reliabletask.NotificationOutboxRecord,
	recipientID string,
) string {
	payload, _ := json.Marshal(struct {
		JobID          string            `json:"jobId"`
		NotificationID string            `json:"notificationId"`
		EventType      string            `json:"eventType"`
		AggregateID    string            `json:"aggregateId"`
		RecipientID    string            `json:"recipientId"`
		Payload        map[string]string `json:"payload"`
	}{
		JobID:          notification.NotificationID,
		NotificationID: notification.SubjectNotificationID,
		EventType:      notification.EventType,
		AggregateID:    notification.AggregateID,
		RecipientID:    recipientID,
		Payload:        notification.Payload,
	})
	sum := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(sum[:])
}

func incomingCallExternalRequestID(
	deliveryKey string,
	endpointRef string,
	action string,
) string {
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(deliveryKey) + "\x00" +
			strings.TrimSpace(endpointRef) + "\x00" +
			strings.TrimSpace(action),
	))
	return "incoming-call-" + hex.EncodeToString(sum[:16])
}

func incomingCallDigest(
	job notification.IncomingCallDeliveryJob,
	action string,
	occurredAt time.Time,
) string {
	payload, _ := json.Marshal(struct {
		Action          string `json:"action"`
		EndpointRef     string `json:"endpointRef"`
		DeliveryKey     string `json:"deliveryKey"`
		CallID          string `json:"callId"`
		TargetPersonaID string `json:"targetPersonaId"`
		CallType        string `json:"callType"`
		CallerName      string `json:"callerName"`
		SourceLabel     string `json:"sourceLabel"`
		TrustRelation   string `json:"trustRelation"`
		ExpiresAt       string `json:"expiresAt"`
		OccurredAt      string `json:"occurredAt"`
	}{
		Action:          action,
		EndpointRef:     job.DestinationRef,
		DeliveryKey:     job.DeliveryKey,
		CallID:          job.CallID,
		TargetPersonaID: job.TargetPersonaID,
		CallType:        job.CallType,
		CallerName:      job.CallerName,
		SourceLabel:     job.SourceLabel,
		TrustRelation:   job.TrustRelation,
		ExpiresAt:       job.ExpiresAt.UTC().Format(time.RFC3339),
		OccurredAt:      occurredAt.UTC().Format(time.RFC3339),
	})
	sum := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(sum[:])
}

func acceptedSequence(acceptedID string) int64 {
	hash := fnv.New64a()
	_, _ = hash.Write([]byte(acceptedID))
	sequence := int64(hash.Sum64() & uint64(^uint64(0)>>1))
	if sequence == 0 {
		return 1
	}
	return sequence
}

func copyAllowed(target map[string]string, source map[string]string, key string) {
	if value := strings.TrimSpace(source[key]); value != "" {
		target[key] = value
	}
}

func validEnvironment(value string) bool {
	switch value {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func recoveryActionFromRemote(action string, status int) failures.RecoveryAction {
	candidate := failures.RecoveryAction(strings.TrimSpace(action))
	switch candidate {
	case failures.RecoveryActionAbsorb,
		failures.RecoveryActionRetry,
		failures.RecoveryActionFallback,
		failures.RecoveryActionSurface,
		failures.RecoveryActionEscalate,
		failures.RecoveryActionCompensate:
		return candidate
	default:
		return recoveryActionForStatus(status)
	}
}

func recoveryActionForStatus(status int) failures.RecoveryAction {
	if status == http.StatusRequestTimeout ||
		status == http.StatusTooEarly ||
		status == http.StatusTooManyRequests ||
		status >= http.StatusInternalServerError {
		return failures.RecoveryActionRetry
	}
	return failures.RecoveryActionSurface
}

func isTimeout(err error) bool {
	if errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	var netErr net.Error
	return errors.As(err, &netErr) && netErr.Timeout()
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if normalized := strings.TrimSpace(value); normalized != "" {
			return normalized
		}
	}
	return ""
}
