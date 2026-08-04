package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	serviceclients "quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
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
	parsed, err := url.Parse(normalized)
	if err != nil || parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, fmt.Errorf("integration service base url is invalid")
	}
	switch strings.TrimSpace(env) {
	case "alpha", "beta", "gamma":
		if parsed.Scheme != "http" || parsed.Host != "integration-service:18086" || (parsed.Path != "" && parsed.Path != "/") {
			return nil, fmt.Errorf("nonprod integration service base url must be canonical internal http")
		}
	case "prod":
		if parsed.Scheme != "https" {
			return nil, fmt.Errorf("prod integration service base url must use https")
		}
	default:
		return nil, fmt.Errorf("unsupported integration service environment %q", env)
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
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+serviceclients.IntegrationExternalRequestsPath, bytes.NewReader(body))
	if err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	idempotencyKey := strings.TrimSpace(req.IdempotencyKey)
	if idempotencyKey == "" {
		return application.ExternalInteractionAccepted{}, fmt.Errorf("idempotency key is required for sms_otp.send")
	}
	httpReq.Header.Set("Idempotency-Key", idempotencyKey)
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
