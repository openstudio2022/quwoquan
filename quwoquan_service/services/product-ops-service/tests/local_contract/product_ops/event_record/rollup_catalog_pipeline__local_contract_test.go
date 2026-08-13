// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-002
// 契约驱动的 rollup 写侧：rollups.yaml（经 codegen 的 RollupCatalog）是 13 个
// rowKind 的唯一聚合真相源，本文件验证代数族、隐私边界与重放幂等。
package local_contract

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	generated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

func TestRollupExecutorEmitsEveryMatchingRowKindWithContractAlgebra(t *testing.T) {
	t.Parallel()
	harness := newElasticsearchHarness(nil)
	server := httptest.NewServer(harness)
	t.Cleanup(server.Close)
	store := newTestElasticsearchStore(t, server.URL)
	ctx := context.Background()
	now := time.Now().UTC().Add(-2 * time.Minute)
	batchKey := strings.Repeat("1", 64)

	records := make([]application.EventRecord, 0)
	appendRecord := func(input application.EventRecordInput) {
		records = append(records, application.EventRecord{
			EventRecordInput: input,
			BatchKey:         batchKey,
			BatchIndex:       len(records),
			IngestedAt:       now.Add(time.Second),
		})
	}

	// video_qoe：readyMs 直方图、rebuffer 求和、durationMismatch 计数、terminal failure。
	for index := 0; index < 2; index++ {
		ready := 400 + index*4000 // 400ms 与 4400ms 落入不同直方图桶
		rebuffer, rebufferMS, seekCount, seekFailure := index, 100*index, 2, index
		seekCommand, seekSettle := 80, 2500 // settle > 2000ms 尾桶
		effective := 10000
		mismatch := index == 1
		result := "success"
		if index == 1 {
			result = "failure"
		}
		playbackMode, evidence := "autoplay", "controller_command_completion"
		event := validEvent("video_playback_qoe", "event", now)
		event.ReadyMS = &ready
		event.RebufferCount = &rebuffer
		event.RebufferMS = &rebufferMS
		event.EffectivePlaybackMS = &effective
		event.SeekCount = &seekCount
		event.SeekFailureCount = &seekFailure
		event.SeekCommandMaxMS = &seekCommand
		event.SeekSettleMaxMS = &seekSettle
		event.DurationMismatch = &mismatch
		event.Result = &result
		event.PlaybackMode = &playbackMode
		event.SeekEvidenceSource = &evidence
		appendRecord(event)
	}

	// search_funnel：同一 requestId 的提交/曝光/点击 + 独立 requestId 的短驻留（非有效）。
	requestA, requestB := "req-a", "req-b"
	shortDwell, longDwell := 800, 3200
	for _, item := range []struct {
		eventType string
		requestID *string
		duration  *int
	}{
		{"search_query_submit", &requestA, nil},
		{"search_result_impression", &requestA, &shortDwell},
		{"search_result_click", &requestA, nil},
		{"search_query_submit", &requestB, nil},
		{"search_result_dwell", &requestB, &shortDwell},
		{"search_result_dwell", &requestA, &longDwell},
	} {
		event := validEvent(item.eventType, "event", now)
		event.RequestID = item.requestID
		event.DurationMS = item.duration
		action := "search"
		event.Action = &action
		appendRecord(event)
	}

	if err := store.PutEventBatch(ctx, batchKey, records); err != nil {
		t.Fatalf("PutEventBatch() error = %v", err)
	}

	byRowKind := map[string][]map[string]any{}
	for _, document := range harness.documents("app-product-telemetry-hourly") {
		rowKind, _ := document["rowKind"].(string)
		byRowKind[rowKind] = append(byRowKind[rowKind], document)
	}
	// 全部事件都进 event_dimensions；video 与 search 各自命中专属 rowKind。
	for _, expected := range []string{"event_dimensions", "video_qoe", "search_funnel"} {
		if len(byRowKind[expected]) == 0 {
			t.Fatalf("rowKind %s missing; got %v", expected, rowKindNames(byRowKind))
		}
	}
	if len(byRowKind["performance"]) != 0 || len(byRowKind["chat_funnel"]) != 0 {
		t.Fatalf("filters leaked unrelated rowKinds: %v", rowKindNames(byRowKind))
	}

	video := mergeRollupDocuments(byRowKind["video_qoe"])
	if got := rollupNumber(t, video, "readyCount"); got != 2 {
		t.Fatalf("video readyCount = %v; want 2", got)
	}
	if got := rollupNumber(t, video, "rebufferCount"); got != 1 {
		t.Fatalf("video rebufferCount sum = %v; want 1", got)
	}
	if got := rollupNumber(t, video, "durationMismatchCount"); got != 1 {
		t.Fatalf("video durationMismatchCount = %v; want 1", got)
	}
	if got := rollupNumber(t, video, "terminalFailureCount"); got != 1 {
		t.Fatalf("video terminalFailureCount = %v; want 1", got)
	}
	readyHistogram := rollupHistogram(t, video, "readyHistogram")
	if readyHistogram["count"] != float64(2) {
		t.Fatalf("video readyHistogram count = %v; want 2", readyHistogram["count"])
	}
	settleHistogram := rollupHistogram(t, video, "seekSettleHistogram")
	settleCounts := settleHistogram["counts"].([]any)
	tail := settleCounts[len(settleCounts)-2].(float64) + settleCounts[len(settleCounts)-1].(float64)
	if tail != 2 {
		t.Fatalf("video seekSettleHistogram 2500ms samples must land in >2000ms buckets: %v", settleCounts)
	}

	search := mergeRollupDocuments(byRowKind["search_funnel"])
	for field, want := range map[string]int{
		"querySubmitCountHashes":            2, // req-a + req-b
		"nonEmptyResultCountHashes":         1, // 仅 req-a 有曝光
		"effectiveActionRequestCountHashes": 1, // req-a 点击 + 长驻留；req-b 短驻留不计
	} {
		if got := rollupHashCount(search, field); got != want {
			t.Fatalf("search %s cardinality = %d; want %d", field, got, want)
		}
	}
	firstActionable := rollupHistogram(t, search, "firstActionableHistogram")
	if firstActionable["count"] != float64(1) {
		t.Fatalf(
			"firstActionableHistogram must only sample impressions: %v",
			firstActionable["count"],
		)
	}

	// 隐私边界：任何 rowKind 文档不得携带禁出字段或裸 requestId 值。
	for rowKind, documents := range byRowKind {
		for _, document := range documents {
			encoded, _ := json.Marshal(document)
			for _, forbidden := range []string{`"sessionId"`, `"userId"`, `"_batchKey"`, `"callStack"`, requestA} {
				if strings.Contains(string(encoded), forbidden) {
					t.Fatalf("rowKind %s leaked %q: %s", rowKind, forbidden, encoded)
				}
			}
		}
	}

	// 重放幂等：同批重放不得放大任何 rowKind 的文档数。
	before := harness.documentCount("app-product-telemetry-hourly")
	if err := store.PutEventBatch(ctx, batchKey, records); err != nil {
		t.Fatalf("PutEventBatch() replay error = %v", err)
	}
	if after := harness.documentCount("app-product-telemetry-hourly"); after != before {
		t.Fatalf("replay changed rollup documents: %d -> %d", before, after)
	}
}

