// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-003
// readiness_case: report-recovery-failure-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rterr "quwoquan_service/runtime/errors"
	rtredis "quwoquan_service/runtime/redis"
	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	eventpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
	recoveryhttp "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/adapters/inbound/http"
	recoveryapp "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/application"
	recoveryreporter "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/infrastructure/eventrecord"
	testsupport "quwoquan_service/services/product-ops-service/tests/support"
)

func TestRecoveryFailureHTTPPersistsSanitizedFactInElasticsearch(
	t *testing.T,
) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()
	testinfra.ConfigureLocalContainerRuntime()
	endpoint, terminateElasticsearch := testsupport.StartElasticsearch(t, ctx)
	t.Cleanup(terminateElasticsearch)

	redisRuntime, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	if err := redisRuntime.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	redisRouter, err := platformredis.NewRouter(realRedisRouterConfig(redisRuntime))
	if err != nil {
		t.Fatalf("create real Redis router: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := redisRouter.Close(); closeErr != nil {
			t.Errorf("close Redis router: %v", closeErr)
		}
		closeCtx, closeCancel := context.WithTimeout(context.Background(), time.Minute)
		defer closeCancel()
		if closeErr := redisRuntime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})

	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	config := eventpersistence.ElasticsearchConfig{
		Endpoint:               endpoint,
		RawIndex:               "qwq-recovery-raw-" + suffix,
		StartupDiagnosticIndex: "qwq-recovery-startup-" + suffix,
		RuntimeLogIndex:        "qwq-recovery-runtime-" + suffix,
		AggregateIndex:         "qwq-recovery-hourly-" + suffix,
		Timeout:                30 * time.Second,
	}
	store, err := eventpersistence.NewElasticsearchEventLogStore(config)
	if err != nil {
		t.Fatalf("create Elasticsearch runtime log store: %v", err)
	}
	if err := store.EnsureIndices(ctx); err != nil {
		t.Fatalf("ensure Elasticsearch runtime log indices: %v", err)
	}
	t.Cleanup(func() {
		cleanupElasticsearchResources(t, endpoint, config)
	})

	ledger := eventpersistence.NewRedisEventBatchLedger(
		redisRouter.Scene("general"),
	)
	runtimeLogs := eventapp.NewRuntimeLogService(store, ledger)
	reporter, err := recoveryreporter.NewReporter(runtimeLogs)
	if err != nil {
		t.Fatalf("create RecoveryFailure EventRecord reporter: %v", err)
	}
	mux := http.NewServeMux()
	recoveryhttp.NewHandler(
		recoveryapp.NewService(reporter),
		writeRecoveryIntegrationError,
	).Register(mux)

	now := time.Now().UTC()
	payload := map[string]any{
		"occurredAt":   now.Format(time.RFC3339Nano),
		"appVersion":   "1.8.2",
		"buildNumber":  "18201",
		"platform":     "android",
		"osVersion":    "15",
		"deviceModel":  "Pixel",
		"errorSource":  "flutter",
		"errorType":    "DatabaseOpenException",
		"errorMessage": "authorization=secret user@example.com",
		"stackTrace":   "at /Users/alice/app.dart https://quwoquan.com/p?token=secret",
	}
	for attempt := 0; attempt < 2; attempt++ {
		response := postRecoveryFailure(t, mux, payload)
		if response.Code != http.StatusNoContent {
			t.Fatalf(
				"report attempt=%d status=%d body=%s",
				attempt+1,
				response.Code,
				response.Body.String(),
			)
		}
	}
	refreshElasticsearch(t, ctx, endpoint)

	drilldown, err := runtimeLogs.GetRuntimeLogDrilldown(
		ctx,
		eventapp.RuntimeLogDrilldownQuery{
			Signal: "app.exception.flutter",
			From:   now.Add(-time.Minute),
			To:     time.Now().UTC().Add(time.Minute),
			Limit:  10,
		},
	)
	if err != nil {
		t.Fatalf("query persisted recovery fact: %v", err)
	}
	if drilldown.TotalCount != 1 || len(drilldown.Items) != 1 {
		t.Fatalf("recovery facts total=%d items=%d", drilldown.TotalCount, len(drilldown.Items))
	}
	item := drilldown.Items[0]
	if item.Signal != "app.exception.flutter" ||
		item.Resource["sourceType"] != "app" ||
		item.Resource["service"] != "quwoquan_app" ||
		item.Resource["appVersion"] != "1.8.2" {
		t.Fatalf("unexpected recovery fact: %+v", item)
	}
	encoded, err := json.Marshal(item)
	if err != nil {
		t.Fatalf("encode recovery fact: %v", err)
	}
	for _, secret := range []string{
		"secret",
		"user@example.com",
		"/Users/alice",
		"token=secret",
	} {
		if strings.Contains(string(encoded), secret) {
			t.Fatalf("persisted recovery fact contains %q: %s", secret, encoded)
		}
	}
}

