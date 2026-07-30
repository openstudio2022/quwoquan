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
	FailureStageNone                          FailureStage = "none"
	FailureStageRecallAllFailed               FailureStage = "recall_all_failed"
	FailureStageRecallPartialFailed           FailureStage = "recall_partial_failed"
	FailureStageRecallPartialFailedEmpty      FailureStage = "recall_partial_failed_empty"
	FailureStageRecallEmptyOutput             FailureStage = "recall_empty_output"
	FailureStageScorerUnavailable             FailureStage = "scorer_unavailable"
	FailureStageScorerEmptyOutput             FailureStage = "scorer_empty_output"
	FailureStageActiveSupplyMissing           FailureStage = "active_supply_missing"
	FailureStageHardExclusionStateUnavailable FailureStage = "hard_exclusion_state_unavailable"
	FailureStagePersonalizationUnavailable    FailureStage = "personalization_unavailable"
	FailureStageExposureMemoryUnavailable     FailureStage = "exposure_memory_unavailable"
	FailureStageRankedWindowUnavailable       FailureStage = "ranked_window_unavailable"
	FailureStageDeliveryPageUnavailable       FailureStage = "delivery_page_unavailable"
	FailureStageHydrationFullMiss             FailureStage = "hydration_full_miss"
	FailureStageExposureExhausted             FailureStage = "exposure_exhausted"
)

type FeedTerminalOutcome string

const (
	FeedTerminalSuccess  FeedTerminalOutcome = "success"
	FeedTerminalDegraded FeedTerminalOutcome = "degraded"
	FeedTerminalEmpty    FeedTerminalOutcome = "empty"
	FeedTerminalFailure  FeedTerminalOutcome = "failure"
)

// FeedTerminalEmptyReason mirrors the content feed wire contract as a bounded
// observability label. It is intentionally not a public response DTO: the
// owning content-service remains responsible for the HTTP envelope.
type FeedTerminalEmptyReason string

const (
	FeedTerminalEmptyReasonNone              FeedTerminalEmptyReason = "none"
	FeedTerminalEmptyReasonNoActiveRelease   FeedTerminalEmptyReason = "no_active_release"
	FeedTerminalEmptyReasonNoEligibleContent FeedTerminalEmptyReason = "no_eligible_content"
	FeedTerminalEmptyReasonFollowingEmpty    FeedTerminalEmptyReason = "following_empty"
	FeedTerminalEmptyReasonContinuationEnd   FeedTerminalEmptyReason = "continuation_end"
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
	switch FailureStage(strings.TrimSpace(string(stage))) {
	case FailureStageNone,
		FailureStageRecallAllFailed,
		FailureStageRecallPartialFailed,
		FailureStageRecallPartialFailedEmpty,
		FailureStageRecallEmptyOutput,
		FailureStageScorerUnavailable,
		FailureStageScorerEmptyOutput,
		FailureStageActiveSupplyMissing,
		FailureStageHardExclusionStateUnavailable,
		FailureStagePersonalizationUnavailable,
		FailureStageExposureMemoryUnavailable,
		FailureStageRankedWindowUnavailable,
		FailureStageDeliveryPageUnavailable,
		FailureStageHydrationFullMiss,
		FailureStageExposureExhausted:
		return FailureStage(strings.TrimSpace(string(stage)))
	default:
		return FailureStageNone
	}
}

func normalizeFeedTerminalEmptyReason(reason FeedTerminalEmptyReason) FeedTerminalEmptyReason {
	switch FeedTerminalEmptyReason(strings.TrimSpace(string(reason))) {
	case FeedTerminalEmptyReasonNone,
		FeedTerminalEmptyReasonNoActiveRelease,
		FeedTerminalEmptyReasonNoEligibleContent,
		FeedTerminalEmptyReasonFollowingEmpty,
		FeedTerminalEmptyReasonContinuationEnd:
		return FeedTerminalEmptyReason(strings.TrimSpace(string(reason)))
	default:
		return FeedTerminalEmptyReasonNone
	}
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
