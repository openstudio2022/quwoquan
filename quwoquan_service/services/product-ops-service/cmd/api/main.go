package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	rtmongo "quwoquan_service/internal/platform/mongodb"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	experimenthttp "quwoquan_service/services/product-ops-service/internal/adapters/http/experiment"
	"quwoquan_service/services/product-ops-service/internal/application"
	experimentapp "quwoquan_service/services/product-ops-service/internal/application/product_ops/experiment"
	"quwoquan_service/services/product-ops-service/internal/infrastructure/messaging"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
	experimentpersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/product_ops/experiment/persistence"
)

type moderationCase struct {
	ID            string   `json:"id"`
	TargetType    string   `json:"targetType"`
	TargetID      string   `json:"targetId"`
	Reason        string   `json:"reason"`
	Status        string   `json:"status"`
	AssignedQueue string   `json:"assignedQueue"`
	EvidenceRefs  []string `json:"evidenceRefs"`
	Resolution    string   `json:"resolution,omitempty"`
	UpdatedAt     string   `json:"updatedAt"`
}

type recoveryCase struct {
	ID           string   `json:"id"`
	UserID       string   `json:"userId"`
	Status       string   `json:"status"`
	EvidenceRefs []string `json:"evidenceRefs"`
	Decision     string   `json:"decision,omitempty"`
	UpdatedAt    string   `json:"updatedAt"`
}

type appealCase struct {
	ID           string   `json:"id"`
	TargetType   string   `json:"targetType"`
	TargetID     string   `json:"targetId"`
	Status       string   `json:"status"`
	EvidenceRefs []string `json:"evidenceRefs"`
	Decision     string   `json:"decision,omitempty"`
	UpdatedAt    string   `json:"updatedAt"`
}

type recommendationPolicy struct {
	ID                string         `json:"id"`
	Name              string         `json:"name"`
	Status            string         `json:"status"`
	PolicyVersion     string         `json:"policyVersion"`
	GuardrailSnapshot map[string]any `json:"guardrailSnapshot"`
	UpdatedAt         string         `json:"updatedAt"`
}

type metricSnapshot struct {
	ID          string  `json:"id"`
	Level       string  `json:"level"`
	Environment string  `json:"environment"`
	Cluster     string  `json:"cluster,omitempty"`
	Service     string  `json:"service,omitempty"`
	InstanceID  string  `json:"instanceId,omitempty"`
	Label       string  `json:"label"`
	Metric      string  `json:"metric"`
	Value       float64 `json:"value"`
	Unit        string  `json:"unit"`
	Status      string  `json:"status"`
	Trend       string  `json:"trend"`
	Source      string  `json:"source,omitempty"`
	Description string  `json:"description"`
}

type visitRecord struct {
	TargetType string `json:"targetType"`
	TargetKey  string `json:"targetKey"`
	UserID     string `json:"userId"`
	VisitCount int    `json:"visitCount"`
	LastSeenAt string `json:"lastSeenAt,omitempty"`
	SessionID  string `json:"sessionId,omitempty"`
	Source     string `json:"source,omitempty"`
}

