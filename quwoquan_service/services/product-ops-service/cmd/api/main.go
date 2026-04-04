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

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/controlplane"
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
	repoRoot := resolveRepoRoot()
	store := controlplane.NewFileStore(filepath.Join(repoRoot, ".control-plane-state", "product-ops-service.json"))
	router := buildRedisRouter(cfg)
	defer router.Close()
	publisher := messaging.NewRedisEventPublisher(router.Scene("general"), serviceName, nil)
	telemetryStore := application.TelemetryStore(telemetrypersistence.NewMemoryTelemetryStore())
	if strings.TrimSpace(cfg.MongoDB.URI) != "" {
		mongoClient, err := mongo.Connect(options.Client().ApplyURI(cfg.MongoDB.URI))
		if err != nil {
			log.Fatalf("product-ops-service mongo connect failed: %v", err)
		}
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
		telemetryStore = mongoStore
		log.Printf("product-ops-service telemetry storage=mongodb db=%s", dbName)
	} else {
		log.Printf("product-ops-service telemetry storage=inmemory (no mongodb.uri configured)")
	}
	service := newProductService(store, application.NewTelemetryService(telemetryStore, publisher))
	if err := service.seed(); err != nil {
		log.Fatalf("seed product ops service: %v", err)
	}
	mux := newServerMux(service)
	log.Printf("product-ops-service listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}

func newProductService(store *controlplane.FileStore, telemetry *application.TelemetryService) *productService {
	return &productService{store: store, telemetry: telemetry}
}

func newServerMux(service *productService) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
	})
	mux.HandleFunc("/v1/ops/experiments/", func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, "/v1/ops/experiments/")
		switch {
		case strings.HasSuffix(path, "/bucket") && r.Method == http.MethodGet:
			service.handleGetBucket(w, r)
		case strings.HasSuffix(path, "/assign") && r.Method == http.MethodPost:
			service.handleAssignBucket(w, r)
		case strings.HasSuffix(path, "/stats") && r.Method == http.MethodGet:
			service.handleGetStats(w, r)
		default:
			http.NotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/ops/visits", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.NotFound(w, r)
			return
		}
		service.handleRecordVisit(w, r)
	})
	mux.HandleFunc("/v1/ops/visits/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleGetVisitStats(w, r)
	})
	mux.HandleFunc("/v1/ops/events", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.NotFound(w, r)
			return
		}
		service.handleReportEventBatch(w, r)
	})
	mux.HandleFunc("/v1/ops/events/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleGetEventSummary(w, r)
	})
	mux.HandleFunc("/v1/ops/events/drilldown", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleGetEventDrilldown(w, r)
	})
	mux.HandleFunc("/v1/control-plane/product/experiments", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "only GET"})
			return
		}
		service.handleListExperiments(w)
	})
	mux.HandleFunc("/v1/control-plane/product/experiments/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":rollout"):
			service.handleRollout(w, r)
		default:
			http.NotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/moderation/cases", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleListModerationCases(w)
	})
	mux.HandleFunc("/v1/control-plane/product/moderation/cases/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet:
			service.handleGetModerationCase(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":startReview"):
			service.handleStartModerationReview(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":applyAction"):
			service.handleApplyEnforcementAction(w, r)
		default:
			http.NotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/recovery/cases", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleListRecoveryCases(w)
	})
	mux.HandleFunc("/v1/control-plane/product/recovery/cases/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet:
			service.handleGetRecoveryCase(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":submitDecision"):
			service.handleSubmitRecoveryDecision(w, r)
		default:
			http.NotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/appeal/cases", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleListAppealCases(w)
	})
	mux.HandleFunc("/v1/control-plane/product/appeal/cases/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet:
			service.handleGetAppealCase(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":submitDecision"):
			service.handleSubmitAppealDecision(w, r)
		default:
			http.NotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/recommendation/policies", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleListRecommendationPolicies(w)
	})
	mux.HandleFunc("/v1/control-plane/product/recommendation/policies/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":simulate"):
			service.handleSimulateRecommendationPolicy(w, r)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":activate"):
			service.handleActivateRecommendationPolicy(w, r)
		default:
			http.NotFound(w, r)
		}
	})
	mux.HandleFunc("/v1/control-plane/product/workflows", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleListWorkflows(w)
	})
	mux.HandleFunc("/v1/control-plane/product/audits", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleListAudits(w)
	})
	mux.HandleFunc("/v1/control-plane/product/approvals", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleListApprovals(w)
	})
	mux.HandleFunc("/v1/control-plane/product/projections/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		service.handleProjectionSummary(w)
	})
	return mux
}

