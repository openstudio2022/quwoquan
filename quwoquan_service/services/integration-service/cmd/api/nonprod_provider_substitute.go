package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const nonprodProviderSubstituteDefaultAddr = ":18089"

// nonprodProviderSubstitute 是 Alpha/Beta/Gamma 共用的第三方协议替代面。
// 它运行在 integration-service 的独立内部端口，不挂载到 API edge；
// Assistant/Content 仍经各自的正式 typed Port 与 wire decoder 调用。
// Prod 不启动该 listener，并继续由环境 Binding 选择真实厂商 Adapter。
type nonprodProviderSubstitute struct {
	server   *http.Server
	listener net.Listener
	ready    atomic.Bool
	mu       sync.Mutex
	counts   map[string]uint64
}

func startNonprodProviderSubstitute(
	environment string,
) (*nonprodProviderSubstitute, error) {
	switch strings.TrimSpace(environment) {
	case "alpha", "beta", "gamma":
	case "prod":
		return nil, nil
	default:
		return nil, fmt.Errorf(
			"nonprod provider substitute received unsupported environment %q",
			environment,
		)
	}
	addr := strings.TrimSpace(os.Getenv("NONPROD_PROVIDER_SUBSTITUTE_ADDR"))
	if addr == "" {
		addr = nonprodProviderSubstituteDefaultAddr
	}
	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("listen on %s: %w", addr, err)
	}
	substitute := &nonprodProviderSubstitute{
		listener: listener,
		counts:   make(map[string]uint64),
	}
	substitute.server = &http.Server{
		Addr:              addr,
		Handler:           substitute.routes(),
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       30 * time.Second,
	}
	substitute.ready.Store(true)
	go func() {
		if serveErr := substitute.server.Serve(listener); serveErr != nil &&
			serveErr != http.ErrServerClosed {
			substitute.ready.Store(false)
		}
	}()
	return substitute, nil
}

func (s *nonprodProviderSubstitute) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.healthHandler)
	mux.HandleFunc("GET /receipts", s.receiptsHandler)
	mux.HandleFunc("POST /v1/chat/completions", s.modelCompletionHandler)
	mux.HandleFunc("POST /v1/embeddings", s.embeddingHandler)
	mux.HandleFunc("GET /search/html", s.searchHandler)
	mux.HandleFunc("GET /weather/geocoding", s.weatherGeocodingHandler)
	mux.HandleFunc("GET /weather/forecast", s.weatherForecastHandler)
	mux.HandleFunc("GET /finance/chart/", s.financeChartHandler)
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Cache-Control", "no-store")
		writer.Header().Set("X-Content-Type-Options", "nosniff")
		mux.ServeHTTP(writer, request)
	})
}

func (s *nonprodProviderSubstitute) close(ctx context.Context) error {
	if s == nil {
		return nil
	}
	s.ready.Store(false)
	return s.server.Shutdown(ctx)
}

func (s *nonprodProviderSubstitute) health(_ context.Context) error {
	if s == nil || !s.ready.Load() {
		return fmt.Errorf("nonprod provider substitute is not ready")
	}
	return nil
}

func (s *nonprodProviderSubstitute) record(capability string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.counts[capability]++
}

func (s *nonprodProviderSubstitute) healthHandler(
	writer http.ResponseWriter,
	_ *http.Request,
) {
	if !s.ready.Load() {
		http.Error(writer, "unavailable", http.StatusServiceUnavailable)
		return
	}
	writeProviderSubstituteJSON(writer, http.StatusOK, map[string]any{
		"status": "ready",
		"mode":   "nonprod_protocol_substitute",
	})
}

func (s *nonprodProviderSubstitute) receiptsHandler(
	writer http.ResponseWriter,
	_ *http.Request,
) {
	s.mu.Lock()
	counts := make(map[string]uint64, len(s.counts))
	for capability, count := range s.counts {
		counts[capability] = count
	}
	s.mu.Unlock()
	writeProviderSubstituteJSON(writer, http.StatusOK, map[string]any{
		"status": "ready",
		"calls":  counts,
	})
}

type modelCompletionSubstituteRequest struct {
	Messages []struct {
		Role    string `json:"role"`
		Content string `json:"content"`
	} `json:"messages"`
	Stream bool `json:"stream"`
}

func (s *nonprodProviderSubstitute) modelCompletionHandler(
	writer http.ResponseWriter,
	request *http.Request,
) {
	var payload modelCompletionSubstituteRequest
	if err := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 1<<20)).Decode(&payload); err != nil {
		http.Error(writer, "invalid request", http.StatusBadRequest)
		return
	}
	content := nonprodModelResponse(payload)
	if payload.Stream {
		writer.Header().Set("Content-Type", "text/event-stream")
		writer.WriteHeader(http.StatusOK)
		chunk := map[string]any{
			"choices": []map[string]any{{
				"delta":         map[string]any{"content": content},
				"finish_reason": "stop",
			}},
			"usage": map[string]int{
				"prompt_tokens": 8, "completion_tokens": 8, "total_tokens": 16,
			},
		}
		encoded, _ := json.Marshal(chunk)
		_, _ = fmt.Fprintf(writer, "data: %s\n\ndata: [DONE]\n\n", encoded)
	} else {
		writeProviderSubstituteJSON(writer, http.StatusOK, map[string]any{
			"choices": []map[string]any{{
				"message":       map[string]any{"role": "assistant", "content": content},
				"finish_reason": "stop",
			}},
			"usage": map[string]int{
				"prompt_tokens": 8, "completion_tokens": 8, "total_tokens": 16,
			},
		})
	}
	s.record("assistant.model.generation")
}

