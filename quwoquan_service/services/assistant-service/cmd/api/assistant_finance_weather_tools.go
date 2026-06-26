package main

import (
	"context"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
)

func yahooFinanceSymbols(input map[string]any) []string {
	symbols := []string{}
	add := func(raw any) {
		symbol := strings.ToUpper(strings.TrimSpace(fmt.Sprint(raw)))
		if symbol == "" || symbol == "<NIL>" {
			return
		}
		matched, _ := regexp.MatchString(`^[0-9]{6}\.(SZ|SS|SH)$|^[A-Z]{1,6}(\.[A-Z]{1,3})?$`, symbol)
		if matched {
			symbols = append(symbols, symbol)
		}
	}
	add(input["symbol"])
	switch items := input["symbols"].(type) {
	case []any:
		for _, item := range items {
			add(item)
		}
	case []string:
		for _, item := range items {
			add(item)
		}
	}
	query := inputString(input, "query")
	for _, match := range regexp.MustCompile(`[0-9]{6}\.(?:SZ|SS|SH)|[A-Z]{1,6}(?:\.[A-Z]{1,3})?`).FindAllString(strings.ToUpper(query), 4) {
		add(match)
	}
	if len(symbols) == 0 {
		return nil
	}
	seen := map[string]bool{}
	unique := []string{}
	for _, symbol := range symbols {
		if seen[symbol] {
			continue
		}
		seen[symbol] = true
		unique = append(unique, symbol)
	}
	return unique
}

func shouldTryFinanceLookup(skillID string, input map[string]any) bool {
	if strings.Contains(skillID, "finance") || strings.Contains(skillID, "stock") {
		return true
	}
	return inputString(input, "symbol") != "" || len(symbolList(input["symbols"])) > 0
}

func symbolList(raw any) []string {
	switch items := raw.(type) {
	case []any:
		out := []string{}
		for _, item := range items {
			text := strings.TrimSpace(fmt.Sprint(item))
			if text != "" && text != "<nil>" {
				out = append(out, text)
			}
		}
		return out
	case []string:
		return items
	default:
		return nil
	}
}

type yahooFinanceChartResponse struct {
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
				Timezone             string  `json:"timezone"`
				ExchangeName         string  `json:"exchangeName"`
			} `json:"meta"`
			Timestamp  []int64 `json:"timestamp"`
			Indicators struct {
				Quote []struct {
					Close []float64 `json:"close"`
				} `json:"quote"`
			} `json:"indicators"`
		} `json:"result"`
		Error any `json:"error"`
	} `json:"chart"`
}