type productService struct {
	store          controlplane.StateStore
	telemetry      *application.TelemetryService
	experimentHTTP *experimenthttp.Handler
	publisher      runtimemessaging.EventPublisher
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("product-ops-service runtime identity invalid: %v", err)
	}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("product-ops-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("product-ops-service config compatibility failed: %v", err)
	}
	if err := validateRequiredRuntimeConfig(cfg); err != nil {
		log.Fatalf("product-ops-service required runtime config invalid: %v", err)
	}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("product-ops-service access token config invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("product-ops-service access token verifier invalid: %v", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatalf("product-ops-service device ticket config invalid: %v", err)
	}
	deviceTicketVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		log.Fatalf("product-ops-service device ticket verifier invalid: %v", err)
	}
	addr := getenvOrDefault("PRODUCT_OPS_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if strings.TrimSpace(addr) == "" {
		addr = ":18086"
	}
	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "product-ops-service", SamplingRatio: 0.1})
	defer otelShutdown()

	ctx, cancelRuntime := context.WithCancel(context.Background())
	defer cancelRuntime()
	postgresConfig, err := pgxpool.ParseConfig(cfg.Postgres.DSN)
	if err != nil {
		log.Fatalf("product-ops-service postgres config invalid: %v", err)
	}
	postgresConfig.MaxConns = 20
	postgresConfig.MinConns = 2
	postgresConfig.HealthCheckPeriod = 30 * time.Second
	postgresPool, err := pgxpool.NewWithConfig(ctx, postgresConfig)
	if err != nil {
		log.Fatalf("product-ops-service postgres connect failed: %v", err)
	}
	defer postgresPool.Close()
	if err := postgresPool.Ping(ctx); err != nil {
		log.Fatalf("product-ops-service postgres unavailable: %v", err)
	}
	store, err := controlplanepersistence.NewPostgresStore(postgresPool, "product-ops")
	if err != nil {
		log.Fatalf("product-ops-service control plane store invalid: %v", err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		log.Fatalf("product-ops-service control plane schema initialization failed: %v", err)
	}
	experimentStore, err := experimentpersistence.NewPostgresStore(postgresPool)
	if err != nil {
		log.Fatalf("product-ops-service experiment store invalid: %v", err)
	}
	if err := experimentStore.EnsureSchema(ctx); err != nil {
		log.Fatalf("product-ops-service experiment schema initialization failed: %v", err)
	}
	experimentFacade, err := experimentapp.NewFacade(
		experimentStore,
		experimentStore,
		experimentStore,
		experimentStore,
	)
	if err != nil {
		log.Fatalf("product-ops-service experiment facade invalid: %v", err)
	}
	router, err := buildRedisRouter(cfg)
	if err != nil {
		log.Fatalf("product-ops-service redis config invalid: %v", err)
	}
	defer router.Close()
	if err := router.PingAll(ctx); err != nil {
		log.Fatalf("product-ops-service redis unavailable: %v", err)
	}
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("redis", func(ctx context.Context) error {
		return router.PingAll(ctx)
	})
	publisher := messaging.NewRedisEventPublisher(router.Scene("general"), serviceName, nil)
	outboxDispatcher, err := experimentpersistence.NewOutboxDispatcher(postgresPool, publisher)
	if err != nil {
		log.Fatalf("product-ops-service outbox dispatcher invalid: %v", err)
	}
	go outboxDispatcher.Run(ctx)
	mongoClient, err := rtmongo.Connect(ctx, rtmongo.ConnectConfig{URI: cfg.MongoDB.URI})
	if err != nil {
		log.Fatalf("product-ops-service mongodb unavailable: %v", err)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = mongoClient.Disconnect(shutdownCtx)
	}()
	dbName := strings.TrimSpace(cfg.MongoDB.Database)
	visitStore := telemetrypersistence.NewMongoVisitStore(mongoClient.Database(dbName))
	if err := visitStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("product-ops-service visit index initialization failed: %v", err)
	}
	healthChecker.Register("mongodb", func(ctx context.Context) error {
		return mongoClient.Ping(ctx, nil)
	})
	healthChecker.Register("postgres", func(ctx context.Context) error {
		return postgresPool.Ping(ctx)
	})
	slsConfig := telemetrypersistence.SLSConfig{
		Region:                    strings.TrimSpace(cfg.SLS.Region),
		Endpoint:                  strings.TrimSpace(cfg.SLS.Endpoint),
		Project:                   strings.TrimSpace(cfg.SLS.Project),
		RawLogstore:               strings.TrimSpace(cfg.SLS.RawLogstore),
		StartupDiagnosticLogstore: strings.TrimSpace(cfg.SLS.StartupDiagnosticLogstore),
		AggregateLogstore:         strings.TrimSpace(cfg.SLS.AggregateLogstore),
		Timeout:                   time.Duration(cfg.SLS.TimeoutMS) * time.Millisecond,
	}
	accessKeyID := strings.TrimSpace(os.Getenv("ALIBABA_CLOUD_ACCESS_KEY_ID"))
	accessKeySecret := strings.TrimSpace(os.Getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET"))
	securityToken := strings.TrimSpace(os.Getenv("ALIBABA_CLOUD_SECURITY_TOKEN"))
	if accessKeyID == "" || accessKeySecret == "" {
		log.Fatal("product-ops-service SLS credentials are required through deployment Secret")
	}
	slsClient := telemetrypersistence.NewOfficialSLSClient(
		slsConfig,
		accessKeyID,
		accessKeySecret,
		securityToken,
	)
	defer slsClient.Close()
	eventStore, err := telemetrypersistence.NewSLSEventLogStore(slsClient, slsConfig)
	if err != nil {
		log.Fatalf("product-ops-service SLS telemetry store invalid: %v", err)
	}
	healthChecker.Register("sls", func(context.Context) error {
		for _, logstore := range []string{
			slsConfig.RawLogstore,
			slsConfig.StartupDiagnosticLogstore,
			slsConfig.AggregateLogstore,
		} {
			if _, err := slsClient.GetLogStore(slsConfig.Project, logstore); err != nil {
				return err
			}
		}
		return nil
	})
	batchLedger := telemetrypersistence.NewRedisEventBatchLedger(router.Scene("general"))
	log.Printf(
		"product-ops-service telemetry storage=sls project=%s raw=%s aggregate=%s visit_storage=mongodb db=%s",
		slsConfig.Project,
		slsConfig.RawLogstore,
		slsConfig.AggregateLogstore,
		dbName,
	)
	service := newProductService(
		store,
		application.NewTelemetryServiceWithStores(visitStore, instrumentEventLogStore(eventStore), batchLedger),
		experimentFacade,
		publisher,
	)
	mux := newServerMux(service, healthChecker)
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", mux)
	// 启动遥测是唯一允许匿名接收的 Ops 路径；handler 以固定 schema、proof 与
	// 每来源 IP 配额收紧，绝不绕过通用 /ops/events 的已验证主体要求。
	outerMux.HandleFunc("/ops/startup-events", func(w http.ResponseWriter, r *http.Request) {
		mux.ServeHTTP(w, r)
	})
	outerMux.Handle(
		"/",
		rtauth.RequireGeneratedOperationAuthorization(
			operationsecurity.ForDomain("ops"),
		)(mux),
	)

	instanceID, _ := os.Hostname()
	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, pErr := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, "info", nil)
	if pErr != nil {
		log.Fatalf("product-ops-service process logger init failed: %v", pErr)
	}
	exceptionLogger, eErr := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if eErr != nil {
		log.Fatalf("product-ops-service exception logger init failed: %v", eErr)
	}
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "product-ops-service",
		ServiceName:       "product-ops-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())
	hotConfigStore := controlplane.NewHotConfigStore()
	go startConfigSyncLoop(serviceName, appEnv, configRoot, configVersion, imageVersion, instanceID, hotConfigStore)

	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(corsHandler)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:  accessVerifier,
			DeviceTicketVerifier: deviceTicketVerifier,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("product-ops-service listening on %s (rate_limit=1000/s)", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("product-ops-service: %v", err)
	}
}

