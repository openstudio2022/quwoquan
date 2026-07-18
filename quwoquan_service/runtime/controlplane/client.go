package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type ConfigResolveResponse struct {
	Scope         ConfigResolutionScope `json:"scope"`
	ResolvedAt    string                `json:"resolvedAt"`
	EffectiveHash string                `json:"effectiveHash"`
	DesiredHash   string                `json:"desiredHash"`
	Values        []ResolvedConfigValue `json:"values"`
	Source        string                `json:"source"`
}

type InstanceConfigReport struct {
	ID            string `json:"id"`
	Environment   string `json:"environment"`
	Cluster       string `json:"cluster"`
	Service       string `json:"service"`
	InstanceID    string `json:"instanceId"`
	ConfigVersion string `json:"configVersion,omitempty"`
	ImageVersion  string `json:"imageVersion,omitempty"`
	DesiredHash   string `json:"desiredHash,omitempty"`
	EffectiveHash string `json:"effectiveHash,omitempty"`
	InSync        bool   `json:"inSync"`
	Source        string `json:"source,omitempty"`
	UpdatedAt     string `json:"updatedAt,omitempty"`
	LastError     string `json:"lastError,omitempty"`
}

type Client struct {
	BaseURL    string
	HTTPClient *http.Client
}

func NewClient(baseURL string, httpClient *http.Client) *Client {
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 5 * time.Second}
	}
	return &Client{
		BaseURL:    strings.TrimRight(strings.TrimSpace(baseURL), "/"),
		HTTPClient: httpClient,
	}
}

func (c *Client) Resolve(ctx context.Context, scope ConfigResolutionScope) (ConfigResolveResponse, error) {
	if c == nil || strings.TrimSpace(c.BaseURL) == "" {
		return ConfigResolveResponse{}, fmt.Errorf("control plane base url is required")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/control-plane/platform/configs/resolve", nil)
	if err != nil {
		return ConfigResolveResponse{}, err
	}
	query := req.URL.Query()
	if scope.Environment != "" {
		query.Set("env", scope.Environment)
	}
	if scope.Cluster != "" {
		query.Set("cluster", scope.Cluster)
	}
	if scope.Service != "" {
		query.Set("service", scope.Service)
	}
	req.URL.RawQuery = query.Encode()
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return ConfigResolveResponse{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return ConfigResolveResponse{}, fmt.Errorf("resolve config status=%d", resp.StatusCode)
	}
	var out ConfigResolveResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return ConfigResolveResponse{}, err
	}
	return out, nil
}

func (c *Client) ReportInstance(ctx context.Context, report InstanceConfigReport) error {
	if c == nil || strings.TrimSpace(c.BaseURL) == "" {
		return fmt.Errorf("control plane base url is required")
	}
	if strings.TrimSpace(report.ID) == "" {
		report.ID = report.InstanceID
	}
	if strings.TrimSpace(report.ID) == "" {
		return fmt.Errorf("instance report id is required")
	}
	if strings.TrimSpace(report.UpdatedAt) == "" {
		report.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	}
	payload, err := json.Marshal(report)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.BaseURL+"/control-plane/platform/configs/instances/"+report.ID+":report",
		bytes.NewReader(payload),
	)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Environment", report.Environment)
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("report instance status=%d", resp.StatusCode)
	}
	return nil
}

func SaveResolveSnapshot(path string, response ConfigResolveResponse) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	payload, err := json.MarshalIndent(response, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, payload, 0o644)
}

func LoadResolveSnapshot(path string) (ConfigResolveResponse, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return ConfigResolveResponse{}, err
	}
	var out ConfigResolveResponse
	if err := json.Unmarshal(data, &out); err != nil {
		return ConfigResolveResponse{}, err
	}
	return out, nil
}
