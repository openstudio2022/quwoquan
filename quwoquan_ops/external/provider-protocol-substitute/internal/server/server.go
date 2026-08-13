package server

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const AdapterID = "ops.provider_protocol_substitute"

type Config struct {
	Environment              string
	ConfigurationDigest      string
	RuntimeCompositionDigest string
	OperatorToken            string
}

type Server struct {
	environment              string
	target                   string
	configurationDigest      string
	runtimeCompositionDigest string
	operatorToken            string
	ready                    atomic.Bool
	mu                       sync.Mutex
	counts                   map[string]uint64
	effectCounts             map[string]uint64
	leases                   map[string]*FaultLease
	activeLeaseByScope       map[string]string
	idempotencyRecords       map[string]*idempotencyRecord
	callbackChannels         map[string]*CallbackChannel
	ledger                   []InvocationLedgerEntry
	callOrdinal              uint64
	now                      func() time.Time
	sleep                    func(time.Duration)
}

func New(cfg Config) (*Server, error) {
	return newServer(cfg, time.Now, time.Sleep)
}

func newServer(
	cfg Config,
	now func() time.Time,
	sleep func(time.Duration),
) (*Server, error) {
	environment := strings.TrimSpace(cfg.Environment)
	switch environment {
	case "alpha", "beta", "gamma":
	default:
		return nil, fmt.Errorf("provider protocol substitute forbids environment %q", environment)
	}
	configurationDigest := strings.TrimSpace(cfg.ConfigurationDigest)
	if !isSHA256Digest(configurationDigest) {
		return nil, errors.New("provider protocol substitute configuration digest is required")
	}
	runtimeCompositionDigest := strings.TrimSpace(cfg.RuntimeCompositionDigest)
	if !isSHA256Digest(runtimeCompositionDigest) {
		return nil, errors.New("provider protocol substitute runtime composition digest is required")
	}
	operatorToken := strings.TrimSpace(cfg.OperatorToken)
	if len(operatorToken) < 24 {
		return nil, errors.New("provider protocol substitute operator token is too short")
	}
	if now == nil || sleep == nil {
		return nil, errors.New("provider protocol substitute clock is required")
	}
	server := &Server{
		environment:              environment,
		target:                   environment + "-local",
		configurationDigest:      configurationDigest,
		runtimeCompositionDigest: runtimeCompositionDigest,
		operatorToken:            operatorToken,
		counts:                   make(map[string]uint64),
		effectCounts:             make(map[string]uint64),
		leases:                   make(map[string]*FaultLease),
		activeLeaseByScope:       make(map[string]string),
		idempotencyRecords:       make(map[string]*idempotencyRecord),
		callbackChannels:         make(map[string]*CallbackChannel),
		now:                      now,
		sleep:                    sleep,
	}
	server.ready.Store(true)
	return server, nil
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.health)
	mux.HandleFunc("POST /control/fault-leases", s.authorizeOperator(s.acquireFaultLease))
	mux.HandleFunc("GET /control/fault-leases/{leaseId}", s.authorizeOperator(s.readFaultLease))
	mux.HandleFunc("DELETE /control/fault-leases/{leaseId}", s.authorizeOperator(s.releaseFaultLease))
	mux.HandleFunc("POST /control/callback-channels", s.authorizeOperator(s.acquireCallbackChannel))
	mux.HandleFunc("GET /control/callback-channels/{channelId}", s.authorizeOperator(s.readCallbackChannel))
	mux.HandleFunc("DELETE /control/callback-channels/{channelId}", s.authorizeOperator(s.releaseCallbackChannel))
	mux.HandleFunc("GET /control/readback", s.authorizeOperator(s.readback))
	mux.HandleFunc("POST /v1/chat/completions", s.modelCompletion)
	mux.HandleFunc("POST /v1/embeddings", s.provider("content.embedding.generation", "embed", s.embedding))
	mux.HandleFunc("GET /search/html", s.provider("assistant.public.search", "search", s.search))
	mux.HandleFunc("GET /weather/geocoding", s.provider("assistant.weather.forecast", "forecast", s.weatherGeocoding))
	mux.HandleFunc("GET /weather/forecast", s.provider("assistant.weather.forecast", "forecast", s.weatherForecast))
	mux.HandleFunc("GET /finance/chart/", s.provider("assistant.finance.quote", "quote", s.financeChart))
	mux.HandleFunc("GET /map/reverse_geocoding/v3/", s.provider("integration.location.lookup", "nearby", s.locationNearby))
	mux.HandleFunc("GET /map/place/v2/search", s.provider("integration.location.lookup", "search", s.locationSearch))
	mux.HandleFunc("GET /nominatim/search", s.provider("location.poi.search", "search", s.nominatimSearch))
	mux.HandleFunc("GET /osrm/route/v1/", s.provider("location.route.read", "route", s.osrmRoute))
	mux.HandleFunc("POST /carrier/resolve", s.provider("identity.carrier.one_tap", "resolvePhone", s.carrierResolve))
	mux.HandleFunc("POST /federated/verify", s.federatedDispatch)
	mux.HandleFunc("POST /push/send", s.provider("integration.push.delivery", "deliver", s.pushSend))
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Cache-Control", "no-store")
		writer.Header().Set("X-Content-Type-Options", "nosniff")
		writer.Header().Set("Referrer-Policy", "no-referrer")
		prepared, ok := s.prepareProviderRequest(writer, request)
		if !ok {
			return
		}
		mux.ServeHTTP(writer, prepared)
	})
}