func (s *productService) seed() error {
	defaultExperiments := []experimentDef{
		{
			ID:            "discovery_feed_v3",
			Name:          "发现流排序权重调优",
			Enabled:       true,
			PolicyVersion: "ops-2026.03.08",
			Buckets: []bucketDef{
				{Name: "control", WeightPct: 50},
				{Name: "variant_a", WeightPct: 25},
				{Name: "variant_b", WeightPct: 25},
			},
			BucketStats: map[string]int{},
			Assignments: map[string]assignment{},
		},
		{
			ID:            "new_user_recall_mix",
			Name:          "新用户召回混排实验",
			Enabled:       true,
			PolicyVersion: "ops-2026.03.08",
			Buckets: []bucketDef{
				{Name: "control", WeightPct: 70},
				{Name: "boosted_recall", WeightPct: 30},
			},
			BucketStats: map[string]int{},
			Assignments: map[string]assignment{},
		},
	}
	for _, item := range defaultExperiments {
		if err := s.putIfMissing("experiments", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("experiment", item.ID, "experiment_rollout_v1", "running"); err != nil {
			return err
		}
	}

	defaultModerationCases := []moderationCase{
		{
			ID:            "case_post_901",
			TargetType:    "post",
			TargetID:      "post_901",
			Reason:        "spam",
			Status:        "reported",
			AssignedQueue: "content-moderation",
			EvidenceRefs:  []string{"evidence_img_1"},
			UpdatedAt:     nowRFC3339(),
		},
	}
	for _, item := range defaultModerationCases {
		if err := s.putIfMissing("moderation_cases", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("moderation_case", item.ID, "moderation_case_v1", item.Status); err != nil {
			return err
		}
	}

	defaultRecoveryCases := []recoveryCase{
		{
			ID:           "recovery_user_1827",
			UserID:       "user_1827",
			Status:       "evidence_verified",
			EvidenceRefs: []string{"device_proof", "payment_receipt"},
			UpdatedAt:    nowRFC3339(),
		},
	}
	for _, item := range defaultRecoveryCases {
		if err := s.putIfMissing("recovery_cases", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("recovery_case", item.ID, "recovery_case_v1", item.Status); err != nil {
			return err
		}
	}

	defaultAppealCases := []appealCase{
		{
			ID:           "appeal_case_301",
			TargetType:   "account",
			TargetID:     "user_1827",
			Status:       "under_review",
			EvidenceRefs: []string{"appeal_form", "chat_snapshot"},
			UpdatedAt:    nowRFC3339(),
		},
	}
	for _, item := range defaultAppealCases {
		if err := s.putIfMissing("appeal_cases", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("appeal_case", item.ID, "appeal_case_v1", item.Status); err != nil {
			return err
		}
	}

	defaultPolicies := []recommendationPolicy{
		{
			ID:            "policy_discovery_rank_v12",
			Name:          "发现流重排策略 v12",
			Status:        "simulated",
			PolicyVersion: "policy-2026.03.08",
			GuardrailSnapshot: map[string]any{
				"ctr":        8.9,
				"complaints": 0.29,
				"diversity":  69,
			},
			UpdatedAt: nowRFC3339(),
		},
	}
	for _, item := range defaultPolicies {
		if err := s.putIfMissing("recommendation_policies", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("recommendation_policy", item.ID, "recommendation_policy_v1", item.Status); err != nil {
			return err
		}
	}

	return nil
}

func (s *productService) handleGetBucket(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/ops/experiments/", "/bucket")
	subjectKey := strings.TrimSpace(r.URL.Query().Get("subjectKey"))
	if subjectKey == "" {
		subjectKey = "anonymous"
	}
	result, err := s.resolveExperimentAssignment(experimentID, subjectKey)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *productService) handleAssignBucket(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/ops/experiments/", "/assign")
	var body struct {
		SubjectKey string `json:"subjectKey"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	subjectKey := strings.TrimSpace(body.SubjectKey)
	if subjectKey == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "subjectKey is required"})
		return
	}
	result, err := s.resolveExperimentAssignment(experimentID, subjectKey)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *productService) handleGetStats(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/ops/experiments/", "/stats")
	experiment, ok, err := s.getExperiment(experimentID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "experiment not found"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"experimentId":     experiment.ID,
		"policyVersion":    experiment.PolicyVersion,
		"enabled":          experiment.Enabled,
		"bucketStats":      experiment.BucketStats,
		"assignedSubjects": len(experiment.Assignments),
	})
}

func (s *productService) handleListExperiments(w http.ResponseWriter) {
	items, err := s.store.ListDocuments("experiments")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		experiment, err := decodeDocument[experimentDef](item)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
			return
		}
		out = append(out, map[string]any{
			"id":               experiment.ID,
			"name":             experiment.Name,
			"enabled":          experiment.Enabled,
			"policyVersion":    experiment.PolicyVersion,
			"buckets":          experiment.Buckets,
			"bucketStats":      experiment.BucketStats,
			"assignedSubjects": len(experiment.Assignments),
		})
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i]["id"].(string) < out[j]["id"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": out})
}

func (s *productService) handleRollout(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/control-plane/product/experiments/", ":rollout")
	var body struct {
		Enabled bool        `json:"enabled"`
		Buckets []bucketDef `json:"buckets"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)

	experiment, ok, err := s.getExperiment(experimentID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "experiment not found"})
		return
	}
	before := documentFromStruct(experiment)
	experiment.Enabled = body.Enabled
	if len(body.Buckets) > 0 {
		experiment.Buckets = body.Buckets
		experiment.PolicyVersion = experiment.PolicyVersion + "+rollout"
		experiment.BucketStats = map[string]int{}
		experiment.Assignments = map[string]assignment{}
	}
	if err := s.putDocument("experiments", experiment.ID, experiment); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "experiment",
		ObjectID:   experiment.ID,
		WorkflowID: "experiment_rollout_v1",
		State:      "ramping",
		History: []controlplane.WorkflowTransition{{
			From:   "running",
			To:     "ramping",
			Action: "rollout",
			Actor:  actorFromRequest(r),
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "experiment",
		ObjectID:   experiment.ID,
		Mode:       "single",
		Actor:      actorFromRequest(r),
		Decision:   "approved",
	})
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:       "experiment_rollout_changed",
		ObjectType:    "experiment",
		ObjectID:      experiment.ID,
		Action:        "rollout",
		DangerLevel:   "high",
		Actor:         actorFromRequest(r),
		Environment:   environmentFromRequest(r),
		RequestID:     requestIDFromRequest(r),
		TraceID:       traceIDFromRequest(r),
		WorkflowRef:   workflow.WorkflowID,
		RollbackToken: "rbk-" + experiment.ID,
		Before:        before,
		After:         documentFromStruct(experiment),
		Metadata:      map[string]any{"bucketCount": len(experiment.Buckets)},
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"id":            experiment.ID,
		"enabled":       experiment.Enabled,
		"policyVersion": experiment.PolicyVersion,
		"buckets":       experiment.Buckets,
	})
}

func (s *productService) handleListModerationCases(w http.ResponseWriter) {
	items, err := s.store.ListDocuments("moderation_cases")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleGetModerationCase(w http.ResponseWriter, r *http.Request) {
	caseID := strings.TrimPrefix(r.URL.Path, "/v1/control-plane/product/moderation/cases/")
	caseID = strings.TrimSuffix(caseID, ":startReview")
	caseID = strings.TrimSuffix(caseID, ":applyAction")
	caseID = strings.Trim(caseID, "/")
	item, ok, err := s.store.GetDocument("moderation_cases", caseID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "moderation case not found"})
		return
	}
	workflow, _, _ := s.store.GetWorkflow("moderation_case", caseID)
	approvals, _ := s.store.ListApprovals("moderation_case", caseID)
	writeJSON(w, http.StatusOK, map[string]any{
		"case":      item,
		"workflow":  workflow,
		"approvals": approvals,
	})
}