func TestRollupCatalogCoversThirteenRowKindsAndLateArrivalContract(t *testing.T) {
	t.Parallel()
	if len(generated.RollupCatalog) != 13 {
		t.Fatalf("RollupCatalog jobs = %d; want 13", len(generated.RollupCatalog))
	}
	if generated.RollupLateArrivalWindowHours != 72 {
		t.Fatalf(
			"late arrival window = %d; want 72",
			generated.RollupLateArrivalWindowHours,
		)
	}
	sources := map[string]string{}
	for _, job := range generated.RollupCatalog {
		sources[job.RowKind] = job.Source
	}
	if sources["runtime_diagnostics"] != "runtime_records" {
		t.Fatalf("runtime_diagnostics source = %q; want runtime_records", sources["runtime_diagnostics"])
	}
	for rowKind, source := range sources {
		if rowKind != "runtime_diagnostics" && source != "raw_records" {
			t.Fatalf("rowKind %s source = %q; want raw_records", rowKind, source)
		}
	}
}

func rowKindNames(byRowKind map[string][]map[string]any) []string {
	names := make([]string, 0, len(byRowKind))
	for name := range byRowKind {
		names = append(names, fmt.Sprintf("%s(%d)", name, len(byRowKind[name])))
	}
	return names
}

// mergeRollupDocuments 把同 rowKind 的多个维度组文档按读侧语义合并，
// 便于对代数总量断言（数值求和、hash 并集、直方图桶相加）。
func mergeRollupDocuments(documents []map[string]any) map[string]any {
	merged := map[string]any{}
	for _, document := range documents {
		for key, value := range document {
			switch typed := value.(type) {
			case float64:
				current, _ := merged[key].(float64)
				merged[key] = current + typed
			case []any:
				if isHashList(typed) {
					existing, _ := merged[key].([]any)
					merged[key] = appendDistinct(existing, typed)
					continue
				}
				merged[key] = value
			case map[string]any:
				merged[key] = mergeHistogramValue(merged[key], typed)
			default:
				merged[key] = value
			}
		}
	}
	return merged
}

func isHashList(values []any) bool {
	for _, value := range values {
		if _, ok := value.(string); !ok {
			return false
		}
	}
	return true
}

func appendDistinct(existing []any, incoming []any) []any {
	seen := map[string]bool{}
	out := make([]any, 0, len(existing)+len(incoming))
	for _, value := range append(existing, incoming...) {
		text := value.(string)
		if seen[text] {
			continue
		}
		seen[text] = true
		out = append(out, value)
	}
	return out
}

func mergeHistogramValue(existing any, incoming map[string]any) map[string]any {
	current, ok := existing.(map[string]any)
	if !ok {
		return incoming
	}
	currentCounts, _ := current["counts"].([]any)
	incomingCounts, _ := incoming["counts"].([]any)
	if len(currentCounts) != len(incomingCounts) {
		return incoming
	}
	mergedCounts := make([]any, len(currentCounts))
	for index := range currentCounts {
		mergedCounts[index] = currentCounts[index].(float64) + incomingCounts[index].(float64)
	}
	return map[string]any{
		"bucketsMs": incoming["bucketsMs"],
		"counts":    mergedCounts,
		"sum":       current["sum"].(float64) + incoming["sum"].(float64),
		"count":     current["count"].(float64) + incoming["count"].(float64),
	}
}

func rollupNumber(t *testing.T, document map[string]any, field string) float64 {
	t.Helper()
	value, ok := document[field].(float64)
	if !ok {
		t.Fatalf("rollup field %s is not numeric: %#v", field, document[field])
	}
	return value
}

func rollupHistogram(t *testing.T, document map[string]any, field string) map[string]any {
	t.Helper()
	value, ok := document[field].(map[string]any)
	if !ok {
		t.Fatalf("rollup field %s is not a histogram: %#v", field, document[field])
	}
	return value
}

func rollupHashCount(document map[string]any, field string) int {
	values, _ := document[field].([]any)
	return len(values)
}
