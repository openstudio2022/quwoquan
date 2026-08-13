// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/analytics-metric-dictionary/spec.md#req-003
// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/analytics-metric-dictionary/spec.md#gwt-001
//
// 黄金指标计算器合约：L1-L4 卡片的数值、状态与告警绑定必须由
// golden_metric_catalog（generated）唯一口径派生——
//   - event_ratio / unique_session_ratio 由 ES 权威回读计算；
//   - 分母为零显式 unavailable，禁止合成数值；
//   - 扩展字段过滤（publicationStage）超出 summary 门面时显式不可算；
//   - series_rate_ratio 构建 canonical PromQL（CTR 分子 engagement{action=click}）；
//   - 越过 alerting.threshold 为 firing，仅违反 target 为 warning，健康侧 quiet。
package local_contract

import (
	"context"
	"encoding/json"
	"sort"
	"strings"
	"testing"
	"time"

	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	eventpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

// decodeMetricItems 经 canonical JSON 视图读取响应（响应类型不导出，
// wire 形状才是合约面），并把告警状态并联到对应指标行。
func decodeMetricItems(t *testing.T, payload any) map[string]map[string]any {
	t.Helper()
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal metrics payload: %v", err)
	}
	var decoded struct {
		Items  []map[string]any `json:"items"`
		Alerts []map[string]any `json:"alerts"`
	}
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("decode metrics payload: %v", err)
	}
	out := map[string]map[string]any{}
	for _, item := range decoded.Items {
		out[item["metric"].(string)] = item
	}
	for _, alert := range decoded.Alerts {
		metric, _ := alert["metric"].(string)
		if row, exists := out[metric]; exists {
			row["alert"] = alert
		}
	}
	return out
}