func (s *productService) handleStartModerationReview(w http.ResponseWriter, r *http.Request) {
	caseID := segmentBetween(r.URL.Path, "/v1/control-plane/product/moderation/cases/", ":startReview")
	item, ok, err := s.store.GetDocument("moderation_cases", caseID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "moderation case not found"})
		return
	}
	before := cloneMap(item)
	item["status"] = "reviewing"
	item["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument("moderation_cases", caseID, item); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "moderation_case",
		ObjectID:   caseID,
		WorkflowID: "moderation_case_v1",
		State:      "reviewing",
		History: []controlplane.WorkflowTransition{{
			From:   "triaged",
			To:     "reviewing",
			Action: "start_review",
			Actor:  actorFromRequest(r),
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "moderation_action_applied",
		ObjectType:  "moderation_case",
		ObjectID:    caseID,
		Action:      "start_review",
		DangerLevel: "high",
		Actor:       actorFromRequest(r),
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		WorkflowRef: workflow.WorkflowID,
		Before:      before,
		After:       item,
	})
	writeJSON(w, http.StatusOK, item)
}

func (s *productService) handleApplyEnforcementAction(w http.ResponseWriter, r *http.Request) {
	caseID := segmentBetween(r.URL.Path, "/v1/control-plane/product/moderation/cases/", ":applyAction")
	var body struct {
		Action string `json:"action"`
		Actor  string `json:"actor"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	action := strings.TrimSpace(body.Action)
	if action == "" {
		action = "take_down"
	}
	actor := strings.TrimSpace(body.Actor)
	if actor == "" {
		actor = actorFromRequest(r)
	}
	item, ok, err := s.store.GetDocument("moderation_cases", caseID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "moderation case not found"})
		return
	}
	before := cloneMap(item)
	approvals, _ := s.store.ListApprovals("moderation_case", caseID)
	if !approvalExists(approvals, actor) {
		_ = s.store.AppendApproval(controlplane.ApprovalDecision{
			ObjectType: "moderation_case",
			ObjectID:   caseID,
			Mode:       "dual",
			Actor:      actor,
			Decision:   action,
		})
		approvals, _ = s.store.ListApprovals("moderation_case", caseID)
	}
	uniqueApprovers := distinctApprovalActors(approvals)
	state := "dual_approval_pending"
	item["status"] = state
	if len(uniqueApprovers) >= 2 {
		state = "action_applied"
		item["status"] = state
		item["resolution"] = action
	}
	item["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument("moderation_cases", caseID, item); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "moderation_case",
		ObjectID:   caseID,
		WorkflowID: "moderation_case_v1",
		State:      state,
		History: []controlplane.WorkflowTransition{{
			From:   "reviewing",
			To:     state,
			Action: action,
			Actor:  actor,
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "moderation_action_applied",
		ObjectType:  "moderation_case",
		ObjectID:    caseID,
		Action:      action,
		DangerLevel: "high",
		Actor:       actor,
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		WorkflowRef: workflow.WorkflowID,
		Before:      before,
		After:       item,
		Metadata:    map[string]any{"approvalCount": len(uniqueApprovers)},
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"case":          item,
		"approvalCount": len(uniqueApprovers),
		"pending":       state != "action_applied",
	})
}

func (s *productService) handleListRecoveryCases(w http.ResponseWriter) {
	items, err := s.store.ListDocuments("recovery_cases")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleGetRecoveryCase(w http.ResponseWriter, r *http.Request) {
	caseID := strings.TrimPrefix(r.URL.Path, "/v1/control-plane/product/recovery/cases/")
	caseID = strings.TrimSuffix(caseID, ":submitDecision")
	caseID = strings.Trim(caseID, "/")
	item, ok, err := s.store.GetDocument("recovery_cases", caseID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "recovery case not found"})
		return
	}
	workflow, _, _ := s.store.GetWorkflow("recovery_case", caseID)
	approvals, _ := s.store.ListApprovals("recovery_case", caseID)
	writeJSON(w, http.StatusOK, map[string]any{
		"case":      item,
		"workflow":  workflow,
		"approvals": approvals,
	})
}

func (s *productService) handleSubmitRecoveryDecision(w http.ResponseWriter, r *http.Request) {
	caseID := segmentBetween(r.URL.Path, "/v1/control-plane/product/recovery/cases/", ":submitDecision")
	var body struct {
		Decision string `json:"decision"`
		Actor    string `json:"actor"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	decision := strings.TrimSpace(body.Decision)
	if decision == "" {
		decision = "recovered"
	}
	actor := strings.TrimSpace(body.Actor)
	if actor == "" {
		actor = actorFromRequest(r)
	}
	item, ok, err := s.store.GetDocument("recovery_cases", caseID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "recovery case not found"})
		return
	}
	before := cloneMap(item)
	approvals, _ := s.store.ListApprovals("recovery_case", caseID)
	if !approvalExists(approvals, actor) {
		_ = s.store.AppendApproval(controlplane.ApprovalDecision{
			ObjectType: "recovery_case",
			ObjectID:   caseID,
			Mode:       "dual",
			Actor:      actor,
			Decision:   decision,
		})
		approvals, _ = s.store.ListApprovals("recovery_case", caseID)
	}
	uniqueApprovers := distinctApprovalActors(approvals)
	state := "dual_review"
	if len(uniqueApprovers) >= 2 {
		state = decision
	}
	item["status"] = state
	item["decision"] = decision
	item["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument("recovery_cases", caseID, item); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "recovery_case",
		ObjectID:   caseID,
		WorkflowID: "recovery_case_v1",
		State:      state,
		History: []controlplane.WorkflowTransition{{
			From:   "evidence_verified",
			To:     state,
			Action: decision,
			Actor:  actor,
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "recovery_decision_submitted",
		ObjectType:  "recovery_case",
		ObjectID:    caseID,
		Action:      decision,
		DangerLevel: "critical",
		Actor:       actor,
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		WorkflowRef: workflow.WorkflowID,
		Before:      before,
		After:       item,
		Metadata:    map[string]any{"approvalCount": len(uniqueApprovers)},
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"case":          item,
		"approvalCount": len(uniqueApprovers),
		"pending":       state == "dual_review",
	})
}

