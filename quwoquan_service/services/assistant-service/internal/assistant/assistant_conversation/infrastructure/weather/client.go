package weather

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

type Config struct {
	GeocodingURL string
	ForecastURL  string
}

type Client struct {
	http         *http.Client
	geocodingURL string
	forecastURL  string
}

func New(cfg Config, httpClient *http.Client) (*Client, error) {
	if !isAbsoluteURL(cfg.GeocodingURL) || !isAbsoluteURL(cfg.ForecastURL) {
		return nil, fmt.Errorf("weather endpoint urls must be absolute")
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 8 * time.Second}
	}
	return &Client{
		http:         httpClient,
		geocodingURL: strings.TrimSpace(cfg.GeocodingURL),
		forecastURL:  strings.TrimSpace(cfg.ForecastURL),
	}, nil
}

func (c *Client) Lookup(
	ctx context.Context,
	request ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	candidates := make([]string, 0, 2)
	if value := strings.TrimSpace(request.LocationSearchName); value != "" {
		candidates = append(candidates, value)
	}
	if value := locationCandidate(request.Query, request.Location); value != "" {
		candidates = append(candidates, value)
	}
	seen := make(map[string]struct{})
	var lastErr error
	for _, candidate := range candidates {
		if _, ok := seen[candidate]; ok {
			continue
		}
		seen[candidate] = struct{}{}
		result, err := c.lookupCandidate(ctx, candidate)
		if err == nil {
			return result, nil
		}
		lastErr = err
	}
	if lastErr != nil {
		return ports.ExternalSearchResult{}, lastErr
	}
	return ports.ExternalSearchResult{}, ports.ProviderFailure{
		Capability: "weather", Reason: ports.ProviderFailureInvalidResponse,
	}
}

