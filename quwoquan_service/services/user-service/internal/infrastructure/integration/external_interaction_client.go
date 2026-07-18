package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/user-service/internal/application"
)

type ExternalInteractionClient struct {
	baseURL string
	client  *http.Client
	env     string
	signer  *rtauth.Signer
}

func NewExternalInteractionClient(baseURL string, env string, client *http.Client, signer *rtauth.Signer) (*ExternalInteractionClient, error) {
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
	if signer == nil {
		return nil, fmt.Errorf("integration service principal signer is required")
	}
	return &ExternalInteractionClient{
		baseURL: normalized,
		client:  client,
		env:     env,
		signer:  signer,
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
			"codeRef":         req.CodeRef,
			"phoneHash":       req.PhoneHash,
			"maskedRecipient": req.MaskedPhone,
			"templateId":      "sms_otp_login",
		},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/integrations/external-requests", bytes.NewReader(body))
	if err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	serviceToken, err := c.signer.Sign(rtauth.TokenSubject{
		AccountID: "service:user-service",
		Roles:     []string{"service"},
		Scopes:    []string{"integration.external_interaction.submit"},
	})
	if err != nil {
		return application.ExternalInteractionAccepted{}, fmt.Errorf("sign integration service principal: %w", err)
	}
	httpReq.Header.Set("Authorization", "Bearer "+serviceToken)
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
