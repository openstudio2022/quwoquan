package feed

type FeedResponseOutcome string

const (
	FeedResponseOutcomeContent FeedResponseOutcome = "content"
	FeedResponseOutcomeEmpty   FeedResponseOutcome = "empty"
)

type FeedEmptyReason string

const (
	FeedEmptyReasonNone              FeedEmptyReason = ""
	FeedEmptyReasonNoActiveRelease   FeedEmptyReason = "no_active_release"
	FeedEmptyReasonNoEligibleContent FeedEmptyReason = "no_eligible_content"
	FeedEmptyReasonFollowingEmpty    FeedEmptyReason = "following_empty"
	FeedEmptyReasonContinuationEnd   FeedEmptyReason = "continuation_end"
)

// emptyListFeedResponse 组装合法空页。releaseID/manifestDigest 是内容激活身份：
// no_active_release 必须同时缺席，no_eligible_content 等 release-bound 空页
// 必须携带完整身份，调用方传入当前 active supply 的两元组。
func emptyListFeedResponse(
	feedRequestID string,
	reason FeedEmptyReason,
	releaseID string,
	manifestDigest string,
) *ListFeedResponse {
	if reason == FeedEmptyReasonNoActiveRelease {
		releaseID = ""
		manifestDigest = ""
	}
	return &ListFeedResponse{
		Items:          []FeedItemView{},
		ObjectCards:    []ObjectCardView{},
		FeedRequestID:  feedRequestID,
		Outcome:        FeedResponseOutcomeEmpty,
		EmptyReason:    reason,
		ReleaseID:      releaseID,
		ManifestDigest: manifestDigest,
	}
}

func classifyFeedResponse(
	itemCount int,
	requestedCursor string,
	following bool,
) (FeedResponseOutcome, FeedEmptyReason) {
	if itemCount > 0 {
		return FeedResponseOutcomeContent, FeedEmptyReasonNone
	}
	if requestedCursor != "" {
		return FeedResponseOutcomeEmpty, FeedEmptyReasonContinuationEnd
	}
	if following {
		return FeedResponseOutcomeEmpty, FeedEmptyReasonFollowingEmpty
	}
	return FeedResponseOutcomeEmpty, FeedEmptyReasonNoEligibleContent
}

func feedOutcomeForItemCount(itemCount int) FeedResponseOutcome {
	if itemCount > 0 {
		return FeedResponseOutcomeContent
	}
	return FeedResponseOutcomeEmpty
}

func feedEmptyReasonForContinuation(itemCount int) FeedEmptyReason {
	if itemCount > 0 {
		return FeedEmptyReasonNone
	}
	return FeedEmptyReasonContinuationEnd
}
