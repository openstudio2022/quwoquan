package integration

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

	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

type ProtocolSubstituteCarrierPhoneResolver struct {
	endpoint string
	client   *http.Client
}

func NewProtocolSubstituteCarrierPhoneResolver(
	endpoint string,
	client *http.Client,
) (*ProtocolSubstituteCarrierPhoneResolver, error) {
	endpoint, err := validateProtocolSubstituteEndpoint(endpoint)
	if err != nil {
		return nil, err
	}
	if client == nil {
		client = &http.Client{Timeout: 3 * time.Second}
	}
	return &ProtocolSubstituteCarrierPhoneResolver{
		endpoint: endpoint,
		client:   client,
	}, nil
}

func (r *ProtocolSubstituteCarrierPhoneResolver) ResolvePhone(
	ctx context.Context,
	carrierToken string,
) (application.VerifiedCarrierPhone, error) {
	carrierToken = strings.TrimSpace(carrierToken)
	if carrierToken == "" {
		return application.VerifiedCarrierPhone{},
			sessiongenerated.AppErrorFromCarrierTokenInvalid("carrier token is required")
	}
	var response struct {
		Phone        string `json:"phone"`
		DisplayLabel string `json:"displayLabel"`
	}
	status, err := postProtocolSubstituteJSON(
		ctx,
		r.client,
		r.endpoint,
		map[string]string{"token": carrierToken},
		&response,
	)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) ||
			errors.Is(err, context.Canceled) {
			return application.VerifiedCarrierPhone{},
				sessiongenerated.AppErrorFromCarrierProviderTimeout(
					"carrier protocol substitute request timed out",
				)
		}
		return application.VerifiedCarrierPhone{},
			sessiongenerated.AppErrorFromCarrierUnavailable(
				"carrier protocol substitute request failed",
			)
	}
	if status == http.StatusBadRequest || status == http.StatusUnauthorized {
		return application.VerifiedCarrierPhone{},
			sessiongenerated.AppErrorFromCarrierTokenInvalid(
				"carrier protocol substitute rejected token",
			)
	}
	if status != http.StatusOK ||
		strings.TrimSpace(response.Phone) == "" ||
		strings.TrimSpace(response.DisplayLabel) == "" {
		return application.VerifiedCarrierPhone{},
			sessiongenerated.AppErrorFromCarrierUnavailable(
				"carrier protocol substitute response invalid",
			)
	}
	return application.VerifiedCarrierPhone{
		Phone:        response.Phone,
		DisplayLabel: response.DisplayLabel,
	}, nil
}

type ProtocolSubstituteFederatedIdentityVerifier struct {
	credentialType credentialmodel.CredentialType
	provider       string
	endpoint       string
	client         *http.Client
}

func NewProtocolSubstituteFederatedIdentityVerifier(
	credentialType credentialmodel.CredentialType,
	provider string,
	endpoint string,
	client *http.Client,
) (*ProtocolSubstituteFederatedIdentityVerifier, error) {
	endpoint, err := validateProtocolSubstituteEndpoint(endpoint)
	if err != nil {
		return nil, err
	}
	provider = strings.TrimSpace(provider)
	if provider == "" {
		return nil, errors.New("federated protocol substitute provider is required")
	}
	if client == nil {
		client = &http.Client{Timeout: 3 * time.Second}
	}
	return &ProtocolSubstituteFederatedIdentityVerifier{
		credentialType: credentialType,
		provider:       provider,
		endpoint:       endpoint,
		client:         client,
	}, nil
}

func (v *ProtocolSubstituteFederatedIdentityVerifier) Verify(
	ctx context.Context,
	authorizationCode string,
) (application.VerifiedFederatedIdentity, error) {
	authorizationCode = strings.TrimSpace(authorizationCode)
	if authorizationCode == "" {
		return application.VerifiedFederatedIdentity{},
			sessiongenerated.AppErrorFromSocialProviderUnavailable(
				"federated authorization code is required",
			)
	}
	var response struct {
		CredentialKey string `json:"credentialKey"`
		DisplayName   string `json:"displayName"`
		AvatarURL     string `json:"avatarUrl"`
	}
	status, err := postProtocolSubstituteJSON(
		ctx,
		v.client,
		v.endpoint,
		map[string]string{
			"provider": v.provider,
			"code":     authorizationCode,
		},
		&response,
	)
	if err != nil || status != http.StatusOK ||
		strings.TrimSpace(response.CredentialKey) == "" {
		return application.VerifiedFederatedIdentity{},
			sessiongenerated.AppErrorFromSocialProviderUnavailable(
				"federated protocol substitute request failed",
			)
	}
	return application.VerifiedFederatedIdentity{
		CredentialType: v.credentialType,
		CredentialKey:  response.CredentialKey,
		DisplayName:    response.DisplayName,
		AvatarURL:      response.AvatarURL,
	}, nil
}

func validateProtocolSubstituteEndpoint(value string) (string, error) {
	value = strings.TrimSpace(value)
	parsed, err := url.ParseRequestURI(value)
	if err != nil || parsed.Host == "" {
		return "", errors.New("protocol substitute endpoint must be an absolute URL")
	}
	if parsed.Scheme != "https" {
		return "", errors.New("protocol substitute endpoint must use HTTPS")
	}
	return value, nil
}

func postProtocolSubstituteJSON(
	ctx context.Context,
	client *http.Client,
	endpoint string,
	payload any,
	target any,
) (int, error) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return 0, err
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		endpoint,
		bytes.NewReader(encoded),
	)
	if err != nil {
		return 0, err
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := client.Do(request)
	if err != nil {
		return 0, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		return response.StatusCode, nil
	}
	if err := json.NewDecoder(io.LimitReader(response.Body, 64<<10)).Decode(target); err != nil {
		return response.StatusCode, fmt.Errorf("decode protocol substitute response: %w", err)
	}
	return response.StatusCode, nil
}

var _ application.CarrierPhoneResolver = (*ProtocolSubstituteCarrierPhoneResolver)(nil)
var _ application.FederatedIdentityVerifier = (*ProtocolSubstituteFederatedIdentityVerifier)(nil)