func newProductService(
	store controlplane.StateStore,
	telemetry *application.TelemetryService,
	experiments *experimentapp.Facade,
	publishers ...runtimemessaging.EventPublisher,
) *productService {
	var publisher runtimemessaging.EventPublisher
	if len(publishers) > 0 {
		publisher = publishers[0]
	}
	if store == nil || telemetry == nil || experiments == nil {
		panic("product service requires control-plane store, telemetry and experiment facade")
	}
	experimentHandler, err := experimenthttp.NewHandler(experiments)
	if err != nil {
		panic(err)
	}
	return &productService{
		store: store, telemetry: telemetry,
		experimentHTTP: experimentHandler, publisher: publisher,
	}
}

func (s *productService) buildL1L4Cards() ([]map[string]any, error) {
	items, err := s.store.ListDocuments("l1l4_metric_snapshots")
	if err != nil {
		return nil, err
	}
	priority := map[string]int{"L1": 1, "L2": 2, "L3": 3, "L4": 4}
	seen := map[string]bool{}
	type card struct {
		level    string
		label    string
		metric   string
		priority int
	}
	cards := make([]card, 0, 4)
	for _, item := range items {
		level, _ := item["level"].(string)
		level = strings.TrimSpace(level)
		if level == "" || seen[level] {
			continue
		}
		rank, ok := priority[level]
		if !ok {
			continue
		}
		seen[level] = true
		cards = append(cards, card{
			level:    level,
			label:    strings.TrimSpace(safeString(item["label"])),
			metric:   strings.TrimSpace(safeString(item["metric"])),
			priority: rank,
		})
	}
	sort.Slice(cards, func(i, j int) bool {
		return cards[i].priority < cards[j].priority
	})
	out := make([]map[string]any, 0, len(cards))
	for _, item := range cards {
		out = append(out, map[string]any{
			"level":  item.level,
			"label":  item.label,
			"metric": item.metric,
		})
	}
	if len(out) == 0 {
		out = []map[string]any{
			{"level": "L1", "label": "产品旅程", "metric": "five_tab_journey_completion_rate"},
			{"level": "L2", "label": "业务质量", "metric": "circle_scenario_ctr"},
			{"level": "L3", "label": "系统 RED", "metric": "api_red_duration_p95_ms"},
			{"level": "L4", "label": "基础设施", "metric": "gateway_up"},
		}
	}
	return out, nil
}

func safeString(value any) string {
	if text, ok := value.(string); ok {
		return text
	}
	return ""
}

