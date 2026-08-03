// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package feed_test

import (
	"context"
	"fmt"
	"testing"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	testsupport "quwoquan_service/services/content-service/tests/support"
)

func TestAnonymousFeedSessionsDoNotEvictEachOthersRankedWindows(t *testing.T) {
	const candidateCount = 24
	candidates := make([]rtrec.ContentCandidate, 0, candidateCount)
	posts := make([]postmodel.Post, 0, candidateCount)
	for index := 0; index < candidateCount; index++ {
		postID := fmt.Sprintf("anonymous-window-post-%02d", index)
		authorID := fmt.Sprintf("anonymous-window-author-%02d", index)
		candidates = append(candidates, rtrec.ContentCandidate{
			ContentID: postID, ContentType: "image", AuthorID: authorID,
		})
		posts = append(posts, postmodel.Post{
			ID: postID, ContentType: "image", AuthorId: authorID,
			Status: "published", Visibility: "public",
		})
	}
	engine := newTerminalFeedEngine(candidates)
	service := NewFeedService(
		fixtureFeedReader{posts: posts},
		testsupport.RankedRecommendationOptions(
			engine,
			readyActiveSupplyOption(),
		)...,
	)

	var firstSessionCursor string
	for sequence := 0; sequence < rtrec.RankedFeedWindowMaxActivePerSubject; sequence++ {
		response, err := service.ListFeed(context.Background(), ListFeedRequest{
			SessionID: "anonymous-session-a",
			ChannelID: "recommend",
			Sort:      rtrec.FeedSortRecommend,
			Limit:     1,
		})
		if err != nil || response.NextCursor == "" {
			t.Fatalf("create anonymous session A window %d: response=%+v err=%v", sequence+1, response, err)
		}
		if sequence == 0 {
			firstSessionCursor = response.NextCursor
		}
	}

	second, err := service.ListFeed(context.Background(), ListFeedRequest{
		SessionID: "anonymous-session-b",
		ChannelID: "recommend",
		Sort:      rtrec.FeedSortRecommend,
		Limit:     1,
	})
	if err != nil || second.NextCursor == "" {
		t.Fatalf("create anonymous session B window: response=%+v err=%v", second, err)
	}

	continued, err := service.ListFeed(context.Background(), ListFeedRequest{
		SessionID: "anonymous-session-a",
		ChannelID: "recommend",
		Sort:      rtrec.FeedSortRecommend,
		Cursor:    firstSessionCursor,
		Limit:     1,
	})
	if err != nil || len(continued.Items) != 1 {
		t.Fatalf("session B evicted session A's valid continuation: response=%+v err=%v", continued, err)
	}
}
