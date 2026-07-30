package useraccount

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
)

type AppealIntakeHTTPClientConfig struct {
	BaseURL     string
	HTTPClient  *http.Client
	Credentials rtauth.ServiceAuthorizationProvider
}

type AppealIntakeHTTPClient struct {
	baseURL     *url.URL
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

func NewAppealIntakeHTTPClient(
	config AppealIntakeHTTPClientConfig,
) (*AppealIntakeHTTPClient, error) {
	baseURL, err := url.Parse(strings.TrimSpace(config.BaseURL))
	if err != nil || baseURL == nil ||
		(baseURL.Scheme != "http" && baseURL.Scheme != "https") ||
		strings.TrimSpace(baseURL.Host) == "" || baseURL.User != nil ||
		baseURL.RawQuery != "" || baseURL.Fragment != "" {
		return nil, errors.New("account appeal intake User base URL is invalid")
	}
	if config.HTTPClient == nil || config.Credentials == nil {
		return nil, errors.New("account appeal intake HTTP client and credentials are required")
	}
	client := *config.HTTPClient
	client.CheckRedirect = func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}
	baseURL.Path = strings.TrimRight(baseURL.Path, "/")
	return &AppealIntakeHTTPClient{
		baseURL: baseURL, httpClient: &client, credentials: config.Credentials,
	}, nil
}

type appealIntakeClaimRequest struct {
	AccountID string `json:"accountId"`
	CaseID    string `json:"caseId"`
}

type appealIntakeClaimResponse struct {
	IntakeRef        string    `json:"intakeRef"`
	AccountID        string    `json:"accountId"`
	CaseID           string    `json:"caseId"`
	Status           string    `json:"status"`
	ClaimedAt        time.Time `json:"claimedAt"`
	IdempotentReplay bool      `json:"idempotentReplay"`
}

func (client *AppealIntakeHTTPClient) Claim(
	ctx context.Context,
	claim ports.AppealIntakeClaim,
) error {
	claim.IntakeRef = strings.TrimSpace(claim.IntakeRef)
	claim.AccountID = strings.TrimSpace(claim.AccountID)
	claim.CaseID = strings.TrimSpace(claim.CaseID)
	if client == nil || client.baseURL == nil || client.httpClient == nil ||
		client.credentials == nil || !claim.Valid() {
		return ports.ErrAppealIntakeInvalid
	}
	payload, err := json.Marshal(appealIntakeClaimRequest{
		AccountID: claim.AccountID,
		CaseID:    claim.CaseID,
	})
	if err != nil {
		return ports.ErrAppealIntakeInvalid
	}
	authorization, err := client.credentials.AuthorizationHeader(ctx)
	if err != nil || strings.TrimSpace(authorization) == "" {
		return ports.ErrAppealIntakeUnavailable
	}
	target := *client.baseURL
	basePath := strings.TrimRight(target.Path, "/")
	baseRawPath := strings.TrimRight(target.EscapedPath(), "/")
	target.Path = basePath + "/internal/user/account-appeal-intakes/" +
		claim.IntakeRef + ":claim"
	target.RawPath = baseRawPath + "/internal/user/account-appeal-intakes/" +
		url.PathEscape(claim.IntakeRef) + ":claim"
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		target.String(),
		bytes.NewReader(payload),
	)
	if err != nil {
		return ports.ErrAppealIntakeInvalid
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Cache-Control", "no-store")
	request.Header.Set("Idempotency-Key", "appeal-intake-claim:"+claim.CaseID)
	response, err := client.httpClient.Do(request)
	if err != nil {
		return ports.ErrAppealIntakeUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return mapAppealIntakeClaimError(response)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 16384))
	decoder.DisallowUnknownFields()
	var result appealIntakeClaimResponse
	if err := decoder.Decode(&result); err != nil {
		return ports.ErrAppealIntakeUnavailable
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return ports.ErrAppealIntakeUnavailable
	}
	if result.IntakeRef != claim.IntakeRef || result.AccountID != claim.AccountID ||
		result.CaseID != claim.CaseID || result.Status != "claimed" ||
		result.ClaimedAt.IsZero() {
		return ports.ErrAppealIntakeUnavailable
	}
	return nil
}

func mapAppealIntakeClaimError(response *http.Response) error {
	var wire struct {
		Code string `json:"code"`
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 4096))
	_ = decoder.Decode(&wire)
	switch strings.TrimSpace(wire.Code) {
	case "USER.ACCOUNT.account_appeal_intake_not_found":
		return ports.ErrAppealIntakeInvalid
	case "USER.ACCOUNT.account_appeal_intake_account_mismatch":
		return ports.ErrAppealIntakeAccountMismatch
	case "USER.ACCOUNT.account_appeal_intake_claimed":
		return ports.ErrAppealIntakeConsumed
	case "USER.ACCOUNT.account_appeal_not_suspended",
		"USER.ACCOUNT.account_appeal_idempotency_conflict":
		return ports.ErrAppealIntakeInvalid
	}
	switch response.StatusCode {
	case http.StatusBadRequest, http.StatusNotFound, http.StatusGone:
		return ports.ErrAppealIntakeInvalid
	case http.StatusConflict:
		return ports.ErrAppealIntakeConsumed
	default:
		return ports.ErrAppealIntakeUnavailable
	}
}

var _ ports.AppealIntakeVerifier = (*AppealIntakeHTTPClient)(nil)