func (c *Client) lookupCandidate(
	ctx context.Context,
	candidate string,
) (ports.ExternalSearchResult, error) {
	geocodeURL, err := queryURL(c.geocodingURL, url.Values{
		"count":    {"5"},
		"language": {"zh"},
		"format":   {"json"},
		"name":     {candidate},
	})
	if err != nil {
		return ports.ExternalSearchResult{}, ports.ProviderFailure{
			Capability: "weather", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	var geocode geocodeWire
	geocodeBody, geocodeStatus, err := c.get(ctx, geocodeURL, "quwoquan-assistant/1.0")
	if err != nil {
		return ports.ExternalSearchResult{}, err
	}
	if geocodeStatus < http.StatusOK || geocodeStatus >= http.StatusMultipleChoices {
		return ports.ExternalSearchResult{}, ports.ProviderFailure{
			Capability: "weather", Reason: ports.ProviderFailureUnavailable,
		}
	}
	if err := json.Unmarshal(geocodeBody, &geocode); err != nil {
		return ports.ExternalSearchResult{}, ports.ProviderFailure{
			Capability: "weather", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	if len(geocode.Results) == 0 {
		return ports.ExternalSearchResult{}, ports.ProviderFailure{
			Capability: "weather", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	place := geocode.Results[0]
	timezone := strings.TrimSpace(place.Timezone)
	if timezone == "" {
		timezone = "auto"
	}
	forecastURL, err := queryURL(c.forecastURL, url.Values{
		"latitude":      {strconv.FormatFloat(place.Latitude, 'f', -1, 64)},
		"longitude":     {strconv.FormatFloat(place.Longitude, 'f', -1, 64)},
		"current":       {"temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"},
		"daily":         {"weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"},
		"timezone":      {timezone},
		"forecast_days": {"3"},
	})
	if err != nil {
		return ports.ExternalSearchResult{}, ports.ProviderFailure{
			Capability: "weather", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	var forecast forecastWire
	forecastBody, forecastStatus, err := c.get(ctx, forecastURL, "quwoquan-assistant/1.0")
	if err != nil {
		return ports.ExternalSearchResult{}, err
	}
	if forecastStatus < http.StatusOK || forecastStatus >= http.StatusMultipleChoices {
		return ports.ExternalSearchResult{}, ports.ProviderFailure{
			Capability: "weather", Reason: ports.ProviderFailureUnavailable,
		}
	}
	if err := json.Unmarshal(forecastBody, &forecast); err != nil {
		return ports.ExternalSearchResult{}, ports.ProviderFailure{
			Capability: "weather", Reason: ports.ProviderFailureInvalidResponse,
		}
	}
	placeName := place.Name
	if strings.TrimSpace(place.Admin1) != "" {
		placeName += "，" + strings.TrimSpace(place.Admin1)
	}
	daily := make([]string, 0, 3)
	for index, day := range forecast.Daily.Time {
		if index == 3 || index >= len(forecast.Daily.Temperature2mMax) || index >= len(forecast.Daily.Temperature2mMin) {
			break
		}
		weather := ""
		if index < len(forecast.Daily.WeatherCode) {
			weather = weatherCode(forecast.Daily.WeatherCode[index])
		}
		precipitation := ""
		if index < len(forecast.Daily.PrecipitationProbability) {
			precipitation = fmt.Sprintf("，降水概率%d%%", forecast.Daily.PrecipitationProbability[index])
		}
		daily = append(daily, fmt.Sprintf(
			"%s：%s，%.0f-%.0f°C%s",
			day,
			weather,
			forecast.Daily.Temperature2mMin[index],
			forecast.Daily.Temperature2mMax[index],
			precipitation,
		))
	}
	summary := fmt.Sprintf(
		"%s 当前%s，气温%.1f°C，体感%.1f°C，湿度%d%%，降水%.1fmm，风速%.1fkm/h。未来三天：%s。数据时间：%s（%s）。",
		placeName,
		weatherCode(forecast.Current.WeatherCode),
		forecast.Current.Temperature2m,
		forecast.Current.ApparentTemperature,
		forecast.Current.RelativeHumidity,
		forecast.Current.Precipitation,
		forecast.Current.WindSpeed10m,
		strings.Join(daily, "；"),
		forecast.Current.Time,
		timezone,
	)
	summary = authoritySummary(candidate, placeName, summary)
	references := authorityReferences(candidate, placeName)
	return normalizeResult(summary, references), nil
}

func (c *Client) get(
	ctx context.Context,
	endpoint string,
	userAgent string,
) ([]byte, int, error) {
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
		if err != nil {
			return nil, 0, ports.ProviderFailure{
				Capability: "weather", Reason: ports.ProviderFailureInvalidResponse,
			}
		}
		request.Header.Set("User-Agent", userAgent)
		response, err := c.http.Do(request)
		if err == nil {
			body, readErr := io.ReadAll(io.LimitReader(response.Body, 256*1024))
			_ = response.Body.Close()
			if readErr == nil && response.StatusCode >= http.StatusOK && response.StatusCode < http.StatusMultipleChoices {
				return body, response.StatusCode, nil
			}
			lastErr = readErr
			if attempt == 1 && readErr == nil {
				return body, response.StatusCode, nil
			}
		} else {
			lastErr = err
		}
		if attempt == 0 {
			select {
			case <-ctx.Done():
				return nil, 0, weatherFailure(ctx.Err())
			case <-time.After(100 * time.Millisecond):
			}
		}
	}
	return nil, 0, weatherFailure(lastErr)
}

func weatherFailure(err error) ports.ProviderFailure {
	if err == context.DeadlineExceeded {
		return ports.ProviderFailure{
			Capability: "weather", Reason: ports.ProviderFailureTimeout,
		}
	}
	return ports.ProviderFailure{
		Capability: "weather", Reason: ports.ProviderFailureUnavailable,
	}
}

func normalizeResult(
	summary string,
	references []ports.ExternalReference,
) ports.ExternalSearchResult {
	for index := range references {
		references[index].Rank = index + 1
	}
	return ports.ExternalSearchResult{
		Summary: summary, References: references,
	}
}

func locationCandidate(query, location string) string {
	candidate := strings.TrimSpace(location)
	if candidate == "" {
		candidate = strings.TrimSpace(query)
	}
	replacer := strings.NewReplacer(
		"天气预报", "", "天气", "", "气温", "", "温度", "", "预报", "",
		"weather", "", "forecast", "", "今天", "", "明天", "", "当前", "",
		"现在", "", "怎么样", "", "如何", "", "查询", "", "搜索", "",
		"？", "", "?", "", "。", "", "，", "", ",", "",
	)
	candidate = strings.TrimSpace(replacer.Replace(candidate))
	if len([]rune(candidate)) > 24 {
		return ""
	}
	return candidate
}

func authoritySummary(query, place, summary string) string {
	if len(authorityReferences(query, place)) == 0 {
		return summary
	}
	return "天气证据优先按国家级气象服务入口与可解析的省/自治区/直辖市气象局排序；" + summary
}

func isAbsoluteURL(raw string) bool {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	return err == nil && parsed.Scheme != "" && parsed.Host != ""
}

func queryURL(raw string, values url.Values) (string, error) {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		if err != nil {
			return "", err
		}
		return "", fmt.Errorf("weather endpoint url must be absolute")
	}
	query := parsed.Query()
	for key, entries := range values {
		query.Del(key)
		for _, entry := range entries {
			query.Add(key, entry)
		}
	}
	parsed.RawQuery = query.Encode()
	return parsed.String(), nil
}

func authorityReferences(query, place string) []ports.ExternalReference {
	references := []ports.ExternalReference{
		{Title: "中国天气网", URL: "https://www.weather.com.cn/", Source: "weather_com_cn", Snippet: "中国天气网为国家级天气服务入口。"},
		{Title: "中央气象台", URL: "https://www.nmc.cn/", Source: "national_meteorological_center", Snippet: "中央气象台提供全国天气预报和预警。"},
		{Title: "中国气象局", URL: "https://www.cma.gov.cn/", Source: "china_meteorological_administration", Snippet: "中国气象局为国家气象主管机构入口。"},
	}
	if regional, ok := regionalAuthority(query + " " + place); ok {
		references = append(references, regional)
	}
	return references
}

func regionalAuthority(raw string) (ports.ExternalReference, bool) {
	normalized := strings.ToLower(raw)
	regions := []struct {
		keywords []string
		title    string
		url      string
		source   string
	}{
		{[]string{"北京", "beijing"}, "北京市气象局", "https://bj.cma.gov.cn/", "beijing_meteorological_bureau"},
		{[]string{"上海", "shanghai"}, "上海市气象局", "https://sh.cma.gov.cn/", "shanghai_meteorological_bureau"},
		{[]string{"浙江", "zhejiang", "杭州", "hangzhou"}, "浙江省气象局", "https://zj.cma.gov.cn/", "zhejiang_meteorological_bureau"},
		{[]string{"广东", "guangdong", "深圳", "shenzhen"}, "广东省气象局", "https://gd.cma.gov.cn/", "guangdong_meteorological_bureau"},
		{[]string{"四川", "sichuan", "成都", "chengdu"}, "四川省气象局", "https://sc.cma.gov.cn/", "sichuan_meteorological_bureau"},
	}
	for _, region := range regions {
		for _, keyword := range region.keywords {
			if strings.Contains(normalized, keyword) {
				return ports.ExternalReference{
					Title: region.title, URL: region.url, Source: region.source,
					Snippet: region.title + "为区域气象服务入口。",
				}, true
			}
		}
	}
	return ports.ExternalReference{}, false
}

func weatherCode(code int) string {
	switch code {
	case 0:
		return "晴"
	case 1, 2, 3:
		return "多云"
	case 45, 48:
		return "雾"
	case 51, 53, 55, 56, 57:
		return "毛毛雨"
	case 61, 63, 65, 66, 67, 80, 81, 82:
		return "降雨"
	case 71, 73, 75, 77, 85, 86:
		return "降雪"
	case 95, 96, 99:
		return "雷暴"
	default:
		return fmt.Sprintf("天气代码%d", code)
	}
}

type geocodeWire struct {
	Results []geocodePlaceWire `json:"results"`
}

type geocodePlaceWire struct {
	Name      string  `json:"name"`
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
	Admin1    string  `json:"admin1"`
	Timezone  string  `json:"timezone"`
}

type forecastWire struct {
	Current struct {
		Time                string  `json:"time"`
		Temperature2m       float64 `json:"temperature_2m"`
		ApparentTemperature float64 `json:"apparent_temperature"`
		RelativeHumidity    int     `json:"relative_humidity_2m"`
		Precipitation       float64 `json:"precipitation"`
		WeatherCode         int     `json:"weather_code"`
		WindSpeed10m        float64 `json:"wind_speed_10m"`
	} `json:"current"`
	Daily struct {
		Time                     []string  `json:"time"`
		WeatherCode              []int     `json:"weather_code"`
		Temperature2mMax         []float64 `json:"temperature_2m_max"`
		Temperature2mMin         []float64 `json:"temperature_2m_min"`
		PrecipitationProbability []int     `json:"precipitation_probability_max"`
	} `json:"daily"`
}