func yahooFinanceSearch(ctx context.Context, client *http.Client, input map[string]any) (string, []map[string]any, bool) {
	symbols := yahooFinanceSymbols(input)
	if len(symbols) == 0 {
		return "", nil, false
	}
	parts := []string{}
	refs := []map[string]any{}
	for _, symbol := range symbols {
		endpoint := "https://query1.finance.yahoo.com/v8/finance/chart/" + url.PathEscape(symbol) + "?range=5d&interval=1d"
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
		if err != nil {
			continue
		}
		req.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
		resp, err := client.Do(req)
		if err != nil {
			log.Printf("assistant yahoo_finance failed symbol=%s err=%v", symbol, err)
			continue
		}
		func() {
			defer resp.Body.Close()
			if resp.StatusCode < 200 || resp.StatusCode >= 300 {
				log.Printf("assistant yahoo_finance status symbol=%s status=%d", symbol, resp.StatusCode)
				return
			}
			var decoded yahooFinanceChartResponse
			if err := json.NewDecoder(io.LimitReader(resp.Body, 128*1024)).Decode(&decoded); err != nil {
				log.Printf("assistant yahoo_finance decode failed symbol=%s err=%v", symbol, err)
				return
			}
			if len(decoded.Chart.Result) == 0 {
				return
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
			changePct := 0.0
			if meta.ChartPreviousClose != 0 {
				changePct = change / meta.ChartPreviousClose * 100
			}
			marketTime := time.Unix(meta.RegularMarketTime, 0).UTC().Format(time.RFC3339)
			snippet := fmt.Sprintf(
				"Yahoo Finance 行情：%s（%s，%s）最新价 %.2f %s，较前收 %.2f 变化 %.2f（%.2f%%），日内 %.2f-%.2f，成交量 %d，市场时间 %s。",
				name,
				meta.Symbol,
				meta.ExchangeName,
				meta.RegularMarketPrice,
				meta.Currency,
				meta.ChartPreviousClose,
				change,
				changePct,
				meta.RegularMarketDayLow,
				meta.RegularMarketDayHigh,
				meta.RegularMarketVolume,
				marketTime,
			)
			parts = append(parts, snippet)
			refs = append(refs, map[string]any{
				"title":   "Yahoo Finance - " + name + " (" + meta.Symbol + ")",
				"url":     endpoint,
				"source":  "yahoo_finance",
				"snippet": snippet,
			})
		}()
	}
	if len(parts) == 0 {
		return "", nil, false
	}
	return strings.Join(parts, "；"), refs, true
}

type bingRSS struct {
	Channel struct {
		Items []struct {
			Title       string `xml:"title"`
			Link        string `xml:"link"`
			Description string `xml:"description"`
			PubDate     string `xml:"pubDate"`
		} `xml:"item"`
	} `xml:"channel"`
}

func bingRSSSearch(ctx context.Context, client *http.Client, query string) (string, []map[string]any, bool) {
	query = strings.TrimSpace(query)
	if query == "" {
		return "", nil, false
	}
	endpoint := "https://www.bing.com/search?format=rss&q=" + url.QueryEscape(query)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "", nil, false
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 quwoquan-assistant-beta/1.0")
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("assistant bing_rss failed query=%q err=%v", query, err)
		return "", nil, false
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		log.Printf("assistant bing_rss status query=%q status=%d", query, resp.StatusCode)
		return "", nil, false
	}
	var decoded bingRSS
	if err := xml.NewDecoder(io.LimitReader(resp.Body, 128*1024)).Decode(&decoded); err != nil {
		log.Printf("assistant bing_rss decode failed query=%q err=%v", query, err)
		return "", nil, false
	}
	refs := []map[string]any{}
	parts := []string{}
	required := firstSearchToken(query)
	for _, item := range decoded.Channel.Items {
		title := cleanSearchText(item.Title)
		snippet := cleanSearchText(item.Description)
		if title == "" && snippet == "" {
			continue
		}
		if required != "" && !strings.Contains(title+snippet, required) {
			continue
		}
		if snippet == "" {
			snippet = title
		}
		parts = append(parts, snippet)
		refs = append(refs, map[string]any{
			"title":   title,
			"url":     strings.TrimSpace(item.Link),
			"source":  "bing_rss",
			"snippet": snippet,
			"pubDate": item.PubDate,
		})
		if len(refs) >= 5 {
			break
		}
	}
	if len(parts) == 0 {
		return "", nil, false
	}
	return truncateRunes(strings.Join(parts, "；"), 500), refs, true
}

func firstSearchToken(query string) string {
	for _, token := range strings.Fields(query) {
		token = strings.TrimSpace(token)
		if len([]rune(token)) >= 2 {
			return token
		}
	}
	return ""
}

func shouldTryWeatherLookup(skillID, query, location, locationSearchName string, input map[string]any) bool {
	normalized := strings.ToLower(strings.TrimSpace(query))
	weatherIntent := skillID == "weather" ||
		searchQueriesMentionWeather(input["searchQueries"]) ||
		searchQueriesMentionWeather(input["queries"]) ||
		strings.Contains(normalized, "天气") ||
		strings.Contains(normalized, "气温") ||
		strings.Contains(normalized, "降雨") ||
		strings.Contains(normalized, "weather") ||
		strings.Contains(normalized, "forecast")
	if !weatherIntent {
		return false
	}
	if strings.TrimSpace(location) != "" {
		return true
	}
	if strings.TrimSpace(locationSearchName) != "" {
		return true
	}
	return true
}

func searchQueriesMentionWeather(raw any) bool {
	switch items := raw.(type) {
	case []any:
		for _, item := range items {
			if searchQueryMentionsWeather(item) {
				return true
			}
		}
	case []map[string]any:
		for _, item := range items {
			if searchQueryMentionsWeather(item) {
				return true
			}
		}
	}
	return false
}

