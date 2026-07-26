package recommendation

// N1-2 契约：二期新能力（objectCards/edge/embedding/gate/shadow/per-source
// 召回失败/Redis 降级/policy reload）的观测挂点存在且可安全调用。
// 历史断裂：这些能力零指标，provider 静默吞错、edge 表 TTL 清空无人知。

import (
	"errors"
	"testing"
)

func TestNewCapabilityMetricRecordersAreSafe(t *testing.T) {
	// 全部 Record 函数必须可在任意输入下安全调用（含空值），不 panic。
	RecordObjectCardsAssembled(0)
	RecordObjectCardsAssembled(3)
	RecordObjectCardsProviderError()

	RecordEdgeMaterializerRun("", nil)
	RecordEdgeMaterializerRun("all", errors.New("boom"))

	RecordEmbeddingProjection("")
	RecordEmbeddingProjection("success")
	RecordEmbeddingProjection("budget_exhausted")

	RecordFeedGateFiltered("", 1)
	RecordFeedGateFiltered("follow_feed", 0)
	RecordFeedGateFiltered("premium_stream", 2)

	RecordShadowScore("attempted")
	RecordShadowScore("succeeded")
	RecordShadowScore("failed")

	RecordRecallSourceFailure("")
	RecordRecallSourceFailure("TagRecallSource")

	RecordRedisDegraded("")
	RecordRedisDegraded("session_state")
	RecordRedisDegraded("exposure_filter")

	RecordPolicyReload("", errors.New("rejected"))
	RecordPolicyReload("v2026.07.20", nil)
}

func TestRecallSourceLabelIsLowCardinality(t *testing.T) {
	if got := recallSourceLabel(nil); got != "unknown" {
		t.Fatalf("nil source label want unknown, got %q", got)
	}
	if got := recallSourceLabel(&mockCandidateSource{}); got != "mockCandidateSource" {
		t.Fatalf("source label must strip package/pointer prefix, got %q", got)
	}
}