func (s *productService) handleListAppealCases(w http.ResponseWriter) {
	items, err := s.store.ListDocuments("appeal_cases")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleGetAppealCase(w http.ResponseWriter, r *http.Request) {
	caseID := strings.TrimPrefix(r.URL.Path, "/v1/control-plane/product/appeal/cases/")
	caseID = strings.TrimSuffix(caseID, ":submitDecision")
	caseID = strings.Trim(caseID, "/")
	item, ok, err := s.store.GetDocument("appeal_cases", caseID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "appeal case not found"})
		return
	}
	workflow, _, _ := s.store.GetWorkflow("appeal_case", caseID)
	approvals, _ := s.store.ListApprovals("appeal_case", caseID)
	writeJSON(w, http.StatusOK, map[string]any{
		"case":      item,
		"workflow":  workflow,
		"approvals": approvals,
	})
}

func (s *productService) handleSubmitAppealDecision(w http.ResponseWriter, r *http.Request) {
	caseID := segmentBetween(r.URL.Path, "/v1/control-plane/product/appeal/cases/", ":submitDecision")
	var body struct {
		Decision string `json:"decision"`
		Actor    string `json:"actor"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	decision := strings.TrimSpace(body.Decision)
	if decision == "" {
		decision = "approved"
	}
	actor := strings.TrimSpace(body.Actor)
	if actor == "" {
		actor = actorFromRequest(r)
	}
	item, ok, err := s.store.GetDocument("appeal_cases", caseID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "appeal case not found"})
		return
	}
	before := cloneMap(item)
	_ = s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "appeal_case",
		ObjectID:   caseID,
		Mode:       "single",
		Actor:      actor,
		Decision:   decision,
	})
	item["status"] = decision
	item["decision"] = decision
	item["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument("appeal_cases", caseID, item); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "appeal_case",
		ObjectID:   caseID,
		WorkflowID: "appeal_case_v1",
		State:      decision,
		History: []controlplane.WorkflowTransition{{
			From:   "under_review",
			To:     decision,
			Action: decision,
			Actor:  actor,
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "appeal_decision_submitted",
		ObjectType:  "appeal_case",
		ObjectID:    caseID,
		Action:      decision,
		DangerLevel: "high",
		Actor:       actor,
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		WorkflowRef: workflow.WorkflowID,
		Before:      before,
		After:       item,
		Metadata:    map[string]any{"evidenceRefs": item["evidenceRefs"]},
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"case": item,
	})
}

func (s *productService) handleListRecommendationPolicies(w http.ResponseWriter) {
	items, err := s.store.ListDocuments("recommendation_policies")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleSimulateRecommendationPolicy(w http.ResponseWriter, r *http.Request) {
	policyID := segmentBetween(r.URL.Path, "/v1/control-plane/product/recommendation/policies/", ":simulate")
	policy, ok, err := s.getRecommendationPolicy(policyID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "recommendation policy not found"})
		return
	}
	before := documentFromStruct(policy)
	policy.Status = "simulated"
	policy.UpdatedAt = nowRFC3339()
	if err := s.putDocument("recommendation_policies", policy.ID, policy); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	_ = s.store.UpsertWorkflow(controlplane.WorkflowState{
		ObjectType: "recommendation_policy",
		ObjectID:   policy.ID,
		WorkflowID: "recommendation_policy_v1",
		State:      "simulated",
		History: []controlplane.WorkflowTransition{{
			From:   "draft",
			To:     "simulated",
			Action: "simulate",
			Actor:  actorFromRequest(r),
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	})
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "recommendation_policy_activated",
		ObjectType:  "recommendation_policy",
		ObjectID:    policy.ID,
		Action:      "simulate",
		DangerLevel: "high",
		Actor:       actorFromRequest(r),
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		Before:      before,
		After:       documentFromStruct(policy),
	})
	writeJSON(w, http.StatusOK, policy)
}

func (s *productService) handleActivateRecommendationPolicy(w http.ResponseWriter, r *http.Request) {
	policyID := segmentBetween(r.URL.Path, "/v1/control-plane/product/recommendation/policies/", ":activate")
	policy, ok, err := s.getRecommendationPolicy(policyID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "recommendation policy not found"})
		return
	}
	before := documentFromStruct(policy)
	policy.Status = "active"
	policy.UpdatedAt = nowRFC3339()
	if err := s.putDocument("recommendation_policies", policy.ID, policy); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	_ = s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "recommendation_policy",
		ObjectID:   policy.ID,
		Mode:       "single",
		Actor:      actorFromRequest(r),
		Decision:   "activate",
	})
	workflow := controlplane.WorkflowState{
		ObjectType: "recommendation_policy",
		ObjectID:   policy.ID,
		WorkflowID: "recommendation_policy_v1",
		State:      "active",
		History: []controlplane.WorkflowTransition{{
			From:   "canary",
			To:     "active",
			Action: "activate",
			Actor:  actorFromRequest(r),
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:       "recommendation_policy_activated",
		ObjectType:    "recommendation_policy",
		ObjectID:      policy.ID,
		Action:        "activate",
		DangerLevel:   "high",
		Actor:         actorFromRequest(r),
		Environment:   environmentFromRequest(r),
		RequestID:     requestIDFromRequest(r),
		TraceID:       traceIDFromRequest(r),
		WorkflowRef:   workflow.WorkflowID,
		RollbackToken: "rbk-" + policy.ID,
		Before:        before,
		After:         documentFromStruct(policy),
		Metadata:      map[string]any{"guardrailSnapshot": policy.GuardrailSnapshot},
	})
	writeJSON(w, http.StatusOK, policy)
}

func (s *productService) handleRecordVisit(w http.ResponseWriter, r *http.Request) {
	var body struct {
		TargetType string `json:"targetType"`
		TargetKey  string `json:"targetKey"`
		UserID     string `json:"userId"`
		SessionID  string `json:"sessionId"`
		Source     string `json:"source"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "invalid json body"})
		return
	}
	if strings.TrimSpace(body.TargetType) == "" || strings.TrimSpace(body.TargetKey) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "targetType and targetKey are required"})
		return
	}
	record, err := s.telemetry.RecordVisit(r.Context(), application.VisitInput{
		UserID:     body.UserID,
		TargetType: body.TargetType,
		TargetKey:  body.TargetKey,
		SessionID:  body.SessionID,
		Source:     body.Source,
	})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, record)
}

