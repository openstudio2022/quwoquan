package recommendation

import (
	"errors"
	"fmt"
	"strings"
)

// FailureStage 是推荐终态的低基数内部分类。公开 HTTP 错误仍由所属服务
// contracts 中的 canonical error code 决定，禁止把这些值扩散为新错误码。
type FailureStage string

const (
	FailureStageNone                     FailureStage = "none"
	FailureStageRecallAllFailed          FailureStage = "recall_all_failed"
	FailureStageRecallPartialFailed      FailureStage = "recall_partial_failed"
	FailureStageRecallPartialFailedEmpty FailureStage = "recall_partial_failed_empty"
	FailureStageRecallEmptyOutput        FailureStage = "recall_empty_output"
	FailureStageScorerUnavailable        FailureStage = "scorer_unavailable"
	FailureStageScorerEmptyOutput        FailureStage = "scorer_empty_output"
	FailureStageActiveSupplyMissing      FailureStage = "active_supply_missing"
	FailureStageHydrationFullMiss        FailureStage = "hydration_full_miss"
	FailureStageExposureExhausted        FailureStage = "exposure_exhausted"
)

type FeedTerminalOutcome string

const (
	FeedTerminalSuccess  FeedTerminalOutcome = "success"
	FeedTerminalDegraded FeedTerminalOutcome = "degraded"
	FeedTerminalEmpty    FeedTerminalOutcome = "empty"
	FeedTerminalFailure  FeedTerminalOutcome = "failure"
)

type FeedRequestClass string

const (
	FeedRequestClassInitialRecommend FeedRequestClass = "initial_recommend"
	FeedRequestClassContinuation     FeedRequestClass = "continuation"
	FeedRequestClassFollowing        FeedRequestClass = "following"
	FeedRequestClassBrowse           FeedRequestClass = "browse"
)

// FeedFailure keeps recommendation failures typed inside the service boundary.
// The application layer maps it to CONTENT.SYSTEM.required_dependency_unavailable.
type FeedFailure struct {
	Stage FailureStage
	Cause error
}

func NewFeedFailure(stage FailureStage, cause error) *FeedFailure {
	return &FeedFailure{Stage: normalizeFailureStage(stage), Cause: cause}
}

func (f *FeedFailure) Error() string {
	if f == nil {
		return ""
	}
	if f.Cause == nil {
		return string(f.Stage)
	}
	return fmt.Sprintf("%s: %v", f.Stage, f.Cause)
}

func (f *FeedFailure) Unwrap() error {
	if f == nil {
		return nil
	}
	return f.Cause
}

func FailureStageOf(err error) FailureStage {
	var failure *FeedFailure
	if errors.As(err, &failure) {
		return normalizeFailureStage(failure.Stage)
	}
	return FailureStageNone
}

func normalizeFailureStage(stage FailureStage) FailureStage {
	if strings.TrimSpace(string(stage)) == "" {
		return FailureStageNone
	}
	return stage
}

// RecallSkipped 表示召回源在当前 feed/surface 上不适用，不等同于成功空结果。
type RecallSkipped struct {
	Reason string
}

func SkipRecall(reason string) error {
	return &RecallSkipped{Reason: strings.TrimSpace(reason)}
}

func (e *RecallSkipped) Error() string {
	if e == nil || e.Reason == "" {
		return "recall source is not applicable"
	}
	return "recall source is not applicable: " + e.Reason
}

func IsRecallSkipped(err error) bool {
	var skipped *RecallSkipped
	return errors.As(err, &skipped)
}