func searchQueryMentionsWeather(raw any) bool {
	text := strings.ToLower(strings.TrimSpace(fmt.Sprint(raw)))
	if text == "" || text == "<nil>" {
		return false
	}
	return strings.Contains(text, "天气") ||
		strings.Contains(text, "气温") ||
		strings.Contains(text, "降雨") ||
		strings.Contains(text, "weather") ||
		strings.Contains(text, "forecast")
}

func weatherLocationCandidate(query, location string) string {
	candidate := strings.TrimSpace(location)
	if candidate == "" {
		candidate = strings.TrimSpace(query)
	}
	replacements := []string{
		"天气预报", "", "天气", "", "气温", "", "温度", "", "预报", "",
		"weather", "", "forecast", "",
		"今天", "", "明天", "", "当前", "", "现在", "",
		"怎么样", "", "如何", "", "查询", "", "搜索", "",
		"？", "", "?", "", "。", "", "，", "", ",", "", "“", "", "”", "", "\"", "",
	}
	replacer := strings.NewReplacer(replacements...)
	candidate = strings.TrimSpace(replacer.Replace(candidate))
	if len([]rune(candidate)) > 24 {
		return ""
	}
	return candidate
}

type openMeteoGeocodeResponse struct {
	Results []struct {
		Name      string  `json:"name"`
		Latitude  float64 `json:"latitude"`
		Longitude float64 `json:"longitude"`
		Country   string  `json:"country"`
		Admin1    string  `json:"admin1"`
		Timezone  string  `json:"timezone"`
	} `json:"results"`
}

type openMeteoForecastResponse struct {
	Timezone string `json:"timezone"`
	Current  struct {
		Time             string  `json:"time"`
		Temperature2m    float64 `json:"temperature_2m"`
		ApparentTemp     float64 `json:"apparent_temperature"`
		RelativeHumidity int     `json:"relative_humidity_2m"`
		Precipitation    float64 `json:"precipitation"`
		WeatherCode      int     `json:"weather_code"`
		WindSpeed10m     float64 `json:"wind_speed_10m"`
	} `json:"current"`
	Daily struct {
		Time                     []string  `json:"time"`
		WeatherCode              []int     `json:"weather_code"`
		Temperature2mMax         []float64 `json:"temperature_2m_max"`
		Temperature2mMin         []float64 `json:"temperature_2m_min"`
		PrecipitationProbability []int     `json:"precipitation_probability_max"`
	} `json:"daily"`
}

type metNoForecastResponse struct {
	Properties struct {
		Timeseries []struct {
			Time string `json:"time"`
			Data struct {
				Instant struct {
					Details struct {
						AirTemperature   float64 `json:"air_temperature"`
						RelativeHumidity float64 `json:"relative_humidity"`
						WindSpeed        float64 `json:"wind_speed"`
					} `json:"details"`
				} `json:"instant"`
				Next1Hours struct {
					Summary struct {
						SymbolCode string `json:"symbol_code"`
					} `json:"summary"`
					Details struct {
						PrecipitationAmount float64 `json:"precipitation_amount"`
					} `json:"details"`
				} `json:"next_1_hours"`
				Next6Hours struct {
					Summary struct {
						SymbolCode string `json:"symbol_code"`
					} `json:"summary"`
					Details struct {
						PrecipitationAmount float64 `json:"precipitation_amount"`
					} `json:"details"`
				} `json:"next_6_hours"`
			} `json:"data"`
		} `json:"timeseries"`
	} `json:"properties"`
}

func openMeteoWeatherSearch(ctx context.Context, client *http.Client, query, location, locationSearchName string) (string, []map[string]any, string, bool) {
	candidates := []string{}
	if strings.TrimSpace(locationSearchName) != "" {
		candidates = append(candidates, strings.TrimSpace(locationSearchName))
	}
	candidate := weatherLocationCandidate(query, location)
	if candidate == "" {
		return "", nil, "", false
	}
	candidates = append(candidates, candidate)
	seenCandidates := map[string]bool{}
	for _, item := range candidates {
		if seenCandidates[item] {
			continue
		}
		seenCandidates[item] = true
		if summary, refs, provider, ok := openMeteoWeatherSearchCandidate(ctx, client, item); ok {
			return summary, refs, provider, true
		}
	}
	return "", nil, "", false
}

