package alerting

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

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

// AlertmanagerClient 把 firing 告警推送到 Alertmanager v2 API。
type AlertmanagerClient struct {
	endpoint string
	client   *http.Client
}

func NewAlertmanagerClient(endpoint string, timeout time.Duration) (*AlertmanagerClient, error) {
	trimmed := strings.TrimRight(strings.TrimSpace(endpoint), "/")
	parsed, err := url.Parse(trimmed)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("alertmanager endpoint %q is invalid", endpoint)
	}
	if timeout <= 0 || timeout > 30*time.Second {
		timeout = 10 * time.Second
	}
	return &AlertmanagerClient{
		endpoint: trimmed,
		client:   &http.Client{Timeout: timeout},
	}, nil
}

func (c *AlertmanagerClient) PostAlerts(
	ctx context.Context,
	alerts []application.AlertmanagerAlert,
) error {
	payload, err := json.Marshal(alerts)
	if err != nil {
		return fmt.Errorf("encode Alertmanager alerts: %w", err)
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.endpoint+"/api/v2/alerts",
		bytes.NewReader(payload),
	)
	if err != nil {
		return fmt.Errorf("build Alertmanager request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := c.client.Do(request)
	if err != nil {
		return fmt.Errorf("post Alertmanager alerts: %w", err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode < http.StatusOK ||
		response.StatusCode >= http.StatusMultipleChoices {
		body, _ := io.ReadAll(io.LimitReader(response.Body, 2048))
		return fmt.Errorf(
			"Alertmanager rejected alerts status=%d: %s",
			response.StatusCode, strings.TrimSpace(string(body)),
		)
	}
	return nil
}