func realRedisRouterConfig(runtime *testinfra.RealRedis) rtredis.RouterConfig {
	scenes := make(map[string]rtredis.SceneConfig, len(rtredis.GeneratedSceneNames()))
	for _, name := range rtredis.GeneratedSceneNames() {
		scenes[name] = rtredis.SceneConfig{
			Mode:     "standalone",
			Addr:     runtime.Addr,
			Password: runtime.Password,
			DB:       0,
			TLS:      runtime.TLS,
		}
	}
	return rtredis.RouterConfig{
		Scenes:       scenes,
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	}
}

func postRecoveryFailure(
	t *testing.T,
	handler http.Handler,
	payload map[string]any,
) *httptest.ResponseRecorder {
	t.Helper()
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal recovery payload: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/ops/recovery-failures",
		bytes.NewReader(body),
	)
	request.RemoteAddr = "192.0.2.10:1234"
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func writeRecoveryIntegrationError(
	w http.ResponseWriter,
	r *http.Request,
	status int,
	userMessage string,
	debugMessage string,
) {
	module, kind, reason := rterr.ModuleOps, rterr.KindSystem, "internal_error"
	if status == http.StatusBadRequest {
		kind, reason = rterr.KindUser, "invalid_argument"
	}
	err := rterr.NewAppError(
		rterr.NewCode(module, kind, reason),
		userMessage,
		debugMessage,
	).WithMetadata(reason, status)
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func refreshElasticsearch(
	t *testing.T,
	ctx context.Context,
	endpoint string,
) {
	t.Helper()
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		endpoint+"/_refresh",
		nil,
	)
	if err != nil {
		t.Fatalf("build Elasticsearch refresh request: %v", err)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("refresh Elasticsearch indices: %v", err)
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(response.Body, 4096))
	if response.StatusCode < http.StatusOK ||
		response.StatusCode >= http.StatusMultipleChoices {
		t.Fatalf(
			"refresh Elasticsearch indices status=%d: %s",
			response.StatusCode,
			body,
		)
	}
}

func cleanupElasticsearchResources(
	t *testing.T,
	endpoint string,
	config eventpersistence.ElasticsearchConfig,
) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
	defer cancel()
	for _, indexBase := range []string{
		config.RawIndex,
		config.StartupDiagnosticIndex,
		config.RuntimeLogIndex,
		config.AggregateIndex,
	} {
		for _, resource := range []string{
			"/" + indexBase + "-" + time.Now().UTC().Format("2006.01.02"),
			"/_index_template/" + indexBase + "-template",
		} {
			request, err := http.NewRequestWithContext(
				ctx,
				http.MethodDelete,
				endpoint+resource,
				nil,
			)
			if err != nil {
				t.Errorf("build Elasticsearch cleanup request: %v", err)
				continue
			}
			response, err := http.DefaultClient.Do(request)
			if err != nil {
				t.Errorf("delete Elasticsearch resource %s: %v", resource, err)
				continue
			}
			_ = response.Body.Close()
			if response.StatusCode != http.StatusNotFound &&
				(response.StatusCode < http.StatusOK ||
					response.StatusCode >= http.StatusMultipleChoices) {
				t.Errorf(
					"delete Elasticsearch resource %s status=%d",
					resource,
					response.StatusCode,
				)
			}
		}
	}
}
