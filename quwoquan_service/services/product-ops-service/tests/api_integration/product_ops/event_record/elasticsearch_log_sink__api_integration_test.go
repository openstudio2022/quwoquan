package api_integration

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"testing"
	"time"

	"github.com/docker/go-connections/nat"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestElasticsearchLogSinkPersistsAndQueriesCanonicalTelemetry(
	t *testing.T,
) {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Minute)
	defer cancel()
	endpoint, terminate := integrationElasticsearchEndpoint(t, ctx)
	defer terminate()

	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	config := telemetrypersistence.ElasticsearchConfig{
		Endpoint:               endpoint,
		RawIndex:               "qwq-telemetry-raw-" + suffix,
		StartupDiagnosticIndex: "qwq-telemetry-startup-" + suffix,
		RuntimeLogIndex:        "qwq-telemetry-runtime-" + suffix,
		AggregateIndex:         "qwq-telemetry-hourly-" + suffix,
		Timeout:                5 * time.Second,
	}
	store, err := telemetrypersistence.NewElasticsearchEventLogStore(config)
	if err != nil {
		t.Fatalf("NewElasticsearchEventLogStore() error = %v", err)
	}
	if err := store.EnsureIndices(ctx); err != nil {
		t.Fatalf("EnsureIndices() error = %v", err)
	}
	t.Cleanup(func() {
		for _, indexBase := range []string{
			config.RawIndex,
			config.StartupDiagnosticIndex,
			config.RuntimeLogIndex,
			config.AggregateIndex,
		} {
			for _, resource := range []string{
				"/" + indexBase + "-*",
				"/_index_template/" + indexBase + "-template",
			} {
				request, _ := http.NewRequest(
					http.MethodDelete,
					endpoint+resource,
					nil,
				)
				response, requestErr := http.DefaultClient.Do(request)
				if requestErr == nil {
					_ = response.Body.Close()
				}
			}
		}
	})

	now := time.Now().UTC().Add(-2 * time.Minute)
	eventInputs := []application.EventRecordInput{
		integrationElasticsearchPageEvent(now, "page_open", "session-a"),
		integrationElasticsearchPageEvent(now.Add(time.Second), "page_return", "session-a"),
		postgresRtcMediaQoeEvent(now.Add(2*time.Second), "completed", true, 100, 1),
		postgresRtcMediaQoeEvent(now.Add(3*time.Second), "connection_lost", true, 200, 2),
		postgresRtcMediaQoeEvent(now.Add(4*time.Second), "connect_failed", false, 0, 3),
		postgresRtcMediaQoeEvent(now.Add(5*time.Second), "abandoned", true, 9999, 99),
	}
	records := make([]application.EventRecord, len(eventInputs))
	eventBatchKey := strings.Repeat("a", 64)
	for index, input := range eventInputs {
		records[index] = application.EventRecord{
			EventRecordInput: input,
			BatchKey:         eventBatchKey,
			BatchIndex:       index,
			IngestedAt:       now.Add(time.Duration(index+10) * time.Second),
		}
	}
	if err := store.PutEventBatch(ctx, eventBatchKey, records); err != nil {
		t.Fatalf("PutEventBatch() error = %v", err)
	}
	if err := store.PutEventBatch(ctx, eventBatchKey, records); err != nil {
		t.Fatalf("PutEventBatch() replay error = %v", err)
	}
	complete, err := store.HasEventBatch(ctx, eventBatchKey, len(records))
	if err != nil || !complete {
		t.Fatalf("HasEventBatch() = %v, %v; want true, nil", complete, err)
	}

	startupBatchKey := strings.Repeat("b", 64)
	if err := store.PutStartupDiagnostics(
		ctx,
		startupBatchKey,
		[]application.StartupDiagnosticRecord{{
			EventID:      "startup-event",
			AttemptID:    "startup-attempt",
			Phase:        "flutter_first_frame",
			Outcome:      "succeeded",
			OccurredAt:   now.Format(time.RFC3339Nano),
			Platform:     "ios",
			RuntimeEnv:   "gamma",
			AppVersion:   "1.0.0",
			NetworkClass: "wifi",
		}},
	); err != nil {
		t.Fatalf("PutStartupDiagnostics() error = %v", err)
	}
	complete, err = store.HasStartupDiagnosticBatch(ctx, startupBatchKey, 1)
	if err != nil || !complete {
		t.Fatalf(
			"HasStartupDiagnosticBatch() = %v, %v; want true, nil",
			complete,
			err,
		)
	}

	runtimeBatchKey := strings.Repeat("c", 64)
	if err := store.PutRuntimeLogBatch(
		ctx,
		runtimeBatchKey,
		[]application.RuntimeLogRecord{{
			Fields: map[string]string{
				"schema":             "runtime-observability/v1",
				"occurredAt":         now.Format(time.RFC3339Nano),
				"observedAt":         now.Add(time.Second).Format(time.RFC3339Nano),
				"logKind":            "error",
				"severity":           "error",
				"signal":             "app.runtime_exception",
				"message":            "provider integration failure",
				"actorHash":          "actor-hash",
				"requestId":          "request-sensitive",
				"resourceSourceType": "app",
				"resourceService":    "quwoquan_app",
				"resourceAppVersion": "1.0.0",
			},
			BatchKey:   runtimeBatchKey,
			BatchIndex: 0,
			IngestedAt: now.Add(20 * time.Second),
		}},
	); err != nil {
		t.Fatalf("PutRuntimeLogBatch() error = %v", err)
	}
	complete, err = store.HasRuntimeLogBatch(ctx, runtimeBatchKey, 1)
	if err != nil || !complete {
		t.Fatalf("HasRuntimeLogBatch() = %v, %v; want true, nil", complete, err)
	}
	refreshElasticsearchIndices(t, ctx, endpoint)
	assertElasticsearchLifecycleBinding(
		t,
		ctx,
		endpoint,
		config.RawIndex,
		now,
		"qwq-product-telemetry-raw-3d",
	)
	assertElasticsearchLifecycleBinding(
		t,
		ctx,
		endpoint,
		config.StartupDiagnosticIndex,
		now,
		"qwq-product-telemetry-raw-3d",
	)
	assertElasticsearchLifecycleBinding(
		t,
		ctx,
		endpoint,
		config.RuntimeLogIndex,
		now,
		"qwq-product-telemetry-raw-3d",
	)
	assertElasticsearchLifecycleBinding(
		t,
		ctx,
		endpoint,
		config.AggregateIndex,
		now,
		"qwq-product-telemetry-hourly-90d",
	)

	from := now.Add(-time.Hour)
	to := now.Add(time.Hour)
	eventSummary, err := store.GetEventSummary(
		ctx,
		application.EventSummaryQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("GetEventSummary() error = %v", err)
	}
	if eventSummary.TotalCount != int64(len(records)) ||
		eventSummary.SessionCount != 5 ||
		eventSummary.SourceKind != "hourly_rollup" {
		t.Fatalf("GetEventSummary() = %+v", eventSummary)
	}

	drilldown, err := store.GetEventDrilldown(
		ctx,
		application.EventDrilldownQuery{From: from, To: to, Limit: 20},
	)
	if err != nil {
		t.Fatalf("GetEventDrilldown() error = %v", err)
	}
	if len(drilldown.Items) != len(records) {
		t.Fatalf("GetEventDrilldown() items = %d; want %d", len(drilldown.Items), len(records))
	}
	for _, item := range drilldown.Items {
		if strings.HasPrefix(item.SessionID, "s.") {
			t.Fatalf("GetEventDrilldown() leaked sessionId: %+v", item)
		}
	}

	pageStats, err := store.GetPageExperienceStats(
		ctx,
		application.PageExperienceQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("GetPageExperienceStats() error = %v", err)
	}
	if len(pageStats) != 2 {
		t.Fatalf("GetPageExperienceStats() = %+v", pageStats)
	}

	sessions, totalEvents, err := store.ListDistinctSessions(ctx, from, to, 100)
	if err != nil {
		t.Fatalf("ListDistinctSessions() error = %v", err)
	}
	if len(sessions) != 5 || totalEvents != int64(len(records)) {
		t.Fatalf("ListDistinctSessions() = %v, %d", sessions, totalEvents)
	}

	rtcSummary, err := store.ReadRtcMediaQoeSummary(
		ctx,
		application.RtcMediaQoeSummaryQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("ReadRtcMediaQoeSummary() error = %v", err)
	}
	if rtcSummary.EffectiveSampleCount != 3 ||
		rtcSummary.MediaConnectedCount != 2 ||
		rtcSummary.ConnectionLostCount != 1 ||
		rtcSummary.ReconnectCount != 6 ||
		rtcSummary.ConnectP95MS == nil ||
		*rtcSummary.ConnectP95MS < 100 ||
		*rtcSummary.ConnectP95MS > 200 {
		t.Fatalf("ReadRtcMediaQoeSummary() = %+v", rtcSummary)
	}

	runtimeSummary, err := store.GetRuntimeLogSummary(
		ctx,
		application.RuntimeLogSummaryQuery{From: from, To: to},
	)
	if err != nil {
		t.Fatalf("GetRuntimeLogSummary() error = %v", err)
	}
	if runtimeSummary.TotalCount != 1 ||
		runtimeSummary.DimensionCounters["signal"]["app.runtime_exception"] != 1 {
		t.Fatalf("GetRuntimeLogSummary() = %+v", runtimeSummary)
	}
	runtimeDrilldown, err := store.GetRuntimeLogDrilldown(
		ctx,
		application.RuntimeLogDrilldownQuery{
			From:            from,
			To:              to,
			Limit:           10,
			ActorHash:       "actor-hash",
			MessageContains: "integration failure",
		},
	)
	if err != nil {
		t.Fatalf("GetRuntimeLogDrilldown() error = %v", err)
	}
	if len(runtimeDrilldown.Items) != 1 ||
		len(runtimeDrilldown.Items[0].Correlation) != 0 {
		t.Fatalf("GetRuntimeLogDrilldown() = %+v", runtimeDrilldown)
	}
}

