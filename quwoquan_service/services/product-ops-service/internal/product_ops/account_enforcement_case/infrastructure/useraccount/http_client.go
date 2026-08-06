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
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
)

type HTTPClientConfig struct {
	BaseURL     string
	HTTPClient  *http.Client
	Credentials rtauth.ServiceAuthorizationProvider
}

type HTTPClient struct {
	baseURL     *url.URL
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

var _ ports.EnforcementPublisher = (*HTTPClient)(nil)

func NewHTTPClient(config HTTPClientConfig) (*HTTPClient, error) {
	baseURL, err := url.Parse(strings.TrimSpace(config.BaseURL))
	if err != nil || baseURL == nil ||
		(baseURL.Scheme != "http" && baseURL.Scheme != "https") ||
		strings.TrimSpace(baseURL.Host) == "" || baseURL.User != nil ||
		baseURL.RawQuery != "" || baseURL.Fragment != "" {
		return nil, errors.New("account enforcement UserAccount base URL is invalid")
	}
	if config.HTTPClient == nil || config.Credentials == nil {
		return nil, errors.New("account enforcement HTTP client and service credentials are required")
	}
	client := *config.HTTPClient
	client.CheckRedirect = func(_ *http.Request, _ []*http.Request) error {
		return http.ErrUseLastResponse
	}
	baseURL.Path = strings.TrimRight(baseURL.Path, "/")
	return &HTTPClient{baseURL: baseURL, httpClient: &client, credentials: config.Credentials}, nil
}

type enforcementRequest struct {
	DecisionID     string    `json:"decisionId"`
	CaseRef        string    `json:"caseRef"`
	DecisionDigest string    `json:"decisionDigest"`
	ApprovedAt     time.Time `json:"approvedAt"`
}

type enforcementResponse struct {
	AccountState     string    `json:"accountState"`
	AuthEpoch        int64     `json:"authEpoch"`
	DecisionID       string    `json:"decisionId"`
	IdempotentReplay bool      `json:"idempotentReplay"`
	OccurredAt       time.Time `json:"occurredAt"`
}

func (client *HTTPClient) Publish(
	ctx context.Context,
	decision model.Decision,
) (ports.DeliveryReceipt, error) {
	if client == nil || client.baseURL == nil || client.httpClient == nil ||
		client.credentials == nil || strings.TrimSpace(decision.ID) == "" ||
		strings.TrimSpace(decision.CaseID) == "" ||
		strings.TrimSpace(decision.AccountID) == "" ||
		strings.TrimSpace(decision.CaseRef) == "" ||
		strings.TrimSpace(decision.DecisionDigest) == "" || decision.ApprovedAt.IsZero() {
		return ports.DeliveryReceipt{}, newDeliveryError("invalid_request", true)
	}
	var actionPath string
	switch decision.Action {
	case model.EnforcementActionSuspend:
		actionPath = "suspend"
	case model.EnforcementActionRestore:
		actionPath = "restore"
	default:
		return ports.DeliveryReceipt{}, newDeliveryError("invalid_request", true)
	}
	payload, err := json.Marshal(enforcementRequest{
		DecisionID: decision.ID, CaseRef: decision.CaseRef,
		DecisionDigest: decision.DecisionDigest, ApprovedAt: decision.ApprovedAt.UTC(),
	})
	if err != nil {
		return ports.DeliveryReceipt{}, newDeliveryError("invalid_request", true)
	}
	authorization, err := client.credentials.AuthorizationHeader(ctx)
	if err != nil || strings.TrimSpace(authorization) == "" {
		return ports.DeliveryReceipt{}, newDeliveryError("unauthorized", false)
	}
	target := *client.baseURL
	basePath := strings.TrimRight(target.Path, "/")
	baseRawPath := strings.TrimRight(target.EscapedPath(), "/")
	target.Path = basePath + "/internal/user/accounts/" + decision.AccountID + "/" + actionPath
	target.RawPath = baseRawPath + "/internal/user/accounts/" +
		url.PathEscape(decision.AccountID) + "/" + actionPath
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, target.String(), bytes.NewReader(payload))
	if err != nil {
		return ports.DeliveryReceipt{}, newDeliveryError("invalid_request", true)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Cache-Control", "no-store")
	request.Header.Set("Idempotency-Key", decision.ID)
	response, err := client.httpClient.Do(request)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) {
			return ports.DeliveryReceipt{}, newDeliveryError("timeout", false)
		}
		if errors.Is(err, context.Canceled) {
			return ports.DeliveryReceipt{}, newDeliveryError("canceled", false)
		}
		return ports.DeliveryReceipt{}, newDeliveryError("transport_unavailable", false)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		return ports.DeliveryReceipt{}, deliveryErrorForStatus(response.StatusCode)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 16384))
	decoder.DisallowUnknownFields()
	var result enforcementResponse
	if err := decoder.Decode(&result); err != nil {
		return ports.DeliveryReceipt{}, newDeliveryError("invalid_response", true)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return ports.DeliveryReceipt{}, newDeliveryError("invalid_response", true)
	}
	if result.DecisionID != decision.ID || result.AuthEpoch <= 0 || result.OccurredAt.IsZero() ||
		(decision.Action == model.EnforcementActionSuspend && result.AccountState != "suspended") ||
		(decision.Action == model.EnforcementActionRestore && result.AccountState != "active") {
		return ports.DeliveryReceipt{}, newDeliveryError("invalid_response", true)
	}
	return ports.DeliveryReceipt{
		DecisionID:       result.DecisionID,
		AccountState:     result.AccountState,
		AuthEpoch:        result.AuthEpoch,
		IdempotentReplay: result.IdempotentReplay,
		OccurredAt:       result.OccurredAt.UTC(),
	}, nil
}

type deliveryError struct {
	class     string
	permanent bool
}

func (current deliveryError) Error() string      { return "account enforcement delivery " + current.class }
func (current deliveryError) ErrorClass() string { return current.class }
func (current deliveryError) Permanent() bool    { return current.permanent }

func newDeliveryError(class string, permanent bool) error {
	return deliveryError{class: class, permanent: permanent}
}

func deliveryErrorForStatus(status int) error {
	switch status {
	case http.StatusBadRequest, http.StatusMethodNotAllowed:
		return newDeliveryError("invalid_request", true)
	case http.StatusNotFound:
		return newDeliveryError("not_found", true)
	case http.StatusConflict:
		return newDeliveryError("state_conflict", true)
	case http.StatusUnauthorized:
		return newDeliveryError("unauthorized", false)
	case http.StatusForbidden:
		return newDeliveryError("forbidden", false)
	default:
		return newDeliveryError("remote_unavailable", false)
	}
}

var _ ports.ClassifiedDeliveryError = deliveryError{}