func (s *Server) provider(
	capability string,
	operation string,
	next http.HandlerFunc,
) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		s.invokeProvider(writer, request, capability, operation, next)
	}
}

func (s *Server) authorizeOperator(next http.HandlerFunc) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		values := request.Header.Values("Authorization")
		if len(values) != 1 || !strings.HasPrefix(values[0], "Bearer ") {
			http.Error(writer, "unauthorized", http.StatusUnauthorized)
			return
		}
		provided := strings.TrimPrefix(values[0], "Bearer ")
		if strings.TrimSpace(provided) != provided || strings.ContainsAny(provided, " \t\r\n") {
			http.Error(writer, "unauthorized", http.StatusUnauthorized)
			return
		}
		if subtle.ConstantTimeCompare([]byte(provided), []byte(s.operatorToken)) != 1 {
			http.Error(writer, "unauthorized", http.StatusUnauthorized)
			return
		}
		next(writer, request)
	}
}

func (s *Server) health(writer http.ResponseWriter, _ *http.Request) {
	status := http.StatusOK
	if !s.ready.Load() {
		status = http.StatusServiceUnavailable
	}
	writeJSON(writer, status, map[string]any{
		"status":                   map[bool]string{true: "ready", false: "unavailable"}[s.ready.Load()],
		"adapterId":                AdapterID,
		"environment":              s.environment,
		"target":                   s.target,
		"configurationDigest":      s.configurationDigest,
		"runtimeCompositionDigest": s.runtimeCompositionDigest,
		"nonPromotable":            true,
		"conformanceMechanisms": []string{
			"tls_dns_authority",
			"idempotency_ledger",
			"callback_channel_ordering",
		},
		"activeFaultLeases": s.activeLeaseSummaries(),
	})
}

type modelCompletionRequest struct {
	Messages []struct {
		Role    string `json:"role"`
		Content string `json:"content"`
	} `json:"messages"`
	Stream bool `json:"stream"`
}

func (s *Server) modelCompletion(writer http.ResponseWriter, request *http.Request) {
	var payload modelCompletionRequest
	if err := decodeJSON(writer, request, 1<<20, &payload); err != nil {
		return
	}
	operation := "complete"
	if payload.Stream {
		operation = "stream"
	}
	s.invokeProvider(writer, request, "assistant.model.generation", operation, func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		s.writeModelCompletion(writer, payload)
	})
}

func (s *Server) writeModelCompletion(writer http.ResponseWriter, payload modelCompletionRequest) {
	content := modelResponse(payload)
	usage := map[string]int{"prompt_tokens": 8, "completion_tokens": 8, "total_tokens": 16}
	if payload.Stream {
		writer.Header().Set("Content-Type", "text/event-stream")
		writer.WriteHeader(http.StatusOK)
		chunk := map[string]any{
			"choices": []map[string]any{{
				"delta": map[string]any{"content": content}, "finish_reason": "stop",
			}},
			"usage": usage,
		}
		encoded, _ := json.Marshal(chunk)
		_, _ = fmt.Fprintf(writer, "data: %s\n\ndata: [DONE]\n\n", encoded)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"choices": []map[string]any{{
			"message": map[string]any{"role": "assistant", "content": content}, "finish_reason": "stop",
		}},
		"usage": usage,
	})
}