func integrationElasticsearchEndpoint(
	t *testing.T,
	ctx context.Context,
) (string, func()) {
	t.Helper()
	if endpoint := strings.TrimSpace(os.Getenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT")); endpoint != "" {
		return strings.TrimRight(endpoint, "/"), func() {}
	}
	ensureDockerHostForTestcontainers(t)
	container, err := testcontainers.GenericContainer(
		ctx,
		testcontainers.GenericContainerRequest{
			ContainerRequest: testcontainers.ContainerRequest{
				Image:           "docker.elastic.co/elasticsearch/elasticsearch:8.13.4",
				ImagePlatform:   "linux/amd64",
				AlwaysPullImage: true,
				SkipReaper:      true,
				AutoRemove:      true,
				Env: map[string]string{
					"discovery.type":                                    "single-node",
					"xpack.security.enabled":                            "false",
					"xpack.security.http.ssl.enabled":                   "false",
					"cluster.routing.allocation.disk.threshold_enabled": "false",
					"ES_JAVA_OPTS":                                      "-Xms512m -Xmx512m",
				},
				ExposedPorts: []string{"9200/tcp"},
				WaitingFor: wait.ForHTTP("/_cluster/health?wait_for_status=yellow&timeout=1s").
					WithPort(nat.Port("9200/tcp")).
					WithStartupTimeout(15 * time.Minute),
			},
			Started: true,
		},
	)
	if err != nil {
		t.Fatalf("start Elasticsearch testcontainer: %v", err)
	}
	endpoint, err := container.Endpoint(ctx, "http")
	if err != nil {
		_ = container.Terminate(context.Background())
		t.Fatalf("resolve Elasticsearch testcontainer endpoint: %v", err)
	}
	return endpoint, func() {
		terminateCtx, terminateCancel := context.WithTimeout(
			context.Background(),
			time.Minute,
		)
		defer terminateCancel()
		if err := container.Terminate(terminateCtx); err != nil {
			t.Errorf("terminate Elasticsearch testcontainer: %v", err)
		}
	}
}

