package provider

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/runtime/reliabletask"
)

type HTTPCallbackSender struct {
	client *http.Client
	secret string
}

func NewHTTPCallbackSender(client *http.Client, secret string) (*HTTPCallbackSender, error) {
	if client == nil {
		return nil, fmt.Errorf("external interaction callback observed HTTP client is required")
	}
	return &HTTPCallbackSender{
		client: client,
		secret: strings.TrimSpace(secret),
	}, nil
}

func (s *HTTPCallbackSender) SendExternalInteractionResult(
	ctx context.Context,
	result reliabletask.ExternalInteractionResult,
) error {
	if strings.TrimSpace(result.RequestID) == "" {
		return fmt.Errorf("external interaction callback requestId is required")
	}
	callbackURL := strings.TrimSpace(result.CallbackURL)
	if callbackURL == "" {
		return nil
	}
	parsed, err := url.Parse(callbackURL)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" || parsed.User != nil {
		return fmt.Errorf("external interaction callback URL must be an absolute https URL")
	}
	if s.secret == "" {
		return fmt.Errorf("external interaction callback secret is required when callbackUrl is set")
	}
	body, err := json.Marshal(callbackPayload{
		RequestID:         result.RequestID,
		Operation:         result.Operation,
		Status:            result.Status,
		Provider:          result.Provider,
		ProviderMessageID: result.ProviderRequestID,
		NormalizedError:   result.NormalizedError,
		Retryable:         result.Retryable,
		Timestamp:         result.OccurredAt.UTC().Format(time.RFC3339),
	})
	if err != nil {
		return fmt.Errorf("encode external interaction callback: %w", err)
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		parsed.String(),
		bytes.NewReader(body),
	)
	if err != nil {
		return fmt.Errorf("build external interaction callback: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-QWQ-Request-ID", result.RequestID)
	mac := hmac.New(sha256.New, []byte(s.secret))
	_, _ = mac.Write(body)
	request.Header.Set(
		"X-QWQ-Callback-Signature",
		"sha256="+hex.EncodeToString(mac.Sum(nil)),
	)
	response, err := s.client.Do(request)
	if err != nil {
		return fmt.Errorf("send external interaction callback: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return fmt.Errorf("external interaction callback status %d", response.StatusCode)
	}
	return nil
}

type callbackPayload struct {
	RequestID         string `json:"requestId"`
	Operation         string `json:"operation"`
	Status            string `json:"status"`
	Provider          string `json:"provider"`
	ProviderMessageID string `json:"providerMessageId"`
	NormalizedError   string `json:"normalizedError,omitempty"`
	Retryable         bool   `json:"retryable"`
	Timestamp         string `json:"timestamp"`
}