func modelResponse(request modelCompletionRequest) string {
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

func (s *Server) embedding(writer http.ResponseWriter, request *http.Request) {
	var payload struct {
		Input []string `json:"input"`
	}
	if err := decodeJSON(writer, request, 2<<20, &payload); err != nil {
		return
	}
	if len(payload.Input) == 0 || len(payload.Input) > 64 {
		http.Error(writer, "invalid request", http.StatusBadRequest)
		return
	}
	data := make([]map[string]any, 0, len(payload.Input))
	for index, text := range payload.Input {
		vector := make([]float64, 1536)
		digest := sha256.Sum256([]byte(text))
		vector[int(digest[0])%len(vector)] = 1
		vector[(int(digest[1])+256)%len(vector)] = 0.5
		data = append(data, map[string]any{"embedding": vector, "index": index})
	}
	writeJSON(writer, http.StatusOK, map[string]any{"data": data})
}

func (s *Server) search(writer http.ResponseWriter, _ *http.Request) {
	writer.Header().Set("Content-Type", "text/html; charset=utf-8")
	writer.WriteHeader(http.StatusOK)
	_, _ = writer.Write([]byte(`<html><body><a class="result__a">非生产隔离搜索结果</a><div class="result__snippet">该结果由受管协议替代服务生成，仅用于 Alpha/Beta/Gamma 功能验证。</div></body></html>`))
}

func (s *Server) weatherGeocoding(writer http.ResponseWriter, _ *http.Request) {
	writeJSON(writer, http.StatusOK, map[string]any{
		"results": []map[string]any{{
			"name": "杭州", "admin1": "浙江", "latitude": 30.2741,
			"longitude": 120.1551, "timezone": "Asia/Shanghai",
		}},
	})
}

func (s *Server) weatherForecast(writer http.ResponseWriter, _ *http.Request) {
	writeJSON(writer, http.StatusOK, map[string]any{
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
}

func (s *Server) financeChart(writer http.ResponseWriter, request *http.Request) {
	symbol := strings.TrimSpace(strings.TrimPrefix(request.URL.Path, "/finance/chart/"))
	if symbol == "" {
		http.Error(writer, "symbol is required", http.StatusBadRequest)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
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
}

func (s *Server) locationNearby(writer http.ResponseWriter, request *http.Request) {
	lat, lng := parseLocation(request.URL.Query().Get("location"))
	writeJSON(writer, http.StatusOK, map[string]any{
		"status": 0,
		"result": map[string]any{"pois": []map[string]any{{
			"uid":  stableID("nearby", request.URL.RawQuery),
			"name": "Nonprod Nearby POI", "addr": "Nonprod",
			"distance": "0", "point": map[string]string{
				"x": strconv.FormatFloat(lng, 'f', 6, 64),
				"y": strconv.FormatFloat(lat, 'f', 6, 64),
			},
		}}},
	})
}

func (s *Server) locationSearch(writer http.ResponseWriter, request *http.Request) {
	lat, lng := parseLocation(request.URL.Query().Get("location"))
	query := strings.TrimSpace(request.URL.Query().Get("query"))
	writeJSON(writer, http.StatusOK, map[string]any{
		"status": 0,
		"results": []map[string]any{{
			"uid":  stableID("search", query+"|"+request.URL.Query().Get("location")),
			"name": "Nonprod Search POI: " + query, "address": "Nonprod",
			"city_code": 0, "location": map[string]float64{"lat": lat, "lng": lng},
		}},
	})
}

// nominatimSearch mirrors the exact upstream wire the integration-service
// NominatimClient consumes: a JSON array of POI rows with string lat/lon and
// stable osm identity, so anti-corruption decoding is exercised for real.
func (s *Server) nominatimSearch(writer http.ResponseWriter, request *http.Request) {
	query := strings.TrimSpace(request.URL.Query().Get("q"))
	if query == "" {
		http.Error(writer, "q is required", http.StatusBadRequest)
		return
	}
	limit, err := strconv.Atoi(strings.TrimSpace(request.URL.Query().Get("limit")))
	if err != nil || limit <= 0 {
		http.Error(writer, "limit is required", http.StatusBadRequest)
		return
	}
	if limit > 3 {
		limit = 3
	}
	rows := make([]map[string]any, 0, limit)
	for index := 0; index < limit; index++ {
		suffix := strconv.Itoa(index + 1)
		rows = append(rows, map[string]any{
			"place_id":     1000 + index,
			"osm_type":     "node",
			"osm_id":       json.Number(stableNumericID(query, index)),
			"lat":          "30.27" + suffix,
			"lon":          "120.15" + suffix,
			"name":         "Nonprod POI " + query + " " + suffix,
			"display_name": "Nonprod POI " + query + " " + suffix + ", Nonprod City",
		})
	}
	writeJSON(writer, http.StatusOK, rows)
}

// osrmRoute mirrors the exact upstream OSRM wire the integration-service
// OSRMClient consumes: /route/v1/{profile}/{lng,lat;lng,lat} with a polyline
// geometry plus non-negative distance/duration.
func (s *Server) osrmRoute(writer http.ResponseWriter, request *http.Request) {
	remainder := strings.TrimPrefix(request.URL.Path, "/osrm/route/v1/")
	parts := strings.SplitN(remainder, "/", 2)
	profile := strings.TrimSpace(parts[0])
	switch profile {
	case "driving", "cycling", "walking":
	default:
		http.Error(writer, "unsupported profile", http.StatusBadRequest)
		return
	}
	if len(parts) != 2 || !strings.Contains(parts[1], ";") {
		http.Error(writer, "coordinates are required", http.StatusBadRequest)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"code": "Ok",
		"routes": []map[string]any{{
			// 固定合法 polyline（杭州附近两点）；客户端只透传不解码。
			"geometry": "_ibiD_seyToclCoclC",
			"distance": 1250.5,
			"duration": 300.0,
		}},
	})
}

func stableNumericID(value string, index int) string {
	digest := sha256.Sum256([]byte(value + "|" + strconv.Itoa(index)))
	return strconv.FormatUint(uint64(digest[0])<<16|uint64(digest[1])<<8|uint64(digest[2]), 10)
}

func (s *Server) carrierResolve(writer http.ResponseWriter, request *http.Request) {
	var payload struct {
		Token string `json:"token"`
	}
	if err := decodeJSON(writer, request, 64<<10, &payload); err != nil {
		return
	}
	if strings.TrimSpace(payload.Token) == "" {
		http.Error(writer, "token is required", http.StatusBadRequest)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]string{
		"phone": "+8613800000000", "displayLabel": "138****0000",
	})
}

type federatedProtocolRequest struct {
	Action   string `json:"action"`
	Provider string `json:"provider"`
	Code     string `json:"code"`
}

func (s *Server) federatedDispatch(writer http.ResponseWriter, request *http.Request) {
	var payload federatedProtocolRequest
	if err := decodeJSON(writer, request, 64<<10, &payload); err != nil {
		return
	}
	payload.Action = strings.TrimSpace(payload.Action)
	if payload.Action == "" {
		payload.Action = "resolveIdentity"
	}
	switch payload.Action {
	case "authorize":
		s.invokeProvider(
			writer,
			request,
			"identity.social.login",
			"authorize",
			func(writer http.ResponseWriter, _ *http.Request) {
				s.federatedAuthorize(writer, payload)
			},
		)
	case "resolveIdentity":
		s.invokeProvider(
			writer,
			request,
			"identity.social.login",
			"resolveIdentity",
			func(writer http.ResponseWriter, _ *http.Request) {
				s.federatedVerify(writer, payload)
			},
		)
	default:
		http.Error(writer, "invalid federated action", http.StatusBadRequest)
	}
}

func (s *Server) federatedAuthorize(
	writer http.ResponseWriter,
	payload federatedProtocolRequest,
) {
	provider := strings.TrimSpace(payload.Provider)
	if provider == "" || strings.TrimSpace(payload.Code) != "" {
		http.Error(writer, "provider is required", http.StatusBadRequest)
		return
	}
	nonce := make([]byte, 24)
	if _, err := rand.Read(nonce); err != nil {
		http.Error(writer, "authorization unavailable", http.StatusServiceUnavailable)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"payload":   base64.RawURLEncoding.EncodeToString(nonce),
		"expiresAt": s.now().UTC().Add(5 * time.Minute),
	})
}

func (s *Server) federatedVerify(
	writer http.ResponseWriter,
	payload federatedProtocolRequest,
) {
	if strings.TrimSpace(payload.Provider) == "" || strings.TrimSpace(payload.Code) == "" {
		http.Error(writer, "provider and code are required", http.StatusBadRequest)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]string{
		"credentialKey": stableID(payload.Provider, payload.Code),
		"displayName":   "Nonprod User",
		"avatarUrl":     "",
	})
}

