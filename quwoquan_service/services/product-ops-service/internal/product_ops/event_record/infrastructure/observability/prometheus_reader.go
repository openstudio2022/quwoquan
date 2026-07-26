package observability

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

type PrometheusReader struct {
	baseURL string
	client  *http.Client
}

type queryResponse struct {
	Status string            `json:"status"`
	Data   queryResponseData `json:"data"`
	Error  string            `json:"error"`
}

type queryResponseData struct {
	ResultType string        `json:"resultType"`
	Result     []queryResult `json:"result"`
}

type queryResult struct {
	Metric map[string]string `json:"metric"`
	Value  []json.RawMessage `json:"value"`
}

func NewPrometheusReader(baseURL string, client *http.Client) (*PrometheusReader, error) {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if baseURL == "" {
		return nil, errors.New("prometheus base url is required")
	}
	if _, err := url.ParseRequestURI(baseURL); err != nil {
		return nil, fmt.Errorf("prometheus base url invalid: %w", err)
	}
	if client == nil {
		client = &http.Client{Timeout: 3 * time.Second}
	}
	return &PrometheusReader{baseURL: baseURL, client: client}, nil
}

func (r *PrometheusReader) Query(ctx context.Context, expression string) (float64, error) {
	decoded, err := r.instantQuery(ctx, expression)
	if err != nil {
		return 0, err
	}
	if decoded.Data.ResultType != "vector" || len(decoded.Data.Result) != 1 ||
		len(decoded.Data.Result[0].Value) != 2 {
		return 0, errors.New("prometheus query did not return one vector sample")
	}
	return decodeSampleValue(decoded.Data.Result[0].Value[1])
}

// QueryVector 返回带标签的即时向量（如 by (route) 分组的每接口 RED 指标）。
func (r *PrometheusReader) QueryVector(ctx context.Context, expression string) ([]application.PrometheusVectorSample, error) {
	decoded, err := r.instantQuery(ctx, expression)
	if err != nil {
		return nil, err
	}
	if decoded.Data.ResultType != "vector" {
		return nil, errors.New("prometheus query did not return a vector")
	}
	samples := make([]application.PrometheusVectorSample, 0, len(decoded.Data.Result))
	for _, result := range decoded.Data.Result {
		if len(result.Value) != 2 {
			continue
		}
		value, err := decodeSampleValue(result.Value[1])
		if err != nil {
			return nil, err
		}
		labels := make(map[string]string, len(result.Metric))
		for key, item := range result.Metric {
			labels[key] = item
		}
		samples = append(samples, application.PrometheusVectorSample{Labels: labels, Value: value})
	}
	return samples, nil
}

func (r *PrometheusReader) instantQuery(ctx context.Context, expression string) (queryResponse, error) {
	expression = strings.TrimSpace(expression)
	if expression == "" {
		return queryResponse{}, errors.New("prometheus query is required")
	}
	requestURL := r.baseURL + "/api/v1/query?query=" + url.QueryEscape(expression)
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return queryResponse{}, err
	}
	response, err := r.client.Do(request)
	if err != nil {
		return queryResponse{}, fmt.Errorf("prometheus query request: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return queryResponse{}, fmt.Errorf("prometheus query status %d", response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, 1024*1024))
	if err != nil {
		return queryResponse{}, err
	}
	var decoded queryResponse
	if err := json.Unmarshal(body, &decoded); err != nil {
		return queryResponse{}, fmt.Errorf("decode prometheus query: %w", err)
	}
	if decoded.Status != "success" || decoded.Error != "" {
		return queryResponse{}, fmt.Errorf("prometheus query failed: %s", decoded.Error)
	}
	return decoded, nil
}

func decodeSampleValue(raw json.RawMessage) (float64, error) {
	var value string
	if err := json.Unmarshal(raw, &value); err != nil {
		return 0, fmt.Errorf("decode prometheus sample: %w", err)
	}
	var parsed float64
	if _, err := fmt.Sscan(value, &parsed); err != nil {
		return 0, fmt.Errorf("parse prometheus sample: %w", err)
	}
	return parsed, nil
}
