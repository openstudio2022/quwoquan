// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// 契约 runtime_entrypoints[].telemetry.metric 的行为绑定：投影 apply 的
// 成功与失败必须以契约声明的指标名按 outcome 计数（消费面是
// qwq-l3-projection-facts 看板与 ObjectProjectionApplyFailures 告警）。
package local_contract

import (
	"context"
	"errors"
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"

	viewevents "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/adapters/inbound/events"
	viewapp "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/application"
)

type failingSnapshots struct{}

func (failingSnapshots) LoadSearchItem(context.Context, string) (viewapp.SearchItem, bool, error) {
	return viewapp.SearchItem{}, false, errors.New("snapshot source unavailable")
}

func entrypointOutcomeValue(t *testing.T, metric string, outcome string) float64 {
	t.Helper()
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("gather default registry: %v", err)
	}
	for _, family := range families {
		if family.GetName() != metric {
			continue
		}
		for _, sample := range family.GetMetric() {
			for _, label := range sample.GetLabel() {
				if label.GetName() == "outcome" && label.GetValue() == outcome {
					return sample.GetCounter().GetValue()
				}
			}
		}
	}
	return 0
}

var _ = dto.MetricFamily{}

func TestProjectionApplyCountsContractMetricByOutcome(t *testing.T) {
	const metric = "circle_search_item_projection"
	ctx := context.Background()

	index := &recordingIndex{}
	projector := viewapp.NewProjector(index)

	// 成功路径：ok 计数增长。
	okBefore := entrypointOutcomeValue(t, metric, "ok")
	healthySink := viewevents.NewSink(projector, searchSnapshots{
		item:    viewapp.SearchItem{CircleID: "circle-1", DisplayName: "Circle", SourceVersion: 1},
		visible: true,
	})
	if err := healthySink.Apply(ctx, viewapp.LifecycleEvent{
		Type: "CircleCreated", CircleID: "circle-1", SourceVersion: 1,
	}); err != nil {
		t.Fatalf("healthy Apply() error = %v", err)
	}
	if got := entrypointOutcomeValue(t, metric, "ok"); got != okBefore+1 {
		t.Fatalf("ok outcome counter = %v; want %v", got, okBefore+1)
	}

	// 失败路径：error 计数增长，契约告警才有真实数据面。
	errorBefore := entrypointOutcomeValue(t, metric, "error")
	failingSink := viewevents.NewSink(projector, failingSnapshots{})
	if err := failingSink.Apply(ctx, viewapp.LifecycleEvent{
		Type: "CircleCreated", CircleID: "circle-2", SourceVersion: 1,
	}); err == nil {
		t.Fatal("failing Apply() must surface the snapshot error")
	}
	if got := entrypointOutcomeValue(t, metric, "error"); got != errorBefore+1 {
		t.Fatalf("error outcome counter = %v; want %v", got, errorBefore+1)
	}
}
