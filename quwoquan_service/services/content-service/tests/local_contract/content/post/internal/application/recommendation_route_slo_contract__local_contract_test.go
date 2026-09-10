// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-006
package local_contract

import (
	"fmt"
	"math"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

type recommendationRouteSLI struct {
	ID          string         `yaml:"id"`
	Source      string         `yaml:"source"`
	SourceRef   string         `yaml:"sourceRef"`
	SLI         string         `yaml:"sli"`
	Objective   float64        `yaml:"objective"`
	Objectives  map[string]int `yaml:"objectives"`
	Observation struct {
		Window       string `yaml:"window"`
		ReleaseProof bool   `yaml:"release_proof"`
	} `yaml:"observation"`
	DiagnosticObjectives struct {
		Status string `yaml:"status"`
		P50MS  int    `yaml:"p50_ms"`
		P99MS  int    `yaml:"p99_ms"`
	} `yaml:"diagnostic_objectives"`
}

type recommendationRouteSLO struct {
	SLIs      []recommendationRouteSLI `yaml:"slis"`
	LoadModel struct {
		TrafficClasses map[string]struct {
			ServerLatencyMS map[string]int `yaml:"server_latency_ms"`
			ErrorRateMax    float64        `yaml:"error_rate_max"`
		} `yaml:"traffic_classes"`
	} `yaml:"load_model"`
}

func TestRecommendationRouteSLOCanonicalLocalContract(t *testing.T) {
	root := resolveRepoRoot(t)
	var slo recommendationRouteSLO
	mustLoadYAML(t, filepath.Join(root, "quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml"), &slo)

	seen := map[string]bool{}
	for _, sli := range slo.SLIs {
		if sli.ID != "recommendation_feed_latency" && sli.ID != "recommendation_feed_availability" {
			continue
		}
		if seen[sli.ID] {
			t.Fatalf("duplicate route SLI %s", sli.ID)
		}
		seen[sli.ID] = true
		t.Run(sli.ID, func(t *testing.T) {
			// 从声明的引用读取真实 operations YAML，而不是另存一组期望阈值。
			contract := resolveRecommendationRouteSLO(t, root, sli.SourceRef)
			if sli.Observation.Window != "rolling_5m" || sli.Observation.ReleaseProof {
				t.Fatalf("route SLI must be rolling_5m observation, not release proof: %+v", sli.Observation)
			}
			selector := fmt.Sprintf(`service="content-service", method="%s", route="%s"`, contract.Method, contract.Path)
			if sli.ID == "recommendation_feed_latency" {
				if len(sli.Objectives) != 1 || sli.Objectives["p95_ms"] != contract.SLO.LatencyP95MS {
					t.Fatalf("route objectives=%v, canonical GetFeed p95=%d", sli.Objectives, contract.SLO.LatencyP95MS)
				}
				want := fmt.Sprintf(`histogram_quantile(q, sum(rate(http_server_duration_seconds_bucket{%s}[5m])) by (le))`, selector)
				if sli.Source != "http_server_duration_seconds" || sli.SLI != want {
					t.Fatalf("route histogram scope drifted: %+v; want %s", sli, want)
				}
				// 保留旧独立分位诊断目标，但不冒充 canonical 路由目标或强压首刷 P99。
				if d := sli.DiagnosticObjectives; d.Status != "unresolved" || d.P50MS != 80 || d.P99MS != 400 {
					t.Fatalf("independent diagnostic targets must remain explicitly unresolved: %+v", d)
				}
			} else {
				if math.Abs(sli.Objective-contract.SLO.AvailabilityPercent/100) > 1e-12 {
					t.Fatalf("route availability=%g, canonical GetFeed=%g%%", sli.Objective, contract.SLO.AvailabilityPercent)
				}
				want := fmt.Sprintf(`1 - sum(rate(http_server_requests_total{%s, status=~"5.."}[5m])) / sum(rate(http_server_requests_total{%s}[5m]))`, selector, selector)
				if sli.Source != "http_server_requests_total" || sli.SLI != want {
					t.Fatalf("availability must retain HTTP 5xx/all-request denominator: %+v; want %s", sli, want)
				}
			}
		})
	}
	if len(seen) != 2 {
		t.Fatalf("missing route SLI: %v", seen)
	}

	// 压测只读各 traffic class；不把首刷/续页 0.5% 误写成整路由错误预算。
	for class, want := range map[string]map[string]int{
		"feed_first_page": {"p50": 150, "p95": 500, "p99": 900},
		"feed_pagination": {"p50": 60, "p95": 200, "p99": 400},
	} {
		got := slo.LoadModel.TrafficClasses[class]
		for percentile, budget := range want {
			if got.ServerLatencyMS[percentile] != budget {
				t.Errorf("%s %s=%d, want independent load target %d", class, percentile, got.ServerLatencyMS[percentile], budget)
			}
		}
		if got.ErrorRateMax != 0.005 {
			t.Errorf("%s error_rate_max=%g, want separate load target 0.005", class, got.ErrorRateMax)
		}
	}
}

type recommendationRouteOperation struct {
	Operation string `yaml:"operation"`
	Method    string `yaml:"method"`
	Path      string `yaml:"path"`
	Telemetry struct {
		Metric string `yaml:"metric"`
	} `yaml:"telemetry"`
	SLO struct {
		LatencyP95MS        int     `yaml:"latency_p95_ms"`
		AvailabilityPercent float64 `yaml:"availability_percent"`
	} `yaml:"slo"`
}

func resolveRecommendationRouteSLO(t *testing.T, root, sourceRef string) recommendationRouteOperation {
	t.Helper()
	path, anchor, ok := strings.Cut(sourceRef, "#")
	if !ok || path != "quwoquan_service/services/content-service/contracts/content/post/operations.yaml" || anchor != "api_routes.GetFeed.slo" {
		t.Fatalf("sourceRef must resolve canonical GetFeed SLO, got %q", sourceRef)
	}
	var operations struct {
		APIRoutes []recommendationRouteOperation `yaml:"api_routes"`
	}
	mustLoadYAML(t, filepath.Join(root, path), &operations)
	var matches []recommendationRouteOperation
	for _, route := range operations.APIRoutes {
		if route.Operation == strings.Split(anchor, ".")[1] {
			matches = append(matches, route)
		}
	}
	if len(matches) != 1 {
		t.Fatalf("sourceRef %s resolved %d operations", sourceRef, len(matches))
	}
	route := matches[0]
	if route.Method != "GET" || route.Path != "/content/feed" || route.Telemetry.Metric == "" || route.SLO.LatencyP95MS <= 0 || route.SLO.AvailabilityPercent <= 0 || route.SLO.AvailabilityPercent > 100 {
		t.Fatalf("invalid GetFeed contract: %+v", route)
	}
	return route
}

func TestRecommendationRouteSLOGeneratedAlertsLocalContract(t *testing.T) {
	root := resolveRepoRoot(t)
	var slo recommendationRouteSLO
	mustLoadYAML(t, filepath.Join(root, "quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml"), &slo)
	var sourceRef string
	for _, sli := range slo.SLIs {
		if sli.ID == "recommendation_feed_availability" {
			sourceRef = sli.SourceRef
		}
	}
	contract := resolveRecommendationRouteSLO(t, root, sourceRef)
	var records struct {
		Groups []struct {
			Rules []struct {
				Record string            `yaml:"record"`
				Expr   string            `yaml:"expr"`
				Labels map[string]string `yaml:"labels"`
			} `yaml:"rules"`
		} `yaml:"groups"`
	}
	mustLoadYAML(t, filepath.Join(root, "quwoquan_ops/observability/monitoring/alerts/content_contract/post.yaml"), &records)
	selector := fmt.Sprintf(`service="content-service",method="%s",route="%s"`, contract.Method, contract.Path)
	wantRecords := map[string]string{
		"quwoquan_content_contract_operation_requests_total":          fmt.Sprintf(`sum by (status) (http_server_requests_total{%s})`, selector),
		"quwoquan_content_contract_operation_duration_seconds_bucket": fmt.Sprintf(`sum by (le) (http_server_duration_seconds_bucket{%s})`, selector),
	}
	for _, group := range records.Groups {
		for _, rule := range group.Rules {
			if rule.Labels["operation"] != "content.post."+contract.Operation {
				continue
			}
			want, ok := wantRecords[rule.Record]
			if !ok || strings.TrimSpace(rule.Expr) != want {
				t.Fatalf("unexpected GetFeed recording rule: %+v", rule)
			}
			if rule.Labels["slo_latency_p95_ms"] != strconv.Itoa(contract.SLO.LatencyP95MS) ||
				rule.Labels["slo_availability_percent"] != strconv.FormatFloat(contract.SLO.AvailabilityPercent, 'f', -1, 64) ||
				rule.Labels["contract_metric"] != contract.Telemetry.Metric {
				t.Fatalf("GetFeed recording labels drifted from canonical: %v", rule.Labels)
			}
			delete(wantRecords, rule.Record)
		}
	}
	if len(wantRecords) != 0 {
		t.Fatalf("missing GetFeed recording rules: %v", wantRecords)
	}
	assertRecommendationRouteAlertThresholds(t, root, contract)
}

func assertRecommendationRouteAlertThresholds(t *testing.T, root string, contract recommendationRouteOperation) {
	t.Helper()
	var coverage prometheusAlertsFile
	mustLoadYAML(t, filepath.Join(root, "quwoquan_ops/observability/monitoring/alerts/contract_object_coverage.yaml"), &coverage)
	rules := rulesForAlertGroup(coverage, "quwoquan_content_contract_object_coverage")
	availability := strconv.FormatFloat(contract.SLO.AvailabilityPercent, 'f', -1, 64)
	latency := strconv.Itoa(contract.SLO.LatencyP95MS)
	baseSelector := `service="content-service",operation=~"content\\..+",contract_metric=~"content_.+",commercial_status="ready"`
	availabilitySelector := baseSelector + `,slo_availability_percent="` + availability + `"`
	latencySelector := baseSelector + `,slo_latency_p95_ms="` + latency + `"`
	// 保持生成告警原有 10m 可用性、5m 延迟窗口和 clamp_min；不拿路由 5m 观测窗口改写告警。
	budget := math.Round((100-contract.SLO.AvailabilityPercent)/100*1e6) / 1e6
	want := map[string]string{
		"ContentContractOperationAvailabilityBelow" + strings.ReplaceAll(availability, ".", "p") + "Percent": fmt.Sprintf(
			`sum(rate(quwoquan_content_contract_operation_requests_total{%s,status=~"5.."}[10m])) by (operation, contract_metric)
			/ clamp_min(sum(rate(quwoquan_content_contract_operation_requests_total{%s}[10m])) by (operation, contract_metric), 0.001) > %g`,
			availabilitySelector, availabilitySelector, budget),
		"ContentContractOperationLatencyP95Above" + latency + "Ms": fmt.Sprintf(
			`histogram_quantile(0.95, sum(rate(quwoquan_content_contract_operation_duration_seconds_bucket{%s}[5m])) by (le, operation, contract_metric)) > %g`,
			latencySelector, float64(contract.SLO.LatencyP95MS)/1000),
	}
	for name, expr := range want {
		if strings.Join(strings.Fields(rules[name]), "") != strings.Join(strings.Fields(expr), "") {
			t.Errorf("generated alert %s must consume canonical threshold and HTTP denominator:\ngot: %s\nwant: %s", name, rules[name], expr)
		}
	}
}
