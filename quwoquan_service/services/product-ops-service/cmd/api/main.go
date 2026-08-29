package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/artifactidentity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/servicehost"
	"quwoquan_service/runtime/servicekit"
	accountenforcementapp "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/application"
	apprelease "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	experimenthttp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/adapters/inbound/http"
	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	assignmenthttp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/adapters/inbound/http"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	premiumpoolapp "quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/application"
	recoveryfailure "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/application"
	visitapplication "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/application"
)

type productService struct {
	store              controlplane.StateStore
	telemetry          *application.TelemetryService
	visits             *visitapplication.Service
	runtimeLogs        *application.RuntimeLogService
	runtimeLogStore    application.RuntimeLogStore
	growth             *application.GrowthService
	prometheus         application.PrometheusQuery
	experimentHTTP     *experimenthttp.Handler
	assignmentHTTP     *assignmenthttp.Handler
	publisher          runtimemessaging.EventPublisher
	appRelease         *apprelease.Service
	recoveryFailures   *recoveryfailure.Service
	accountEnforcement *accountenforcementapp.Service
	premiumPool        *premiumpoolapp.Service
}

func main() {
	if _, err := artifactidentity.LoadAndValidate(
		os.Getenv("QWQ_ARTIFACT_IDENTITY_FILE"),
		os.Getenv("APP_ENV"),
	); err != nil {
		log.Fatalf("product-ops-service artifact identity invalid: %v", err)
	}
	servicekit.RunStandalone(serviceName, func() (servicehost.Module, error) {
		return newModule()
	})
}

func newProductService(
	store controlplane.StateStore,
	telemetry *application.TelemetryService,
	visits *visitapplication.Service,
	experiments *experimentapp.Facade,
	assignments *assignmentapp.Facade,
	publishers ...runtimemessaging.EventPublisher,
) *productService {
	return newProductServiceWithRuntimeLogs(
		store,
		telemetry,
		visits,
		nil,
		experiments,
		assignments,
		publishers...,
	)
}

func newProductServiceWithRuntimeLogs(
	store controlplane.StateStore,
	telemetry *application.TelemetryService,
	visits *visitapplication.Service,
	runtimeLogs *application.RuntimeLogService,
	experiments *experimentapp.Facade,
	assignments *assignmentapp.Facade,
	publishers ...runtimemessaging.EventPublisher,
) *productService {
	var publisher runtimemessaging.EventPublisher
	if len(publishers) > 0 {
		publisher = publishers[0]
	}
	if store == nil || telemetry == nil || visits == nil || experiments == nil || assignments == nil {
		panic("product service requires control-plane store, telemetry, visits, experiment and assignment facades")
	}
	experimentHandler, err := experimenthttp.NewHandler(experiments, assignments)
	if err != nil {
		panic(err)
	}
	assignmentHandler, err := assignmenthttp.NewHandler(assignments)
	if err != nil {
		panic(err)
	}
	return &productService{
		store: store, telemetry: telemetry, visits: visits, runtimeLogs: runtimeLogs,
		experimentHTTP: experimentHandler, assignmentHTTP: assignmentHandler,
		publisher: publisher,
	}
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

func approvalExistsForIntent(
	items []controlplane.ApprovalDecision,
	actor string,
	payloadDigest string,
	decision string,
) bool {
	for _, item := range items {
		if item.Actor == actor &&
			item.Mode == "dual" &&
			item.PayloadDigest == payloadDigest &&
			item.Decision == decision {
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

func dualApprovalPayloadDigest(before controlplane.Document, intent string) string {
	payload, _ := json.Marshal(struct {
		Before controlplane.Document `json:"before"`
		Intent string                `json:"intent"`
	}{Before: before, Intent: strings.TrimSpace(intent)})
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}

func dualApprovalSatisfied(
	items []controlplane.ApprovalDecision,
	payloadDigest string,
	decision string,
) bool {
	actors := make(map[string]struct{}, 2)
	for _, item := range items {
		if item.Mode != "dual" ||
			item.PayloadDigest != payloadDigest ||
			item.Decision != decision {
			continue
		}
		actor := strings.TrimSpace(item.Actor)
		if actor != "" {
			actors[actor] = struct{}{}
		}
	}
	return len(actors) >= 2
}

func distinctMatchingApprovalActors(
	items []controlplane.ApprovalDecision,
	payloadDigest string,
	decision string,
) []string {
	seen := make(map[string]struct{}, 2)
	for _, item := range items {
		if item.Mode != "dual" ||
			item.PayloadDigest != payloadDigest ||
			item.Decision != decision {
			continue
		}
		if actor := strings.TrimSpace(item.Actor); actor != "" {
			seen[actor] = struct{}{}
		}
	}
	out := make([]string, 0, len(seen))
	for actor := range seen {
		out = append(out, actor)
	}
	sort.Strings(out)
	return out
}

func countMatchingApprovals(
	items []controlplane.ApprovalDecision,
	payloadDigest string,
	decision string,
) int {
	return len(distinctMatchingApprovalActors(items, payloadDigest, decision))
}

func actorFromRequest(r *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		if actor := strings.TrimSpace(principal.Actor.AccountID); actor != "" {
			return actor
		}
		if actor := strings.TrimSpace(principal.Actor.DeviceActorID); actor != "" {
			return actor
		}
	}
	return "unverified"
}

func environmentFromRequest(r *http.Request) string {
	_ = r
	if env := strings.TrimSpace(os.Getenv("APP_ENV")); env != "" {
		return env
	}
	return "unknown"
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

func writeRuntimeNotFound(
	w http.ResponseWriter,
	r *http.Request,
	_ int,
	_ string,
	_ string,
) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
			"接口不存在",
			"route not found",
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
