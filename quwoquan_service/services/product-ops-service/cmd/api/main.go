package main

import (
	"context"
	"encoding/json"
	"errors"
	"hash/fnv"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	rtmongo "quwoquan_service/runtime/mongodb"

	"log/slog"

	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/repository"
	"quwoquan_service/services/product-ops-service/internal/application"
	"quwoquan_service/services/product-ops-service/internal/infrastructure/messaging"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

type bucketDef struct {
	Name      string `json:"name"`
	WeightPct int    `json:"weightPct"`
}

type assignment struct {
	ExperimentID    string `json:"experimentId"`
	SubjectKey      string `json:"subjectKey"`
	Bucket          string `json:"bucket"`
	PolicyVersion   string `json:"policyVersion"`
	AssignmentTrace string `json:"assignmentTrace"`
}

type experimentDef struct {
	ID            string                `json:"id"`
	Name          string                `json:"name"`
	Enabled       bool                  `json:"enabled"`
	PolicyVersion string                `json:"policyVersion"`
	Buckets       []bucketDef           `json:"buckets"`
	BucketStats   map[string]int        `json:"bucketStats"`
	Assignments   map[string]assignment `json:"assignments"`
}

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
	store     *controlplane.FileStore
	telemetry *application.TelemetryService
	publisher repository.EventPublisher
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
	addr := getenvOrDefault("PRODUCT_OPS_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if strings.TrimSpace(addr) == "" {
		addr = ":18086"
	}
	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "product-ops-service", SamplingRatio: 0.1})
	defer otelShutdown()

	ctx := context.Background()
	repoRoot := resolveRepoRoot()
	store := controlplane.NewFileStore(localControlPlaneStorePath(repoRoot, "product-ops-service"))
	router := buildRedisRouter(cfg)
	defer router.Close()
	if err := router.PingAll(ctx); err != nil {
		log.Printf("WARN: product-ops-service redis PingAll: %v", err)
	}
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("redis", func(ctx context.Context) error {
		return router.PingAll(ctx)
	})
	publisher := messaging.NewRedisEventPublisher(router.Scene("general"), serviceName, nil)
	telemetryStore := application.TelemetryStore(telemetrypersistence.NewMemoryTelemetryStore())
	if strings.TrimSpace(cfg.MongoDB.URI) != "" {
		mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: cfg.MongoDB.URI}, "product-ops-service")
		defer func() {
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = mongoClient.Disconnect(shutdownCtx)
		}()
		dbName := cfg.MongoDB.Database
		if strings.TrimSpace(dbName) == "" {
			dbName = "quwoquan_product_ops"
		}
		mongoStore := telemetrypersistence.NewMongoTelemetryStore(mongoClient.Database(dbName))
		if err := mongoStore.EnsureIndexes(context.Background()); err != nil {
			log.Printf("WARN: product-ops-service ensure mongo indexes: %v", err)
		}
		healthChecker.Register("mongodb", func(ctx context.Context) error {
			return mongoClient.Ping(ctx, nil)
		})
		telemetryStore = mongoStore
		log.Printf("product-ops-service telemetry storage=mongodb db=%s", dbName)
	} else {
		log.Printf("product-ops-service telemetry storage=inmemory (no mongodb.uri configured)")
	}
	var eventMirror application.EventMirror
	if esURL := strings.TrimSpace(os.Getenv("PRODUCT_OPS_ES_URL")); esURL != "" {
		esCB := rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default())
		esClient := rtgov.WrapClientWithCB(&http.Client{Timeout: 5 * time.Second}, esCB)
		eventMirror = telemetrypersistence.NewElasticsearchEventMirror(esURL, telemetrypersistence.WithESHTTPClient(esClient))
		log.Printf("product-ops-service exception ES mirror enabled url=%s", esURL)
	}
	service := newProductService(store, application.NewTelemetryServiceWithMirror(telemetryStore, publisher, eventMirror), publisher)
	if err := service.seed(); err != nil {
		log.Fatalf("seed product ops service: %v", err)
	}
	mux := newServerMux(service, healthChecker)

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
	observedHandler := rthttp.NewHTTPServerMiddleware(mux, rthttp.HTTPServerMiddlewareConfig{
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
		Addr:              addr,
		Handler:           rateLimited,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("product-ops-service listening on %s (rate_limit=1000/s)", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("product-ops-service: %v", err)
	}
}

func newProductService(store *controlplane.FileStore, telemetry *application.TelemetryService, publishers ...repository.EventPublisher) *productService {
	var publisher repository.EventPublisher
	if len(publishers) > 0 {
		publisher = publishers[0]
	}
	return &productService{store: store, telemetry: telemetry, publisher: publisher}
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

func (s *productService) resolveExperimentAssignment(experimentID, subjectKey string) (assignment, error) {
	experiment, ok, err := s.getExperiment(experimentID)
	if err != nil {
		return assignment{}, err
	}
	if !ok || !experiment.Enabled {
		return assignment{
			ExperimentID:    experimentID,
			SubjectKey:      subjectKey,
			Bucket:          "control",
			PolicyVersion:   "not-found",
			AssignmentTrace: "experiment not found or disabled",
		}, nil
	}
	if existing, ok := experiment.Assignments[subjectKey]; ok {
		return existing, nil
	}
	bucket := assignBucket(experimentID, subjectKey, experiment.Buckets)
	out := assignment{
		ExperimentID:    experimentID,
		SubjectKey:      subjectKey,
		Bucket:          bucket,
		PolicyVersion:   experiment.PolicyVersion,
		AssignmentTrace: "hash",
	}
	if experiment.Assignments == nil {
		experiment.Assignments = map[string]assignment{}
	}
	if experiment.BucketStats == nil {
		experiment.BucketStats = map[string]int{}
	}
	experiment.Assignments[subjectKey] = out
	experiment.BucketStats[bucket]++
	if err := s.putDocument("experiments", experiment.ID, experiment); err != nil {
		return assignment{}, err
	}
	return out, nil
}

func (s *productService) getExperiment(id string) (experimentDef, bool, error) {
	item, ok, err := s.store.GetDocument("experiments", id)
	if err != nil || !ok {
		return experimentDef{}, ok, err
	}
	out, err := decodeDocument[experimentDef](item)
	return out, true, err
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

func assignBucket(experimentID, subjectKey string, buckets []bucketDef) string {
	if len(buckets) == 0 {
		return "control"
	}
	hasher := fnv.New32a()
	_, _ = hasher.Write([]byte(experimentID + ":" + subjectKey))
	position := int(hasher.Sum32() % 100)
	cumulative := 0
	for _, bucket := range buckets {
		cumulative += bucket.WeightPct
		if position < cumulative {
			return bucket.Name
		}
	}
	return buckets[len(buckets)-1].Name
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

func resolveRepoRoot() string {
	if root := strings.TrimSpace(os.Getenv("REPO_ROOT")); root != "" {
		return root
	}
	wd, err := os.Getwd()
	if err != nil {
		return "."
	}
	current := wd
	for {
		if _, err := os.Stat(filepath.Join(current, "quwoquan_service", "contracts", "metadata")); err == nil {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			return wd
		}
		current = parent
	}
}

func localControlPlaneStorePath(repoRoot, serviceName string) string {
	return filepath.Join(repoRoot, ".qwq_output", "env", "repo", "local", "control-plane", serviceName, serviceName+".json")
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
	if status == http.StatusBadRequest || status == http.StatusMethodNotAllowed || status == http.StatusNotFound {
		reason = "invalid_argument"
		kind = rterr.KindUser
	}
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleOps, kind, reason),
			userMessage,
			debugMessage,
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}

func check(err error) bool {
	return err == nil
}

var _ = errors.New
var _ = must
var _ = check