func nonprodModelResponse(request modelCompletionSubstituteRequest) string {
	system := ""
	for _, message := range request.Messages {
		if strings.EqualFold(strings.TrimSpace(message.Role), "system") {
			system = message.Content
			break
		}
	}
	switch {
	case strings.Contains(system, "技能选择器"):
		return `{"skillId":"daily_assistant","reason":"非生产协议替代返回可复核的技能选择"}`
	case strings.Contains(system, "problemShape"):
		return `{"problemShape":"single_skill","subagentPlan":[]}`
	case strings.Contains(system, "nextAction"):
		return `{"nextAction":"ask_user","toolName":"","toolInput":{},"stageNarrative":"你可以继续补充需要验证的具体目标。","askUser":{"slotId":"nonprod_clarification","prompt":"请补充你希望验证的具体目标","required":true,"suggestions":[]}}`
	case strings.Contains(system, "retrievalProcessing"):
		return `{"retrievalProcessing":{"processingSummary":"你的非生产协议链路已完成验证。","selectedKeyPoints":[],"acceptedReferences":[]},"evidenceSufficient":true}`
	default:
		return "你当前使用的是 Alpha/Beta/Gamma 隔离协议替代链路；请以此结果验证页面、恢复动作与可观测回读。"
	}
}

type embeddingSubstituteRequest struct {
	Input []string `json:"input"`
}

func (s *nonprodProviderSubstitute) embeddingHandler(
	writer http.ResponseWriter,
	request *http.Request,
) {
	var payload embeddingSubstituteRequest
	if err := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 2<<20)).Decode(&payload); err != nil || len(payload.Input) == 0 || len(payload.Input) > 64 {
		http.Error(writer, "invalid request", http.StatusBadRequest)
		return
	}
	data := make([]map[string]any, 0, len(payload.Input))
	for index, text := range payload.Input {
		vector := make([]float64, 1536)
		digest := sha256.Sum256([]byte(text))
		vector[int(digest[0])%len(vector)] = 1
		vector[(int(digest[1])+256)%len(vector)] = 0.5
		data = append(data, map[string]any{
			"embedding": vector,
			"index":     index,
		})
	}
	writeProviderSubstituteJSON(writer, http.StatusOK, map[string]any{"data": data})
	s.record("content.embedding.generation")
}

func (s *nonprodProviderSubstitute) searchHandler(
	writer http.ResponseWriter,
	_ *http.Request,
) {
	writer.Header().Set("Content-Type", "text/html; charset=utf-8")
	writer.WriteHeader(http.StatusOK)
	_, _ = writer.Write([]byte(`<html><body><a class="result__a">非生产隔离搜索结果</a><div class="result__snippet">该结果由受管协议替代服务生成，仅用于 Alpha/Beta/Gamma 功能验证。</div></body></html>`))
	s.record("assistant.public.search")
}

func (s *nonprodProviderSubstitute) weatherGeocodingHandler(
	writer http.ResponseWriter,
	_ *http.Request,
) {
	writeProviderSubstituteJSON(writer, http.StatusOK, map[string]any{
		"results": []map[string]any{{
			"name": "杭州", "admin1": "浙江", "latitude": 30.2741,
			"longitude": 120.1551, "timezone": "Asia/Shanghai",
		}},
	})
	s.record("assistant.weather.geocoding")
}

func (s *nonprodProviderSubstitute) weatherForecastHandler(
	writer http.ResponseWriter,
	_ *http.Request,
) {
	writeProviderSubstituteJSON(writer, http.StatusOK, map[string]any{
		"current": map[string]any{
			"time": "2026-08-02T12:00", "temperature_2m": 28.0,
			"apparent_temperature": 29.0, "relative_humidity_2m": 64,
			"precipitation": 0.0, "weather_code": 1, "wind_speed_10m": 6.0,
		},
		"daily": map[string]any{
			"time":                          []string{"2026-08-02", "2026-08-03", "2026-08-04"},
			"weather_code":                  []int{1, 2, 3},
			"temperature_2m_max":            []float64{31, 32, 30},
			"temperature_2m_min":            []float64{24, 25, 23},
			"precipitation_probability_max": []int{10, 20, 30},
		},
	})
	s.record("assistant.weather.forecast")
}

func (s *nonprodProviderSubstitute) financeChartHandler(
	writer http.ResponseWriter,
	request *http.Request,
) {
	symbol := strings.TrimSpace(strings.TrimPrefix(request.URL.Path, "/finance/chart/"))
	if symbol == "" {
		http.Error(writer, "symbol is required", http.StatusBadRequest)
		return
	}
	writeProviderSubstituteJSON(writer, http.StatusOK, map[string]any{
		"chart": map[string]any{"result": []map[string]any{{
			"meta": map[string]any{
				"symbol": symbol, "currency": "CNY", "longName": "非生产行情样本",
				"regularMarketTime": 1785643200, "regularMarketPrice": 10.5,
				"regularMarketDayHigh": 10.8, "regularMarketDayLow": 10.1,
				"regularMarketVolume": 1000, "chartPreviousClose": 10.2,
				"exchangeName": "NONPROD",
			},
		}}},
	})
	s.record("assistant.finance.quote")
}

func writeProviderSubstituteJSON(
	writer http.ResponseWriter,
	status int,
	payload any,
) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}