func openMeteoWeatherSearchCandidate(ctx context.Context, client *http.Client, candidate string) (string, []map[string]any, string, bool) {
	geoURL := "https://geocoding-api.open-meteo.com/v1/search?count=5&language=zh&format=json&name=" + url.QueryEscape(candidate)
	geoReq, err := http.NewRequestWithContext(ctx, http.MethodGet, geoURL, nil)
	if err != nil {
		return "", nil, "", false
	}
	geoReq.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
	geoResp, err := client.Do(geoReq)
	if err != nil {
		log.Printf("assistant open_meteo geocode failed location=%q err=%v", candidate, err)
		return "", nil, "", false
	}
	defer geoResp.Body.Close()
	if geoResp.StatusCode < 200 || geoResp.StatusCode >= 300 {
		log.Printf("assistant open_meteo geocode status location=%q status=%d", candidate, geoResp.StatusCode)
		return "", nil, "", false
	}
	var geo openMeteoGeocodeResponse
	if err := json.NewDecoder(io.LimitReader(geoResp.Body, 128*1024)).Decode(&geo); err != nil {
		log.Printf("assistant open_meteo geocode decode failed location=%q err=%v", candidate, err)
		return "", nil, "", false
	}
	if len(geo.Results) == 0 {
		log.Printf("assistant open_meteo geocode empty location=%q", candidate)
		return "", nil, "", false
	}
	place := geo.Results[0]
	tz := strings.TrimSpace(place.Timezone)
	if tz == "" {
		tz = "auto"
	}
	forecastURL := fmt.Sprintf(
		"https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=%s&forecast_days=3",
		strconv.FormatFloat(place.Latitude, 'f', -1, 64),
		strconv.FormatFloat(place.Longitude, 'f', -1, 64),
		url.QueryEscape(tz),
	)
	forecastReq, err := http.NewRequestWithContext(ctx, http.MethodGet, forecastURL, nil)
	if err != nil {
		return "", nil, "", false
	}
	forecastReq.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0")
	forecastResp, err := client.Do(forecastReq)
	if err != nil {
		log.Printf("assistant open_meteo forecast failed location=%q err=%v", candidate, err)
		return metNoWeatherSearch(ctx, client, place.Name, place.Admin1, place.Latitude, place.Longitude)
	}
	defer forecastResp.Body.Close()
	if forecastResp.StatusCode < 200 || forecastResp.StatusCode >= 300 {
		log.Printf("assistant open_meteo forecast status location=%q status=%d", candidate, forecastResp.StatusCode)
		return metNoWeatherSearch(ctx, client, place.Name, place.Admin1, place.Latitude, place.Longitude)
	}
	var forecast openMeteoForecastResponse
	if err := json.NewDecoder(io.LimitReader(forecastResp.Body, 128*1024)).Decode(&forecast); err != nil {
		log.Printf("assistant open_meteo forecast decode failed location=%q err=%v", candidate, err)
		return "", nil, "", false
	}
	placeName := place.Name
	if place.Admin1 != "" {
		placeName = placeName + "，" + place.Admin1
	}
	current := forecast.Current
	dailyParts := []string{}
	for i := range forecast.Daily.Time {
		if i >= 3 || i >= len(forecast.Daily.Temperature2mMax) || i >= len(forecast.Daily.Temperature2mMin) {
			break
		}
		weather := ""
		if i < len(forecast.Daily.WeatherCode) {
			weather = weatherCodeText(forecast.Daily.WeatherCode[i])
		}
		precip := ""
		if i < len(forecast.Daily.PrecipitationProbability) {
			precip = fmt.Sprintf("，降水概率%d%%", forecast.Daily.PrecipitationProbability[i])
		}
		dailyParts = append(dailyParts, fmt.Sprintf("%s：%s，%.0f-%.0f°C%s", forecast.Daily.Time[i], weather, forecast.Daily.Temperature2mMin[i], forecast.Daily.Temperature2mMax[i], precip))
	}
	summary := fmt.Sprintf(
		"Open-Meteo 实时天气：%s 当前%s，气温%.1f°C，体感%.1f°C，湿度%d%%，降水%.1fmm，风速%.1fkm/h。未来三天：%s。数据时间：%s（%s）。",
		placeName,
		weatherCodeText(current.WeatherCode),
		current.Temperature2m,
		current.ApparentTemp,
		current.RelativeHumidity,
		current.Precipitation,
		current.WindSpeed10m,
		strings.Join(dailyParts, "；"),
		current.Time,
		tz,
	)
	summary = withLocalWeatherAuthoritySummary(candidate, placeName, "Open-Meteo", summary)
	refs := []map[string]any{
		{
			"title":   "Open-Meteo Forecast API - " + placeName,
			"url":     "https://open-meteo.com/en/docs",
			"source":  "open_meteo_forecast",
			"snippet": summary + " 原始 forecast endpoint: " + forecastURL,
		},
		{
			"title":   "Open-Meteo Geocoding API - " + placeName,
			"url":     "https://open-meteo.com/en/docs/geocoding-api",
			"source":  "open_meteo_geocoding",
			"snippet": fmt.Sprintf("地理解析命中：%s，经纬度 %.5f, %.5f，时区 %s。原始 geocoding endpoint: %s", placeName, place.Latitude, place.Longitude, tz, geoURL),
		},
		{
			"title":   "Open-Meteo Weather Forecast API 文档",
			"url":     "https://open-meteo.com/en/docs",
			"source":  "open_meteo_docs",
			"snippet": "Open-Meteo 天气预报接口说明，包含 current 与 daily 预报字段定义。",
		},
	}
	refs = withLocalWeatherAuthorityReferences(candidate, placeName, refs)
	return summary, refs, "open_meteo", true
}

