package finance

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/application"
)

type Config struct {
	ChartURL string
}

type Client struct {
	http     *http.Client
	chartURL string
}

func New(cfg Config, httpClient *http.Client) (*Client, error) {
	chartURL, err := url.Parse(strings.TrimSpace(cfg.ChartURL))
	if err != nil || chartURL.Scheme == "" || chartURL.Host == "" {
		return nil, fmt.Errorf("finance chart url must be absolute")
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 8 * time.Second}
	}
	return &Client{http: httpClient, chartURL: chartURL.String()}, nil
}

func (c *Client) Lookup(
	ctx context.Context,
	request application.ExternalSearchRequest,
) (application.ExternalSearchResult, error) {
	symbols := normalizeSymbols(request.Symbols, request.Query)
	if len(symbols) == 0 {
		return application.ExternalSearchResult{}, application.ProviderFailure{
			Capability: "finance", Reason: application.ProviderFailureInvalidResponse,
		}
	}
	references := make([]application.ExternalReference, 0, len(symbols))
	parts := make([]string, 0, len(symbols))
	for _, symbol := range symbols {
		result, err := c.quote(ctx, symbol)
		if err != nil {
			continue
		}
		references = append(references, result.reference)
		parts = append(parts, result.summary)
	}
	if len(references) == 0 {
		return application.ExternalSearchResult{}, application.ProviderFailure{
			Capability: "finance", Reason: application.ProviderFailureUnavailable,
		}
	}
	for index := range references {
		references[index].Rank = index + 1
	}
	return application.ExternalSearchResult{
		Summary:    strings.Join(parts, "；"),
		References: references,
	}, nil
}

type quoteResult struct {
	summary   string
	reference application.ExternalReference
}

func (c *Client) quote(ctx context.Context, symbol string) (quoteResult, error) {
	endpoint, err := chartEndpoint(c.chartURL, symbol)
	if err != nil {
		return quoteResult{}, application.ProviderFailure{
			Capability: "finance", Reason: application.ProviderFailureInvalidResponse,
		}
	}
	body, status, err := c.get(ctx, endpoint)
	if err != nil {
		return quoteResult{}, err
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		return quoteResult{}, application.ProviderFailure{
			Capability: "finance", Reason: application.ProviderFailureUnavailable,
		}
	}
	var decoded chartWire
	if err := json.Unmarshal(body, &decoded); err != nil || len(decoded.Chart.Result) == 0 {
		return quoteResult{}, application.ProviderFailure{
			Capability: "finance", Reason: application.ProviderFailureInvalidResponse,
		}
	}
	meta := decoded.Chart.Result[0].Meta
	name := strings.TrimSpace(meta.LongName)
	if name == "" {
		name = strings.TrimSpace(meta.ShortName)
	}
	if name == "" {
		name = symbol
	}
	change := meta.RegularMarketPrice - meta.ChartPreviousClose
	changePercentage := 0.0
	if meta.ChartPreviousClose != 0 {
		changePercentage = change / meta.ChartPreviousClose * 100
	}
	marketTime := time.Unix(meta.RegularMarketTime, 0).UTC().Format(time.RFC3339)
	summary := fmt.Sprintf(
		"%s（%s，%s）最新价 %.2f %s，较前收 %.2f 变化 %.2f（%.2f%%），日内 %.2f-%.2f，成交量 %d，市场时间 %s。",
		name,
		meta.Symbol,
		meta.ExchangeName,
		meta.RegularMarketPrice,
		meta.Currency,
		meta.ChartPreviousClose,
		change,
		changePercentage,
		meta.RegularMarketDayLow,
		meta.RegularMarketDayHigh,
		meta.RegularMarketVolume,
		marketTime,
	)
	return quoteResult{
		summary: summary,
		reference: application.ExternalReference{
			Title:   "市场行情数据 - " + name + " (" + meta.Symbol + ")",
			Source:  "market_data",
			Snippet: summary,
		},
	}, nil
}

func chartEndpoint(baseURL, symbol string) (string, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return "", fmt.Errorf("finance chart url must be absolute")
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + "/" + url.PathEscape(symbol)
	query := parsed.Query()
	query.Set("range", "5d")
	query.Set("interval", "1d")
	parsed.RawQuery = query.Encode()
	return parsed.String(), nil
}

func (c *Client) get(
	ctx context.Context,
	endpoint string,
) ([]byte, int, error) {
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
		if err != nil {
			return nil, 0, application.ProviderFailure{
				Capability: "finance", Reason: application.ProviderFailureInvalidResponse,
			}
		}
		request.Header.Set("User-Agent", "quwoquan-assistant/1.0")
		response, err := c.http.Do(request)
		if err == nil {
			body, readErr := io.ReadAll(io.LimitReader(response.Body, 128*1024))
			_ = response.Body.Close()
			if readErr == nil && (response.StatusCode < 500 || attempt == 1) {
				return body, response.StatusCode, nil
			}
			lastErr = readErr
		} else {
			lastErr = err
		}
		if attempt == 0 {
			select {
			case <-ctx.Done():
				return nil, 0, financeFailure(ctx.Err())
			case <-time.After(100 * time.Millisecond):
			}
		}
	}
	return nil, 0, financeFailure(lastErr)
}

func financeFailure(err error) application.ProviderFailure {
	if err == context.DeadlineExceeded {
		return application.ProviderFailure{
			Capability: "finance", Reason: application.ProviderFailureTimeout,
		}
	}
	return application.ProviderFailure{
		Capability: "finance", Reason: application.ProviderFailureUnavailable,
	}
}

func normalizeSymbols(values []string, query string) []string {
	symbolPattern := regexp.MustCompile(`^[0-9]{6}\.(SZ|SS|SH)$|^[A-Z]{1,6}(\.[A-Z]{1,3})?$`)
	candidates := append([]string{}, values...)
	candidates = append(
		candidates,
		regexp.MustCompile(`[0-9]{6}\.(?:SZ|SS|SH)|[A-Z]{1,6}(?:\.[A-Z]{1,3})?`).
			FindAllString(strings.ToUpper(query), 4)...,
	)
	result := make([]string, 0, len(candidates))
	seen := make(map[string]struct{})
	for _, candidate := range candidates {
		symbol := strings.ToUpper(strings.TrimSpace(candidate))
		if !symbolPattern.MatchString(symbol) {
			continue
		}
		if _, ok := seen[symbol]; ok {
			continue
		}
		seen[symbol] = struct{}{}
		result = append(result, symbol)
	}
	return result
}

type chartWire struct {
	Chart struct {
		Result []struct {
			Meta struct {
				Symbol               string  `json:"symbol"`
				Currency             string  `json:"currency"`
				LongName             string  `json:"longName"`
				ShortName            string  `json:"shortName"`
				RegularMarketTime    int64   `json:"regularMarketTime"`
				RegularMarketPrice   float64 `json:"regularMarketPrice"`
				RegularMarketDayHigh float64 `json:"regularMarketDayHigh"`
				RegularMarketDayLow  float64 `json:"regularMarketDayLow"`
				RegularMarketVolume  int64   `json:"regularMarketVolume"`
				ChartPreviousClose   float64 `json:"chartPreviousClose"`
				ExchangeName         string  `json:"exchangeName"`
			} `json:"meta"`
		} `json:"result"`
	} `json:"chart"`
}