func metricIDs(items map[string]map[string]any) []string {
	ids := make([]string, 0, len(items))
	for id := range items {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

// recordingPrometheusReader 记录全部查询并按固定值应答，用于断言
// series_rate_ratio 的 PromQL 形状与阈值分派。
type recordingPrometheusReader struct {
	value   float64
	queries []string
}

func (reader *recordingPrometheusReader) Query(_ context.Context, query string) (float64, error) {
	reader.queries = append(reader.queries, query)
	return reader.value, nil
}

func (reader *recordingPrometheusReader) QueryVector(
	context.Context, string,
) ([]eventapp.PrometheusVectorSample, error) {
	return nil, nil
}

func loginFunnelEvent(t *testing.T, session string, result string, occurredAt time.Time) eventapp.EventRecordInput {
	t.Helper()
	event := validEvent("login_funnel", "event", occurredAt)
	event.SessionID = session
	action := "login_terminal"
	if result == "exposed" {
		action = "login_flow_exposed"
	}
	flowID := "flow-0001"
	step := "terminal"
	event.Action = &action
	event.FlowID = &flowID
	event.Step = &step
	event.Result = &result
	return event
}

func goldenMetricSnapshot(
	t *testing.T,
	store *eventpersistence.MemoryTelemetryStore,
	reader *recordingPrometheusReader,
) map[string]map[string]any {
	t.Helper()
	telemetry := eventapp.NewTelemetryService(store, store)
	metrics := eventapp.NewMetricQueryService(telemetry, reader)
	payload, err := metrics.ListL1L4MetricSnapshots(
		context.Background(),
		eventapp.L1L4MetricsScope{Environment: "alpha"},
	)
	if err != nil {
		t.Fatalf("ListL1L4MetricSnapshots error = %v", err)
	}
	// 经 JSON 视图字段（私有 struct 不可导出）间接读取：用反射不如直接
	// 消费导出的响应形状；这里通过重新序列化为通用 map 断言。
	return decodeMetricItems(t, payload)
}

func TestGoldenLoginSuccessRateFiresBoundAlertBelowThreshold(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	now := time.Now().UTC().Add(-2 * time.Hour)
	events := []eventapp.EventRecordInput{
		loginFunnelEvent(t, "s.YWN0b3ItMQ.1", "exposed", now),
		loginFunnelEvent(t, "s.YWN0b3ItMg.1", "exposed", now),
		loginFunnelEvent(t, "s.YWN0b3ItMw.1", "exposed", now),
		loginFunnelEvent(t, "s.YWN0b3ItNA.1", "exposed", now),
		loginFunnelEvent(t, "s.YWN0b3ItMQ.1", "login_success", now.Add(time.Second)),
		loginFunnelEvent(t, "s.YWN0b3ItMg.1", "login_success", now.Add(time.Second)),
	}
	service := eventapp.NewTelemetryService(store, store)
	if _, err := service.ReportEventBatch(
		context.Background(), digestKey("golden-login-fire"), events,
	); err != nil {
		t.Fatalf("ReportEventBatch error = %v", err)
	}

	items := goldenMetricSnapshot(t, store, &recordingPrometheusReader{value: 99})
	login, exists := items["login_success_rate"]
	if !exists {
		t.Fatalf("login_success_rate must be live: %v", metricIDs(items))
	}
	if login["value"].(float64) != 50 {
		t.Fatalf("login success rate must be 2/4 sessions = 50%%, got %v", login["value"])
	}
	if login["source"] != "telemetry" {
		t.Fatalf("golden event metrics must come from telemetry readback: %v", login["source"])
	}
	alert := login["alert"].(map[string]any)
	if alert["state"] != "firing" || alert["severity"] != "critical" {
		t.Fatalf("value below alerting threshold must fire: %+v", alert)
	}
	if alert["alertId"] != "LoginCompletionRateLow" {
		t.Fatalf("firing alert must reference the bound Prometheus alert: %+v", alert)
	}
}

func TestGoldenRatioZeroDenominatorIsExplicitlyUnavailable(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	items := goldenMetricSnapshot(t, store, &recordingPrometheusReader{value: 99})
	if _, exists := items["login_success_rate"]; exists {
		t.Fatal("zero-denominator golden metric must be unavailable, not synthesized")
	}
	if _, exists := items["journey_completion_rate"]; exists {
		t.Fatal("journey completion without page_open denominator must be unavailable")
	}
}

func TestGoldenExtensionFilterMetricIsExplicitlyNotComputable(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	now := time.Now().UTC().Add(-time.Minute)
	event := validEvent("content_publication", "event", now)
	stage := "published"
	contentType := "article"
	objectState := "published"
	surfaceID := "create"
	result := "success"
	event.PublicationStage = &stage
	event.ContentType = &contentType
	event.ObjectState = &objectState
	event.SurfaceID = &surfaceID
	event.Result = &result
	service := eventapp.NewTelemetryService(store, store)
	if _, err := service.ReportEventBatch(
		context.Background(), digestKey("golden-publish-filter"), []eventapp.EventRecordInput{event},
	); err != nil {
		t.Fatalf("ReportEventBatch error = %v", err)
	}

	items := goldenMetricSnapshot(t, store, &recordingPrometheusReader{value: 99})
	if _, exists := items["content_publish_success_rate"]; exists {
		t.Fatal(
			"publicationStage filter exceeds the summary facade; the realtime card " +
				"must stay unavailable instead of dropping the filter",
		)
	}
}

func TestGoldenSeriesRatioBuildsCanonicalCtrQueryAndQuietAboveTarget(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	reader := &recordingPrometheusReader{value: 6}
	items := goldenMetricSnapshot(t, store, reader)

	ctr, exists := items["feed_click_through_rate"]
	if !exists {
		t.Fatalf("feed CTR must be live via prometheus: %v", metricIDs(items))
	}
	if ctr["value"].(float64) != 6 || ctr["source"] != "prometheus" {
		t.Fatalf("CTR must consume the prometheus ratio: %+v", ctr)
	}
	alert := ctr["alert"].(map[string]any)
	if alert["state"] != "quiet" {
		t.Fatalf("6%% >= 5%% target must stay quiet: %+v", alert)
	}
	wantQuery := `100 * sum(rate(recommendation_feed_engagement_total{action="click"}[5m])) / (sum(rate(recommendation_feed_impressed_total[5m])) + 0.001)`
	found := false
	for _, query := range reader.queries {
		if query == wantQuery {
			found = true
		}
		if strings.Contains(query, "recommendation_feed_click_total") {
			t.Fatalf("CTR numerator must be engagement{action=click}, got %q", query)
		}
	}
	if !found {
		t.Fatalf("canonical CTR query missing from prometheus calls: %v", reader.queries)
	}
}

func TestGoldenSeriesRatioFiresBelowBoundThreshold(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	items := goldenMetricSnapshot(t, store, &recordingPrometheusReader{value: 4})
	ctr, exists := items["feed_click_through_rate"]
	if !exists {
		t.Fatal("feed CTR must be live via prometheus")
	}
	alert := ctr["alert"].(map[string]any)
	if alert["state"] != "firing" || alert["alertId"] != "RecommendationClickThroughRateLow" {
		t.Fatalf("4%% < 5%% alerting threshold must fire the bound alert: %+v", alert)
	}
}

// percentile 形态由 raw 原始样本统计门面承载：20 个 page_first_usable
// durationMs 样本的最近秩 P95 超过 2000ms 目标即 warning（无告警绑定）。
func TestGoldenPercentileMetricComputesFromRawValueStats(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	now := time.Now().UTC().Add(-2 * time.Hour)
	events := make([]eventapp.EventRecordInput, 0, 20)
	for index := 0; index < 20; index++ {
		event := validEvent("page_first_usable", "event", now.Add(time.Duration(index)*time.Second))
		durationMS := 500 + index*200 // 500..4300ms，最近秩 P95 = 4100
		terminalState := "content"
		event.DurationMS = &durationMS
		event.TerminalState = &terminalState
		events = append(events, event)
	}
	service := eventapp.NewTelemetryService(store, store)
	if _, err := service.ReportEventBatch(
		context.Background(), digestKey("golden-percentile"), events,
	); err != nil {
		t.Fatalf("ReportEventBatch error = %v", err)
	}

	items := goldenMetricSnapshot(t, store, &recordingPrometheusReader{value: 99})
	usable, exists := items["page_first_usable_p95_ms"]
	if !exists {
		t.Fatalf("page_first_usable_p95_ms must be live: %v", metricIDs(items))
	}
	if usable["value"].(float64) != 4100 || usable["unit"] != "ms" {
		t.Fatalf("nearest-rank P95 drifted: %+v", usable)
	}
	alert := usable["alert"].(map[string]any)
	if alert["state"] != "warning" {
		t.Fatalf("4100ms > 2000ms target must warn: %+v", alert)
	}
}

// sum_ratio 形态：jankyFrames/sampledFrames 求和比值；6% 超过 5% 的
// 告警绑定阈值（近实时预警口径）即 firing。
func TestGoldenSumRatioMetricFiresAboveBoundThreshold(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	now := time.Now().UTC().Add(-2 * time.Hour)
	events := make([]eventapp.EventRecordInput, 0, 4)
	for index := 0; index < 4; index++ {
		event := validEvent("app_frame_jank_outcome", "event", now.Add(time.Duration(index)*time.Second))
		sampled := 1000
		janky := 60
		worstFrame := 120
		worstBuild := 60
		worstRaster := 60
		threshold := 16
		result := "sampled"
		event.SampledFrames = &sampled
		event.JankyFrames = &janky
		event.WorstFrameMS = &worstFrame
		event.WorstBuildFrameMS = &worstBuild
		event.WorstRasterFrameMS = &worstRaster
		event.JankThresholdMS = &threshold
		event.Result = &result
		events = append(events, event)
	}
	service := eventapp.NewTelemetryService(store, store)
	if _, err := service.ReportEventBatch(
		context.Background(), digestKey("golden-sum-ratio"), events,
	); err != nil {
		t.Fatalf("ReportEventBatch error = %v", err)
	}

	items := goldenMetricSnapshot(t, store, &recordingPrometheusReader{value: 99})
	jank, exists := items["app_jank_frame_rate"]
	if !exists {
		t.Fatalf("app_jank_frame_rate must be live: %v", metricIDs(items))
	}
	if jank["value"].(float64) != 6 {
		t.Fatalf("sum ratio must be 240/4000 = 6%%, got %v", jank["value"])
	}
	alert := jank["alert"].(map[string]any)
	if alert["state"] != "firing" || alert["alertId"] != "AppJankFrameRateHigh" {
		t.Fatalf("6%% > 5%% bound threshold must fire: %+v", alert)
	}
}

func TestGoldenEventRatioWithoutAlertBindingWarnsOnTargetViolation(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	now := time.Now().UTC().Add(-2 * time.Hour)
	events := make([]eventapp.EventRecordInput, 0, 6)
	for index, session := range []string{"s.cGFnZS0x.1", "s.cGFnZS0y.1", "s.cGFnZS0z.1", "s.cGFnZS00.1"} {
		event := validEvent("page_open", "event", now.Add(time.Duration(index)*time.Second))
		event.SessionID = session
		events = append(events, event)
	}
	for index, session := range []string{"s.cGFnZS0x.1", "s.cGFnZS0y.1"} {
		event := validEvent("page_return", "event", now.Add(time.Duration(index+10)*time.Second))
		event.SessionID = session
		durationMS := 1500
		event.DurationMS = &durationMS
		events = append(events, event)
	}
	service := eventapp.NewTelemetryService(store, store)
	if _, err := service.ReportEventBatch(
		context.Background(), digestKey("golden-journey-warn"), events,
	); err != nil {
		t.Fatalf("ReportEventBatch error = %v", err)
	}

	items := goldenMetricSnapshot(t, store, &recordingPrometheusReader{value: 99})
	journey, exists := items["journey_completion_rate"]
	if !exists {
		t.Fatalf("journey completion must be live: %v", metricIDs(items))
	}
	if journey["value"].(float64) != 50 {
		t.Fatalf("journey completion must be 2/4 events = 50%%, got %v", journey["value"])
	}
	alert := journey["alert"].(map[string]any)
	if alert["state"] != "warning" || alert["severity"] != "warning" {
		t.Fatalf("target violation without alert binding must warn, not fire: %+v", alert)
	}
}
