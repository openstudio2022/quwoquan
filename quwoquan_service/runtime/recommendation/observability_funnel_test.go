package recommendation

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

// TestNormalizeFeedbackState_ClickIsDistinct 守护七态漏斗：click 是独立态，
// 与 impressed / interaction 分离（CTR = click / impressed 才能正确计算）。
func TestNormalizeFeedbackState_ClickIsDistinct(t *testing.T) {
	cases := map[string]string{
		"impression": "impressed",
		"click":      "click",
		"dwell":      "dwell",
		"like":       "interaction",
		"comment":    "interaction",
		"share":      "interaction",
		"follow":     "interaction",
		"dislike":    "negative",
		"report":     "negative",
	}
	for action, want := range cases {
		if got := normalizeFeedbackState(BehaviorSignal{Action: action}); got != want {
			t.Errorf("normalizeFeedbackState(action=%q) = %q, want %q", action, got, want)
		}
	}
	// 端侧显式上报的 state 优先于 action 派生。
	if got := normalizeFeedbackState(BehaviorSignal{Action: "click", State: "visible"}); got != "visible" {
		t.Errorf("explicit state must win: got %q, want visible", got)
	}
}

// TestRecordBehaviorIngest_ClickFunnel 验证 click 既计独立 click 态又作为 CTR 分子
// 进 engagement{action=click}，且不混入 interaction 态。
func TestRecordBehaviorIngest_ClickFunnel(t *testing.T) {
	clickBefore := testutil.ToFloat64(feedClickTotal)
	engClickBefore := testutil.ToFloat64(feedEngagementTotal.WithLabelValues("click"))
	interactionBefore := testutil.ToFloat64(feedInteractionTotal)

	RecordBehaviorIngest(BehaviorSignal{Action: "click", ContentID: "c1"})

	if got := testutil.ToFloat64(feedClickTotal) - clickBefore; got != 1 {
		t.Errorf("feedClickTotal delta = %v, want 1", got)
	}
	if got := testutil.ToFloat64(feedEngagementTotal.WithLabelValues("click")) - engClickBefore; got != 1 {
		t.Errorf("feedEngagementTotal{click} delta = %v, want 1", got)
	}
	if got := testutil.ToFloat64(feedInteractionTotal) - interactionBefore; got != 0 {
		t.Errorf("click must not increment interaction: delta = %v, want 0", got)
	}
}

// TestRecordBehaviorIngest_Completion 验证完成事件阈值：content_depth L3+ 或
// play_progress >=90% 计入完成率分子，未达阈值不计。
func TestRecordBehaviorIngest_Completion(t *testing.T) {
	base := testutil.ToFloat64(feedCompletionTotal)

	RecordBehaviorIngest(BehaviorSignal{Action: "content_depth", EngagementDepth: 3, ContentID: "c1"})
	if got := testutil.ToFloat64(feedCompletionTotal) - base; got != 1 {
		t.Fatalf("content_depth L3 should count completion: delta = %v, want 1", got)
	}

	RecordBehaviorIngest(BehaviorSignal{Action: "play_progress", ConsumedRatio: 0.95, ContentID: "c2"})
	if got := testutil.ToFloat64(feedCompletionTotal) - base; got != 2 {
		t.Fatalf("play_progress 95%% should count completion: delta = %v, want 2", got)
	}

	RecordBehaviorIngest(BehaviorSignal{Action: "content_depth", EngagementDepth: 2, ContentID: "c3"})
	if got := testutil.ToFloat64(feedCompletionTotal) - base; got != 2 {
		t.Fatalf("content_depth L2 below threshold must not count: delta = %v, want 2", got)
	}
}

// TestRecordDuplicateExposureFiltered 验证重复曝光拦截度量按 served/impressed 拆分，
// 且 n<=0 不写入（避免噪声）。
func TestRecordDuplicateExposureFiltered(t *testing.T) {
	servedBefore := testutil.ToFloat64(feedDuplicateExposureFiltered.WithLabelValues("served"))
	impressedBefore := testutil.ToFloat64(feedDuplicateExposureFiltered.WithLabelValues("impressed"))

	RecordDuplicateExposureFiltered("served", 3)
	RecordDuplicateExposureFiltered("impressed", 2)
	RecordDuplicateExposureFiltered("served", 0)
	RecordDuplicateExposureFiltered("impressed", -1)

	if got := testutil.ToFloat64(feedDuplicateExposureFiltered.WithLabelValues("served")) - servedBefore; got != 3 {
		t.Errorf("served dup delta = %v, want 3", got)
	}
	if got := testutil.ToFloat64(feedDuplicateExposureFiltered.WithLabelValues("impressed")) - impressedBefore; got != 2 {
		t.Errorf("impressed dup delta = %v, want 2", got)
	}
}
