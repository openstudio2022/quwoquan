package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/services/user-service/internal/application"
)

type ExternalInteractionClient struct {
	baseURL string
	client  *http.Client
	env     string
}

func NewExternalInteractionClient(baseURL string, env string, client *http.Client) (*ExternalInteractionClient, error) {
	normalized := strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if normalized == "" {
		normalized = "https://integration-service.local"
	}
	if !strings.HasPrefix(normalized, "https://") {
		return nil, fmt.Errorf("integration service base url must use https")
	}
	if client == nil {
		client = &http.Client{Timeout: 3 * time.Second}
	}
	return &ExternalInteractionClient{
		baseURL: normalized,
		client:  client,
		env:     env,
	}, nil
}

func (c *ExternalInteractionClient) SubmitSMSOTP(ctx context.Context, req application.SMSOTPDispatchRequest) (application.ExternalInteractionAccepted, error) {
	payload := map[string]any{
		"requestId":      req.RequestID,
		"operation":      "sms_otp.send",
		"tenant":         "quwoquan",
		"env":            c.env,
		"idempotencyKey": req.IdempotencyKey,
		"callbackEvent":  "SmsOtpDeliverySucceeded",
		"payloadRef":     "otp_challenge:" + req.ChallengeID,
		"payloadDigest":  req.PhoneHash,
		"sensitivity":    "secret",
		"expiresAt":      req.ExpiresAt.UTC().Format(time.RFC3339),
		"payload": map[string]string{
			"challengeId":     req.ChallengeID,
			"phoneHash":       req.PhoneHash,
			"maskedRecipient": req.MaskedPhone,
			"templateId":      "sms_otp_login",
		},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/integrations/external-requests", bytes.NewReader(body))
	if err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.client.Do(httpReq)
	if err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusAccepted {
		return application.ExternalInteractionAccepted{}, fmt.Errorf("integration external request status %d", resp.StatusCode)
	}
	var accepted application.ExternalInteractionAccepted
	if err := json.NewDecoder(resp.Body).Decode(&accepted); err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
	return accepted, nil
}
