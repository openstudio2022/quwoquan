// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package feed_test

import (
	"context"
	"strings"
	"testing"

	rtrec "quwoquan_service/runtime/recommendation"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
)

func TestNormalizeFeedLimitClampsUntrustedWireValue(t *testing.T) {
	for _, testCase := range []struct {
		name string
		raw  int
		want int
	}{
		{name: "missing", raw: 0, want: feedapp.DefaultFeedPageSize},
		{name: "negative", raw: -1, want: feedapp.DefaultFeedPageSize},
		{name: "minimum", raw: 1, want: 1},
		{name: "maximum", raw: feedapp.MaxFeedPageSize, want: feedapp.MaxFeedPageSize},
		{name: "over maximum", raw: feedapp.MaxFeedPageSize + 10_000, want: feedapp.MaxFeedPageSize},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			if got := feedapp.NormalizeFeedLimit(testCase.raw); got != testCase.want {
				t.Fatalf("NormalizeFeedLimit(%d)=%d want=%d", testCase.raw, got, testCase.want)
			}
		})
	}
}

func TestRecommendationFeedRejectsMissingOrUnboundedSessionID(t *testing.T) {
	service := feedapp.NewFeedService(nil, nil)
	for _, testCase := range []struct {
		name      string
		sessionID string
	}{
		{name: "missing"},
		{name: "whitespace", sessionID: "session with space"},
		{name: "control", sessionID: "session\nnewline"},
		{name: "over maximum", sessionID: strings.Repeat("s", 129)},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			_, err := service.ListFeed(context.Background(), feedapp.ListFeedRequest{
				SessionID: testCase.sessionID,
				ChannelID: "recommend",
				Sort:      rtrec.FeedSortRecommend,
				Limit:     20,
			})
			requireAppErrorCodeAndStage(
				t,
				err,
				"CONTENT.USER.invalid_argument",
				rtrec.FailureStageNone,
			)
		})
	}
}