func (s *productService) getRecommendationPolicy(id string) (recommendationPolicy, bool, error) {
	item, ok, err := s.store.GetDocument("recommendation_policies", id)
	if err != nil || !ok {
		return recommendationPolicy{}, ok, err
	}
	out, err := decodeDocument[recommendationPolicy](item)
	return out, true, err
}

func (s *productService) getVisitRecord(id string) (visitRecord, bool, error) {
	item, ok, err := s.store.GetDocument("visit_records", id)
	if err != nil || !ok {
		return visitRecord{}, ok, err
	}
	out, err := decodeDocument[visitRecord](item)
	return out, true, err
}

func (s *productService) putIfMissing(namespace, id string, value any) error {
	_, ok, err := s.store.GetDocument(namespace, id)
	if err != nil || ok {
		return err
	}
	return s.putDocument(namespace, id, value)
}

func (s *productService) putWorkflowIfMissing(objectType, objectID, workflowID, state string) error {
	_, ok, err := s.store.GetWorkflow(objectType, objectID)
	if err != nil || ok {
		return err
	}
	return s.store.UpsertWorkflow(controlplane.WorkflowState{
		ObjectType: objectType,
		ObjectID:   objectID,
		WorkflowID: workflowID,
		State:      state,
		History:    []controlplane.WorkflowTransition{},
		UpdatedAt:  nowRFC3339(),
	})
}

func (s *productService) putDocument(namespace, id string, value any) error {
	return s.store.PutDocument(namespace, id, documentFromStruct(value))
}

func decodeDocument[T any](doc controlplane.Document) (T, error) {
	var out T
	data, err := json.Marshal(doc)
	if err != nil {
		return out, err
	}
	if err := json.Unmarshal(data, &out); err != nil {
		return out, err
	}
	return out, nil
}

func documentFromStruct(value any) controlplane.Document {
	data, _ := json.Marshal(value)
	var out controlplane.Document
	_ = json.Unmarshal(data, &out)
	return out
}

func approvalExists(items []controlplane.ApprovalDecision, actor string) bool {
	for _, item := range items {
		if item.Actor == actor {
			return true
		}
	}
	return false
}

func distinctApprovalActors(items []controlplane.ApprovalDecision) []string {
	seen := map[string]bool{}
	out := make([]string, 0)
	for _, item := range items {
		if item.Actor == "" || seen[item.Actor] {
			continue
		}
		seen[item.Actor] = true
		out = append(out, item.Actor)
	}
	sort.Strings(out)
	return out
}

func actorFromRequest(r *http.Request) string {
	if actor := strings.TrimSpace(r.Header.Get("X-Actor")); actor != "" {
		return actor
	}
	return "portal.ops"
}

func environmentFromRequest(r *http.Request) string {
	if env := strings.TrimSpace(r.Header.Get("X-Environment")); env != "" {
		return env
	}
	return "beta"
}

func requestIDFromRequest(r *http.Request) string {
	if requestID := strings.TrimSpace(r.Header.Get("X-Request-Id")); requestID != "" {
		return requestID
	}
	return "req-" + strings.ReplaceAll(nowRFC3339(), ":", "")
}

func traceIDFromRequest(r *http.Request) string {
	if traceID := strings.TrimSpace(r.Header.Get("X-Trace-Id")); traceID != "" {
		return traceID
	}
	return "trace-" + strings.ReplaceAll(nowRFC3339(), ":", "")
}

func segmentBetween(path, prefix, suffix string) string {
	value := strings.TrimPrefix(path, prefix)
	value = strings.TrimSuffix(value, suffix)
	return strings.Trim(value, "/")
}

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}

func cloneMap(in map[string]any) map[string]any {
	data, _ := json.Marshal(in)
	var out map[string]any
	_ = json.Unmarshal(data, &out)
	return out
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeRuntimeNotFound(w http.ResponseWriter, r *http.Request) {
	writeRuntimeError(w, r, http.StatusNotFound, "接口不存在", "route not found")
}

func writeRuntimeError(
	w http.ResponseWriter,
	r *http.Request,
	status int,
	userMessage string,
	debugMessage string,
) {
	reason := "internal_error"
	kind := rterr.KindSystem
	if status == http.StatusUnauthorized {
		reason = "unauthorized"
		kind = rterr.KindUser
	} else if status == http.StatusBadRequest || status == http.StatusMethodNotAllowed || status == http.StatusNotFound {
		reason = "invalid_argument"
		kind = rterr.KindUser
	}
	appError := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleOps, kind, reason),
		userMessage,
		debugMessage,
	)
	if status == http.StatusUnauthorized {
		appError.WithMetadata("unauthorized", http.StatusUnauthorized)
	}
	rterr.WriteHTTPError(
		w,
		appError,
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