func metNoWeatherSearch(ctx context.Context, client *http.Client, name, admin string, lat, lon float64) (string, []map[string]any, string, bool) {
	endpoint := fmt.Sprintf(
		"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%s&lon=%s",
		strconv.FormatFloat(lat, 'f', -1, 64),
		strconv.FormatFloat(lon, 'f', -1, 64),
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "", nil, "", false
	}
	req.Header.Set("User-Agent", "quwoquan-assistant-beta/1.0 contact=dev@quwoquan.local")
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("assistant met_no forecast failed location=%q err=%v", name, err)
		return "", nil, "", false
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		log.Printf("assistant met_no forecast status location=%q status=%d", name, resp.StatusCode)
		return "", nil, "", false
	}
	var forecast metNoForecastResponse
	if err := json.NewDecoder(io.LimitReader(resp.Body, 256*1024)).Decode(&forecast); err != nil {
		log.Printf("assistant met_no forecast decode failed location=%q err=%v", name, err)
		return "", nil, "", false
	}
	if len(forecast.Properties.Timeseries) == 0 {
		log.Printf("assistant met_no forecast empty location=%q", name)
		return "", nil, "", false
	}
	placeName := strings.TrimSpace(name)
	if strings.TrimSpace(admin) != "" {
		placeName = placeName + "，" + strings.TrimSpace(admin)
	}
	current := forecast.Properties.Timeseries[0]
	details := current.Data.Instant.Details
	symbol := strings.ReplaceAll(current.Data.Next1Hours.Summary.SymbolCode, "_", " ")
	if symbol == "" {
		symbol = strings.ReplaceAll(current.Data.Next6Hours.Summary.SymbolCode, "_", " ")
	}
	precip := current.Data.Next1Hours.Details.PrecipitationAmount
	if precip == 0 {
		precip = current.Data.Next6Hours.Details.PrecipitationAmount
	}
	summary := fmt.Sprintf(
		"MET Norway Locationforecast 实时天气：%s 当前气温%.1f°C，湿度%.0f%%，风速%.1fm/s，近期天气符号%s，未来降水量%.1fmm。数据时间：%s。",
		placeName,
		details.AirTemperature,
		details.RelativeHumidity,
		details.WindSpeed,
		symbol,
		precip,
		current.Time,
	)
	summary = withLocalWeatherAuthoritySummary(name+" "+admin, placeName, "MET Norway", summary)
	refs := []map[string]any{
		{
			"title":   "MET Norway Locationforecast - " + placeName,
			"url":     "https://api.met.no/weatherapi/locationforecast/2.0/documentation",
			"source":  "met_no_locationforecast",
			"snippet": summary + " 原始 endpoint: " + endpoint,
		},
		{
			"title":   "MET Norway Locationforecast 数据模型说明",
			"url":     "https://api.met.no/weatherapi/locationforecast/2.0/documentation",
			"source":  "met_no_locationforecast_docs",
			"snippet": "Locationforecast 接口说明，包含 instant、next_1_hours、next_6_hours 等字段定义。",
		},
		{
			"title":   "Norwegian Meteorological Institute API Terms",
			"url":     "https://developer.yr.no/doc/TermsOfService/",
			"source":  "met_no_terms",
			"snippet": "MET Norway / Yr 开放天气 API 使用条款与数据来源说明。",
		},
	}
	refs = withLocalWeatherAuthorityReferences(name+" "+admin, placeName, refs)
	return summary, refs, "met_no", true
}

