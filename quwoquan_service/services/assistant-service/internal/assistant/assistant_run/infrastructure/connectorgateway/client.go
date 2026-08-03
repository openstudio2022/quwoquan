// Package connectorgateway resolves current Connector capability grants through
// Integration Service. It never receives credentials or provider tokens.
package connectorgateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/toolaccess"
)

const (
	resolveCapabilityOperation = "integration.connector_connection.ResolveConnectorCapabilityGrant"
	maxResponseBytes           = 64 << 10
)

type Client struct {
	baseURL       *url.URL
	http          *http.Client
	authorization rtauth.ServiceAuthorizationProvider
	path          string
}

func New(
	baseURL string,
	httpClient *http.Client,
	authorization rtauth.ServiceAuthorizationProvider,
) (*Client, error) {
	parsed, err := url.Parse(strings.TrimRight(strings.TrimSpace(baseURL), "/"))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") {
		return nil, fmt.Errorf("integration-service base URL must be absolute http or https")
	}
	if httpClient == nil {
		return nil, fmt.Errorf("integration-service observed HTTP client is required")
	}
	if authorization == nil {
		return nil, fmt.Errorf("integration-service service authorization is required")
	}
	descriptor, err := operationDescriptor()
	if err != nil {
		return nil, err
	}
	return &Client{
		baseURL: parsed, http: httpClient, authorization: authorization,
		path: descriptor.PathTemplate,
	}, nil
}

func RequiredScope() (string, error) {
	descriptor, err := operationDescriptor()
	if err != nil {
		return "", err
	}
	if len(descriptor.Scopes) != 1 || strings.TrimSpace(descriptor.Scopes[0]) == "" {
		return "", fmt.Errorf("connector capability operation must declare one service scope")
	}
	return strings.TrimSpace(descriptor.Scopes[0]), nil
}

func (client *Client) ResolveCapability(
	ctx context.Context,
	input toolaccess.ConnectorGrantRequest,
) (toolaccess.ConnectorGrantDecision, error) {
	if client == nil || client.http == nil || client.authorization == nil {
		return toolaccess.ConnectorGrantDecision{}, fmt.Errorf("connector gateway is not initialized")
	}
	payload, err := json.Marshal(struct {
		AccountID      string   `json:"accountId"`
		CapabilityKey  string   `json:"capabilityKey"`
		SurfaceKind    string   `json:"surfaceKind"`
		ConnectionRefs []string `json:"connectionRefs"`
	}{
		AccountID:      strings.TrimSpace(input.AccountID),
		CapabilityKey:  strings.TrimSpace(input.CapabilityKey),
		SurfaceKind:    strings.TrimSpace(input.SurfaceKind),
		ConnectionRefs: append([]string(nil), input.ConnectionRefs...),
	})
	if err != nil {
		return toolaccess.ConnectorGrantDecision{}, fmt.Errorf("encode connector capability request: %w", err)
	}
	target := *client.baseURL
	target.Path = strings.TrimRight(target.Path, "/") + client.path
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		target.String(),
		bytes.NewReader(payload),
	)
	if err != nil {
		return toolaccess.ConnectorGrantDecision{}, fmt.Errorf("build connector capability request: %w", err)
	}
	authorization, err := client.authorization.AuthorizationHeader(ctx)
	if err != nil {
		return toolaccess.ConnectorGrantDecision{}, fmt.Errorf("authorize connector capability request: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Content-Type", "application/json")
	response, err := client.http.Do(request)
	if err != nil {
		return toolaccess.ConnectorGrantDecision{}, fmt.Errorf("call connector capability gateway: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 8<<10))
		return toolaccess.ConnectorGrantDecision{}, fmt.Errorf(
			"connector capability gateway status=%d",
			response.StatusCode,
		)
	}
	var payloadDecision struct {
		Allowed       bool   `json:"allowed"`
		CapabilityKey string `json:"capabilityKey"`
		SurfaceKind   string `json:"surfaceKind"`
		ConnectionID  string `json:"connectionId"`
		ConnectorID   string `json:"connectorId"`
		FreshnessAt   string `json:"freshnessAt"`
		ExpiresAt     string `json:"expiresAt"`
		Reason        string `json:"reason"`
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, maxResponseBytes))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payloadDecision); err != nil {
		return toolaccess.ConnectorGrantDecision{}, fmt.Errorf(
			"decode connector capability decision: %w",
			err,
		)
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return toolaccess.ConnectorGrantDecision{}, fmt.Errorf(
			"connector capability decision must contain one JSON object",
		)
	}
	if payloadDecision.CapabilityKey != strings.TrimSpace(input.CapabilityKey) ||
		payloadDecision.SurfaceKind != strings.TrimSpace(input.SurfaceKind) ||
		strings.TrimSpace(payloadDecision.Reason) == "" ||
		(payloadDecision.Allowed && (strings.TrimSpace(payloadDecision.ConnectionID) == "" ||
			strings.TrimSpace(payloadDecision.ConnectorID) == "")) {
		return toolaccess.ConnectorGrantDecision{}, fmt.Errorf(
			"connector capability decision identity mismatch",
		)
	}
	return toolaccess.ConnectorGrantDecision{
		Allowed:      payloadDecision.Allowed,
		ConnectionID: strings.TrimSpace(payloadDecision.ConnectionID),
		ConnectorID:  strings.TrimSpace(payloadDecision.ConnectorID),
		Reason:       strings.TrimSpace(payloadDecision.Reason),
	}, nil
}

func operationDescriptor() (rtauth.OperationSecurityDescriptor, error) {
	for _, descriptor := range operationsecurity.ForDomain("integration") {
		if descriptor.CanonicalOperationID == resolveCapabilityOperation {
			if descriptor.Method != http.MethodPost || !strings.HasPrefix(descriptor.PathTemplate, "/internal/") {
				return rtauth.OperationSecurityDescriptor{}, fmt.Errorf(
					"connector capability operation must be an internal POST",
				)
			}
			return descriptor, nil
		}
	}
	return rtauth.OperationSecurityDescriptor{}, fmt.Errorf(
		"missing generated connector capability operation descriptor",
	)
}

var _ toolaccess.ConnectorGateway = (*Client)(nil)
