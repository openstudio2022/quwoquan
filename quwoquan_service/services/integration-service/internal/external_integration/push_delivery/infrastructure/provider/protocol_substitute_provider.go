package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/runtime/reliabletask"
	generated "quwoquan_service/services/integration-service/generated/external_integration/push_delivery"
	pushapp "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
)

const ProtocolSubstituteProviderName = "push_protocol_substitute"

type ProtocolSubstitutePushProvider struct {
	endpoint string
	client   *http.Client
}

func NewProtocolSubstitutePushProvider(
	endpoint string,
	client *http.Client,
	timeout time.Duration,
) (*ProtocolSubstitutePushProvider, error) {
	endpoint = strings.TrimSpace(endpoint)
	parsed, err := url.ParseRequestURI(endpoint)
	if err != nil || parsed.Host == "" || parsed.Scheme != "https" {
		return nil, errors.New("push protocol substitute endpoint is invalid")
	}
	if timeout <= 0 {
		return nil, errors.New("push protocol substitute timeout must be positive")
	}
	if client == nil {
		client = &http.Client{Timeout: timeout}
	}
	return &ProtocolSubstitutePushProvider{
		endpoint: endpoint,
		client:   client,
	}, nil
}

func (p *ProtocolSubstitutePushProvider) Send(
	ctx context.Context,
	request reliabletask.ExternalInteractionRequest,
	_ reliabletask.ReliableAsyncTask,
) (reliabletask.ExternalInteractionResult, error) {
	payload, err := json.Marshal(map[string]string{
		"requestId":      request.RequestID,
		"operation":      request.Operation,
		"idempotencyKey": request.IdempotencyKey,
		"payloadDigest":  request.PayloadDigest,
	})
	if err != nil {
		return reliabletask.ExternalInteractionResult{}, err
	}
	httpRequest, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		p.endpoint,
		bytes.NewReader(payload),
	)
	if err != nil {
		return reliabletask.ExternalInteractionResult{}, err
	}
	httpRequest.Header.Set("Content-Type", "application/json")
	response, err := p.client.Do(httpRequest)
	if err != nil {
		return p.failure(
			request,
			generated.ErrPushProviderTimeout.Error(),
			true,
			err,
		)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusAccepted &&
		response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		code := generated.ErrPushProviderRejected.Error()
		retryable := response.StatusCode == http.StatusTooManyRequests ||
			response.StatusCode >= http.StatusInternalServerError
		if response.StatusCode == http.StatusTooManyRequests {
			code = generated.ErrPushProviderRateLimited.Error()
		}
		return p.failure(
			request,
			code,
			retryable,
			fmt.Errorf("push protocol substitute status=%d", response.StatusCode),
		)
	}
	var receipt struct {
		ProviderRequestID string `json:"providerRequestId"`
	}
	if err := json.NewDecoder(
		io.LimitReader(response.Body, 64<<10),
	).Decode(&receipt); err != nil ||
		strings.TrimSpace(receipt.ProviderRequestID) == "" {
		return p.failure(
			request,
			generated.ErrPushProviderRejected.Error(),
			true,
			errors.New("push protocol substitute response is invalid"),
		)
	}
	return reliabletask.ExternalInteractionResult{
		RequestID:         request.RequestID,
		Operation:         request.Operation,
		Status:            reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:          ProtocolSubstituteProviderName,
		ProviderRequestID: receipt.ProviderRequestID,
		OccurredAt:        time.Now().UTC(),
	}, nil
}

func (p *ProtocolSubstitutePushProvider) failure(
	request reliabletask.ExternalInteractionRequest,
	code string,
	retryable bool,
	cause error,
) (reliabletask.ExternalInteractionResult, error) {
	failure := &pushapp.PushProviderFailure{
		Code:      code,
		Provider:  ProtocolSubstituteProviderName,
		Retryable: retryable,
		Cause:     cause,
	}
	return reliabletask.ExternalInteractionResult{
		RequestID:       request.RequestID,
		Operation:       request.Operation,
		Status:          reliabletask.ExternalInteractionStatusFailed,
		Provider:        ProtocolSubstituteProviderName,
		NormalizedError: code,
		Retryable:       retryable,
		OccurredAt:      time.Now().UTC(),
	}, failure
}

var _ reliabletask.ExternalProvider = (*ProtocolSubstitutePushProvider)(nil)