func withLocalWeatherAuthoritySummary(query, placeName, structuredProvider, summary string) string {
	if len(weatherAuthorityReferences(query, placeName)) == 0 {
		return summary
	}
	provider := strings.TrimSpace(structuredProvider)
	if provider == "" {
		provider = "结构化天气 API"
	}
	return "天气证据优先按国家级气象服务入口与可解析的省/自治区/直辖市气象局排序；" +
		provider + " 仅作为实时温度、湿度、风力、降水等结构化数据补充。 " + summary
}

func withLocalWeatherAuthorityReferences(query, placeName string, refs []map[string]any) []map[string]any {
	authorityRefs := weatherAuthorityReferences(query, placeName)
	if len(authorityRefs) == 0 {
		return refs
	}
	merged := make([]map[string]any, 0, len(authorityRefs)+len(refs))
	seen := map[string]bool{}
	appendRef := func(ref map[string]any) {
		rawURL, _ := ref["url"].(string)
		key := strings.TrimSpace(rawURL)
		if key != "" {
			if seen[key] {
				return
			}
			seen[key] = true
		}
		merged = append(merged, ref)
	}
	for _, ref := range authorityRefs {
		appendRef(ref)
	}
	for _, ref := range refs {
		appendRef(ref)
	}
	for i := range merged {
		merged[i]["rank"] = i + 1
	}
	return merged
}

func weatherAuthorityReferences(query, placeName string) []map[string]any {
	refs := []map[string]any{
		{
			"title":   "中国天气网",
			"url":     "https://www.weather.com.cn/",
			"source":  "weather_com_cn",
			"snippet": "中国天气网为国家级天气服务入口，可按城市查询实况、预报、生活指数等信息。",
		},
		{
			"title":   "中央气象台",
			"url":     "https://www.nmc.cn/",
			"source":  "national_meteorological_center",
			"snippet": "中央气象台提供全国天气预报、气象预警、降水、台风和雷达等国家级气象服务。",
		},
		{
			"title":   "中国气象局",
			"url":     "https://www.cma.gov.cn/",
			"source":  "china_meteorological_administration",
			"snippet": "中国气象局为国家气象主管机构入口，可用于核验权威气象服务和区域气象机构信息。",
		},
	}
	if ref, ok := regionalWeatherAuthorityReference(query + " " + placeName); ok {
		refs = append(refs, ref)
	}
	return refs
}