func ensureDockerHostForTestcontainers(t *testing.T) {
	t.Helper()
	t.Setenv("TESTCONTAINERS_RYUK_DISABLED", "true")
	if strings.TrimSpace(os.Getenv("DOCKER_HOST")) != "" {
		return
	}
	output, err := exec.Command(
		"docker",
		"context",
		"inspect",
		"--format",
		"{{.Endpoints.docker.Host}}",
	).Output()
	if err != nil {
		t.Fatalf("resolve Docker context for Elasticsearch testcontainer: %v", err)
	}
	dockerHost := strings.TrimSpace(string(output))
	if dockerHost == "" {
		t.Fatal("active Docker context has no endpoint")
	}
	t.Setenv("DOCKER_HOST", dockerHost)
}

func integrationElasticsearchPageEvent(
	occurredAt time.Time,
	eventType string,
	session string,
) application.EventRecordInput {
	readyMS := 120
	durationMS := 500
	input := application.EventRecordInput{
		LogType:            "event",
		EventType:          eventType,
		SessionID:          "s." + session + ".1",
		PageName:           "chat_detail",
		OccurredAt:         occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple",
		DeviceModel:        "iPhone",
		AppVersion:         "1.0.0",
		NetworkClass:       "wifi",
		DevicePlatform:     "ios",
	}
	if eventType == "page_open" {
		input.ReadyMS = &readyMS
	}
	if eventType == "page_return" {
		input.DurationMS = &durationMS
	}
	return input
}

func assertElasticsearchLifecycleBinding(
	t *testing.T,
	ctx context.Context,
	endpoint string,
	indexBase string,
	instant time.Time,
	expectedPolicy string,
) {
	t.Helper()
	resources := []string{
		"/_index_template/" + indexBase + "-template",
		"/" + indexBase + "-" + instant.UTC().Format("2006.01.02") + "/_settings",
	}
	for _, resource := range resources {
		request, err := http.NewRequestWithContext(
			ctx,
			http.MethodGet,
			endpoint+resource,
			nil,
		)
		if err != nil {
			t.Fatalf("build Elasticsearch lifecycle request: %v", err)
		}
		response, err := http.DefaultClient.Do(request)
		if err != nil {
			t.Fatalf("read Elasticsearch lifecycle resource %s: %v", resource, err)
		}
		body, readErr := io.ReadAll(io.LimitReader(response.Body, 64<<10))
		_ = response.Body.Close()
		if readErr != nil {
			t.Fatalf("read Elasticsearch lifecycle response %s: %v", resource, readErr)
		}
		if response.StatusCode < http.StatusOK ||
			response.StatusCode >= http.StatusMultipleChoices {
			t.Fatalf(
				"Elasticsearch lifecycle resource %s status=%d: %s",
				resource,
				response.StatusCode,
				body,
			)
		}
		if !bytes.Contains(body, []byte(expectedPolicy)) {
			t.Fatalf(
				"Elasticsearch lifecycle resource %s does not bind policy %s: %s",
				resource,
				expectedPolicy,
				body,
			)
		}
	}
}

func refreshElasticsearchIndices(
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
