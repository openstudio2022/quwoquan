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

func emptyListFeedResponse(
	feedRequestID string,
	reason FeedEmptyReason,
) *ListFeedResponse {
	return &ListFeedResponse{
		Items:         []FeedItemView{},
		ObjectCards:   []ObjectCardView{},
		FeedRequestID: feedRequestID,
		Outcome:       FeedResponseOutcomeEmpty,
		EmptyReason:   reason,
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