func regionalWeatherAuthorityReference(raw string) (map[string]any, bool) {
	normalized := strings.ToLower(raw)
	regionRefs := []struct {
		keywords []string
		title    string
		url      string
		source   string
	}{
		{[]string{"北京", "beijing"}, "北京市气象局", "http://bj.cma.gov.cn/", "beijing_meteorological_bureau"},
		{[]string{"上海", "shanghai"}, "上海市气象局", "http://sh.cma.gov.cn/", "shanghai_meteorological_bureau"},
		{[]string{"天津", "tianjin"}, "天津市气象局", "http://tj.cma.gov.cn/", "tianjin_meteorological_bureau"},
		{[]string{"重庆", "chongqing"}, "重庆市气象局", "http://cq.cma.gov.cn/", "chongqing_meteorological_bureau"},
		{[]string{"河北", "hebei"}, "河北省气象局", "http://he.cma.gov.cn/", "hebei_meteorological_bureau"},
		{[]string{"山西", "shanxi"}, "山西省气象局", "http://sx.cma.gov.cn/", "shanxi_meteorological_bureau"},
		{[]string{"内蒙古", "inner mongolia"}, "内蒙古自治区气象局", "http://nm.cma.gov.cn/", "inner_mongolia_meteorological_bureau"},
		{[]string{"辽宁", "liaoning"}, "辽宁省气象局", "http://ln.cma.gov.cn/", "liaoning_meteorological_bureau"},
		{[]string{"吉林", "jilin"}, "吉林省气象局", "http://jl.cma.gov.cn/", "jilin_meteorological_bureau"},
		{[]string{"黑龙江", "heilongjiang"}, "黑龙江省气象局", "http://hl.cma.gov.cn/", "heilongjiang_meteorological_bureau"},
		{[]string{"江苏", "jiangsu"}, "江苏省气象局", "http://js.cma.gov.cn/", "jiangsu_meteorological_bureau"},
		{[]string{"浙江", "zhejiang"}, "浙江省气象局", "http://zj.cma.gov.cn/", "zhejiang_meteorological_bureau"},
		{[]string{"安徽", "anhui"}, "安徽省气象局", "http://ah.cma.gov.cn/", "anhui_meteorological_bureau"},
		{[]string{"福建", "fujian"}, "福建省气象局", "http://fj.cma.gov.cn/", "fujian_meteorological_bureau"},
		{[]string{"江西", "jiangxi"}, "江西省气象局", "http://jx.cma.gov.cn/", "jiangxi_meteorological_bureau"},
		{[]string{"山东", "shandong"}, "山东省气象局", "http://sd.cma.gov.cn/", "shandong_meteorological_bureau"},
		{[]string{"河南", "henan"}, "河南省气象局", "http://ha.cma.gov.cn/", "henan_meteorological_bureau"},
		{[]string{"湖北", "hubei"}, "湖北省气象局", "http://hb.cma.gov.cn/", "hubei_meteorological_bureau"},
		{[]string{"湖南", "hunan"}, "湖南省气象局", "http://hn.cma.gov.cn/", "hunan_meteorological_bureau"},
		{[]string{"广东", "guangdong"}, "广东省气象局", "http://gd.cma.gov.cn/", "guangdong_meteorological_bureau"},
		{[]string{"广西", "guangxi"}, "广西壮族自治区气象局", "http://gx.cma.gov.cn/", "guangxi_meteorological_bureau"},
		{[]string{"海南", "hainan"}, "海南省气象局", "http://hi.cma.gov.cn/", "hainan_meteorological_bureau"},
		{[]string{"四川", "sichuan"}, "四川省气象局", "http://sc.cma.gov.cn/", "sichuan_meteorological_bureau"},
		{[]string{"贵州", "guizhou"}, "贵州省气象局", "http://gz.cma.gov.cn/", "guizhou_meteorological_bureau"},
		{[]string{"云南", "yunnan"}, "云南省气象局", "http://yn.cma.gov.cn/", "yunnan_meteorological_bureau"},
		{[]string{"西藏", "tibet", "xizang"}, "西藏自治区气象局", "http://xz.cma.gov.cn/", "xizang_meteorological_bureau"},
		{[]string{"陕西", "shaanxi"}, "陕西省气象局", "http://sn.cma.gov.cn/", "shaanxi_meteorological_bureau"},
		{[]string{"甘肃", "gansu"}, "甘肃省气象局", "http://gs.cma.gov.cn/", "gansu_meteorological_bureau"},
		{[]string{"青海", "qinghai"}, "青海省气象局", "http://qh.cma.gov.cn/", "qinghai_meteorological_bureau"},
		{[]string{"宁夏", "ningxia"}, "宁夏回族自治区气象局", "http://nx.cma.gov.cn/", "ningxia_meteorological_bureau"},
		{[]string{"新疆", "xinjiang"}, "新疆维吾尔自治区气象局", "http://xj.cma.gov.cn/", "xinjiang_meteorological_bureau"},
	}
	for _, ref := range regionRefs {
		for _, keyword := range ref.keywords {
			if strings.Contains(normalized, strings.ToLower(keyword)) {
				return map[string]any{
					"title":   ref.title,
					"url":     ref.url,
					"source":  ref.source,
					"snippet": ref.title + "为区域气象服务入口，可用于核验该省/自治区/直辖市范围内的天气预报、预警和实况信息。",
				}, true
			}
		}
	}
	return nil, false
}

func weatherCodeText(code int) string {
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