func (s *productService) handleGetVisitStats(w http.ResponseWriter, r *http.Request) {
	stats, err := s.telemetry.GetVisitStats(r.Context(), application.VisitStatsQuery{
		TargetType: strings.TrimSpace(r.URL.Query().Get("targetType")),
		TargetKey:  strings.TrimSpace(r.URL.Query().Get("targetKey")),
	})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, stats)
}

func (s *productService) handleListWorkflows(w http.ResponseWriter) {
	items, err := s.store.ListWorkflows()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleListAudits(w http.ResponseWriter) {
	items, err := s.store.ListAudits()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleListApprovals(w http.ResponseWriter) {
	items, err := s.store.ListAllApprovals()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleProjectionSummary(w http.ResponseWriter) {
	workflows, err := s.store.ListWorkflows()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	approvals, err := s.store.ListAllApprovals()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	audits, err := s.store.ListAudits()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	pendingDualReview := 0
	for _, workflow := range workflows {
		if workflow.State == "dual_review" || workflow.State == "dual_approval_pending" {
			pendingDualReview++
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"workflowCount":     len(workflows),
		"approvalCount":     len(approvals),
		"auditCount":        len(audits),
		"pendingDualReview": pendingDualReview,
		"activeObjectTypes": []string{"moderation_case", "recovery_case", "appeal_case", "experiment", "recommendation_policy"},
	})
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
		if _, err := os.Stat(filepath.Join(current, "contracts", "metadata")); err == nil {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			return wd
		}
		current = parent
	}
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
	return "integration"
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
