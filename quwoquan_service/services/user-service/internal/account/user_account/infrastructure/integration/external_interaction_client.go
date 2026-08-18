package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
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
	templateID, err := smsOTPTemplateID(req.Platform)
	if err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
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
			"templateId":      templateID,
			"platform":        strings.TrimSpace(req.Platform),
			"requestRef":      strings.TrimSpace(req.RequestRef),
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

func smsOTPTemplateID(platform string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(platform)) {
	case "ios":
		return "sms_otp_login_ios_domain_bound", nil
	case "android":
		return "sms_otp_login_android_retriever", nil
	case "web":
		return "sms_otp_login_web", nil
	case "acceptance":
		return "sms_otp_login_acceptance", nil
	default:
		return "", fmt.Errorf("unsupported otp client platform")
	}
}

func (c *ExternalInteractionClient) GetSMSOTPDeliveryReadiness(
	ctx context.Context,
) (application.SMSOTPDeliveryReadiness, error) {
	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		c.baseURL+serviceclients.IntegrationSmsOtpDeliveryReadinessPath,
		nil,
	)
	if err != nil {
		return application.SMSOTPDeliveryReadiness{}, err
	}
	serviceToken, err := c.signer.Sign(rtauth.TokenSubject{
		AccountID: "service:user-service",
		Roles:     []string{"service"},
		Scopes: []string{
			serviceclients.IntegrationSmsOtpDeliveryReadinessScope,
		},
	})
	if err != nil {
		return application.SMSOTPDeliveryReadiness{}, fmt.Errorf(
			"sign SMS OTP readiness principal: %w",
			err,
		)
	}
	req.Header.Set("Authorization", "Bearer "+serviceToken)
	resp, err := c.client.Do(req)
	if err != nil {
		return application.SMSOTPDeliveryReadiness{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return application.SMSOTPDeliveryReadiness{}, fmt.Errorf(
			"integration SMS OTP readiness status %d",
			resp.StatusCode,
		)
	}
	var readiness struct {
		Availability      string `json:"availability"`
		RetryAfterSeconds int    `json:"retryAfterSeconds"`
	}
	decoder := json.NewDecoder(io.LimitReader(resp.Body, 4096))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&readiness); err != nil {
		return application.SMSOTPDeliveryReadiness{}, fmt.Errorf(
			"decode integration SMS OTP readiness: %w",
			err,
		)
	}
	if readiness.Availability != "ready" &&
		readiness.Availability != "temporarily_unavailable" {
		return application.SMSOTPDeliveryReadiness{}, fmt.Errorf(
			"integration SMS OTP readiness availability is invalid",
		)
	}
	if readiness.RetryAfterSeconds < 0 ||
		(readiness.Availability == "ready" && readiness.RetryAfterSeconds != 0) ||
		(readiness.Availability == "temporarily_unavailable" &&
			readiness.RetryAfterSeconds == 0) {
		return application.SMSOTPDeliveryReadiness{}, fmt.Errorf(
			"integration SMS OTP readiness retry delay is invalid",
		)
	}
	return application.SMSOTPDeliveryReadiness{
		Availability:      readiness.Availability,
		RetryAfterSeconds: readiness.RetryAfterSeconds,
	}, nil
}