func (s *Server) pushSend(writer http.ResponseWriter, request *http.Request) {
	var payload map[string]any
	if err := decodeJSON(writer, request, 1<<20, &payload); err != nil {
		return
	}
	requestID := strings.TrimSpace(fmt.Sprint(payload["requestId"]))
	if requestID == "" {
		http.Error(writer, "requestId is required", http.StatusBadRequest)
		return
	}
	writeJSON(writer, http.StatusAccepted, map[string]string{
		"providerRequestId": "nonprod-" + stableID("push", requestID),
	})
}

func stableID(kind, value string) string {
	digest := sha256.Sum256([]byte(kind + "|" + value))
	return "np-" + hex.EncodeToString(digest[:8])
}

func parseLocation(value string) (float64, float64) {
	parts := strings.Split(value, ",")
	if len(parts) != 2 {
		return 30.2741, 120.1551
	}
	latitude, _ := strconv.ParseFloat(strings.TrimSpace(parts[0]), 64)
	longitude, _ := strconv.ParseFloat(strings.TrimSpace(parts[1]), 64)
	return latitude, longitude
}

func decodeJSON(
	writer http.ResponseWriter,
	request *http.Request,
	limit int64,
	target any,
) error {
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, limit))
	if err := decoder.Decode(target); err != nil {
		http.Error(writer, "invalid request", http.StatusBadRequest)
		return err
	}
	return nil
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}
