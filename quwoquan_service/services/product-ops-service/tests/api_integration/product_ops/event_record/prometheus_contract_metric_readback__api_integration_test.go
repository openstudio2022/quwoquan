// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-002
// readiness_case: report-event-batch-api
//
// 契约指标运行时读回：真实 Prometheus 加载 ContractGraph 生成的 recording
// rules，scrape 统一中间件形状的样本后，必须能按 operation/contract_metric
// label 查询到派生 series。这补上「静态契约闭合 → 运行时求值」的验证空白。
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"

	"quwoquan_service/internal/platform/testinfra"
)

const contractRecordingRulesPath = "quwoquan_ops/observability/monitoring/alerts/ops_contract/event_record.yaml"

func TestPrometheusLoadsContractRecordingRulesAndDerivesContractMetricSeries(
	t *testing.T,
) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	testinfra.ConfigureLocalContainerRuntime()

	// 宿主侧最小 /metrics 面：发射统一中间件形状的样本，计数随每次
	// scrape 递增，确保 recording rule 求值有非零输入。
	var scrapes atomic.Int64
	metricsServer := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			count := scrapes.Add(1) * 7
			w.Header().Set("Content-Type", "text/plain; version=0.0.4")
			fmt.Fprintf(
				w,
				"http_server_requests_total{service=\"product-ops-service\",method=\"POST\",route=\"/ops/events\",status=\"200\"} %d\n",
				count,
			)
		},
	))
	defer metricsServer.Close()
	_, hostPort, err := net.SplitHostPort(strings.TrimPrefix(metricsServer.URL, "http://"))
	if err != nil {
		t.Fatalf("parse metrics server port: %v", err)
	}

	repoRoot := resolveIntegrationRepoRoot(t)
	rulesSource := filepath.Join(repoRoot, contractRecordingRulesPath)
	if _, err := os.Stat(rulesSource); err != nil {
		t.Fatalf("contract recording rules missing: %v", err)
	}
	configDir := t.TempDir()
	prometheusConfig := fmt.Sprintf(`global:
  scrape_interval: 1s
  evaluation_interval: 1s
rule_files:
  - /etc/prometheus/rules/event_record.yaml
scrape_configs:
  - job_name: quwoquan-service-plane
    metrics_path: /metrics
    static_configs:
      - targets:
          - host.testcontainers.internal:%s
`, hostPort)
	configPath := filepath.Join(configDir, "prometheus.yml")
	if err := os.WriteFile(configPath, []byte(prometheusConfig), 0o644); err != nil {
		t.Fatalf("write prometheus config: %v", err)
	}

	var exposedHostPort int
	if _, err := fmt.Sscanf(hostPort, "%d", &exposedHostPort); err != nil {
		t.Fatalf("parse host port: %v", err)
	}
	container, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: testcontainers.ContainerRequest{
			Image:           "prom/prometheus:v2.53.0",
			SkipReaper:      true,
			ExposedPorts:    []string{"9090/tcp"},
			HostAccessPorts: []int{exposedHostPort},
			Files: []testcontainers.ContainerFile{
				{
					HostFilePath:      configPath,
					ContainerFilePath: "/etc/prometheus/prometheus.yml",
					FileMode:          0o644,
				},
				{
					HostFilePath:      rulesSource,
					ContainerFilePath: "/etc/prometheus/rules/event_record.yaml",
					FileMode:          0o644,
				},
			},
			WaitingFor: wait.ForHTTP("/-/ready").
				WithPort("9090/tcp").
				WithStartupTimeout(5 * time.Minute),
		},
		Started: true,
	})
	if err != nil {
		t.Fatalf("start prometheus container: %v", err)
	}
	defer func() { _ = container.Terminate(context.Background()) }()

	endpoint, err := container.PortEndpoint(ctx, "9090/tcp", "http")
	if err != nil {
		t.Fatalf("resolve prometheus endpoint: %v", err)
	}

	query := `quwoquan_ops_contract_operation_requests_total{operation="ops.event_record.ReportEventBatch",contract_metric="ops_event_batch_report"}`
	deadline := time.Now().Add(3 * time.Minute)
	var lastBody string
	for time.Now().Before(deadline) {
		time.Sleep(2 * time.Second)
		body, queryErr := queryPrometheus(ctx, endpoint, query)
		if queryErr != nil {
			lastBody = queryErr.Error()
			continue
		}
		lastBody = body
		var payload struct {
			Data struct {
				Result []struct {
					Metric map[string]string `json:"metric"`
				} `json:"result"`
			} `json:"data"`
		}
		if err := json.Unmarshal([]byte(body), &payload); err != nil {
			continue
		}
		if len(payload.Data.Result) == 0 {
			continue
		}
		metric := payload.Data.Result[0].Metric
		if metric["contract_metric"] != "ops_event_batch_report" ||
			metric["operation"] != "ops.event_record.ReportEventBatch" ||
			metric["service"] != "product-ops-service" {
			t.Fatalf("derived series labels drifted: %+v", metric)
		}
		return
	}
	t.Fatalf(
		"contract recording rule did not derive contract_metric series in time; last=%s",
		lastBody,
	)
}

func queryPrometheus(ctx context.Context, endpoint, query string) (string, error) {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		endpoint+"/api/v1/query?query="+url.QueryEscape(query),
		nil,
	)
	if err != nil {
		return "", err
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return "", err
	}
	return string(body), nil
}

func resolveIntegrationRepoRoot(t *testing.T) string {
	t.Helper()
	directory, err := os.Getwd()
	if err != nil {
		t.Fatalf("resolve working directory: %v", err)
	}
	for {
		if _, statErr := os.Stat(filepath.Join(directory, "quwoquan_ops")); statErr == nil {
			return directory
		}
		parent := filepath.Dir(directory)
		if parent == directory {
			t.Fatal("repo root with quwoquan_ops was not found")
		}
		directory = parent
	}
}
