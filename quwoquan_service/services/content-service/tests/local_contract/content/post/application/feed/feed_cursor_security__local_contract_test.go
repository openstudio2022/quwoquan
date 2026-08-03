// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package feed_test

import (
	"context"
	"strings"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
)

func TestListFeedCursorIsOpaqueTamperSafeAndRequestBound(t *testing.T) {
	now := time.Now().UTC()
	posts := []postmodel.Post{
		{
			ID: "cursor-security-1", AuthorId: "cursor-author-1",
			ContentType: "image", ContentIdentity: "work",
			Status: "published", Visibility: "public", CreatedAt: now, PublishedAt: now,
		},
		{
			ID: "cursor-security-2", AuthorId: "cursor-author-2",
			ContentType: "image", ContentIdentity: "work",
			Status: "published", Visibility: "public",
			CreatedAt: now.Add(-time.Minute), PublishedAt: now.Add(-time.Minute),
		},
	}
	service := newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{
			{
				ContentID: posts[0].ID, ContentType: "image",
				AuthorID: posts[0].AuthorId, PublishedAt: posts[0].PublishedAt,
			},
			{
				ContentID: posts[1].ID, ContentType: "image",
				AuthorID: posts[1].AuthorId, PublishedAt: posts[1].PublishedAt,
			},
		}),
		fixtureFeedReader{posts: posts},
		readyActiveSupplyOption(),
	)
	request := ListFeedRequest{
		UserID: "cursor-user", ViewerPersonaID: "cursor-persona", SessionID: "cursor-session",
		ChannelID: "following", Limit: 1,
	}
	first, err := service.ListFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("initial feed page: %v", err)
	}
	if !strings.HasPrefix(first.NextCursor, "fc.") {
		t.Fatalf("cursor wire format = %q", first.NextCursor)
	}
	for _, plaintext := range []string{request.UserID, request.SessionID, first.FeedRequestID, posts[0].ID} {
		if strings.Contains(first.NextCursor, plaintext) {
			t.Fatalf("cursor leaked plaintext %q", plaintext)
		}
	}

	tampered := []byte(first.NextCursor)
	index := len(tampered) / 2
	if tampered[index] == 'A' {
		tampered[index] = 'B'
	} else {
		tampered[index] = 'A'
	}
	assertInvalidFeedCursor(t, service, ListFeedRequest{
		UserID: request.UserID, SessionID: request.SessionID,
		ChannelID: request.ChannelID, Limit: request.Limit, Cursor: string(tampered),
	})
	assertInvalidFeedCursor(t, service, ListFeedRequest{
		UserID: request.UserID, SessionID: "another-session",
		ChannelID: request.ChannelID, Limit: request.Limit, Cursor: first.NextCursor,
	})
	assertInvalidFeedCursor(t, service, ListFeedRequest{
		UserID: "another-user", SessionID: request.SessionID,
		ChannelID: request.ChannelID, Limit: request.Limit, Cursor: first.NextCursor,
	})
	assertInvalidFeedCursor(t, service, ListFeedRequest{
		UserID: request.UserID, SessionID: request.SessionID,
		ChannelID: "recommend", Limit: request.Limit, Cursor: first.NextCursor,
	})
	assertInvalidFeedCursor(t, service, ListFeedRequest{
		UserID: request.UserID, SessionID: request.SessionID,
		ChannelID: request.ChannelID, Limit: request.Limit, Cursor: first.NextCursor,
		FeedRequestID: "frq_conflict",
	})
}

func TestListFeedCursorScopeIsInjectiveAcrossFieldBoundaries(t *testing.T) {
	now := time.Now().UTC()
	posts := []postmodel.Post{
		{ID: "cursor-scope-1", AuthorId: "cursor-scope-author-1", ContentType: "image", ContentIdentity: "work", Status: "published", Visibility: "public", CreatedAt: now, PublishedAt: now},
		{ID: "cursor-scope-2", AuthorId: "cursor-scope-author-2", ContentType: "image", ContentIdentity: "work", Status: "published", Visibility: "public", CreatedAt: now.Add(-time.Minute), PublishedAt: now.Add(-time.Minute)},
	}
	service := newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{
			{ContentID: posts[0].ID, ContentType: "image", AuthorID: posts[0].AuthorId, PublishedAt: posts[0].PublishedAt},
			{ContentID: posts[1].ID, ContentType: "image", AuthorID: posts[1].AuthorId, PublishedAt: posts[1].PublishedAt},
		}),
		fixtureFeedReader{posts: posts},
		readyActiveSupplyOption(),
	)
	original := ListFeedRequest{
		UserID: "actor-a", ViewerPersonaID: "persona-a", SessionID: "session-b-session-c",
		ChannelID: "following", Limit: 1,
	}
	first, err := service.ListFeed(context.Background(), original)
	if err != nil || first.NextCursor == "" {
		t.Fatalf("create cursor for injective-scope test: response=%+v err=%v", first, err)
	}

	// 将原 scope 的字段边界重新分配后必须失效；scope 由结构化长度前缀编码，
	// 不能依赖任何可出现在合法 identity 中的分隔符。
	assertInvalidFeedCursor(t, service, ListFeedRequest{
		UserID: "actor-a-session-b", ViewerPersonaID: "persona-a", SessionID: "session-c",
		ChannelID: "following", Limit: 1, Cursor: first.NextCursor,
	})
}

func TestListFeedCursorExpiresAndStopsAtContinuationDepthLimit(t *testing.T) {
	newService := func(t *testing.T, options ...FeedCursorCodecOption) (*FeedService, ListFeedRequest) {
		t.Helper()
		codec, err := NewFeedCursorCodec(
			[]byte(strings.Repeat("cursor-contract-root-", 2)),
			options...,
		)
		if err != nil {
			t.Fatalf("new feed cursor codec: %v", err)
		}
		now := time.Now().UTC()
		posts := []postmodel.Post{
			{
				ID: "cursor-boundary-1", AuthorId: "cursor-boundary-author-1",
				ContentType: "image", ContentIdentity: "work",
				Status: "published", Visibility: "public", CreatedAt: now, PublishedAt: now,
			},
			{
				ID: "cursor-boundary-2", AuthorId: "cursor-boundary-author-2",
				ContentType: "image", ContentIdentity: "work",
				Status: "published", Visibility: "public",
				CreatedAt: now.Add(-time.Minute), PublishedAt: now.Add(-time.Minute),
			},
			{
				ID: "cursor-boundary-3", AuthorId: "cursor-boundary-author-3",
				ContentType: "image", ContentIdentity: "work",
				Status: "published", Visibility: "public",
				CreatedAt: now.Add(-2 * time.Minute), PublishedAt: now.Add(-2 * time.Minute),
			},
		}
		candidates := make([]rtrec.ContentCandidate, 0, len(posts))
		for _, post := range posts {
			candidates = append(candidates, rtrec.ContentCandidate{
				ContentID: post.ID, ContentType: post.ContentType,
				AuthorID: post.AuthorId, PublishedAt: post.PublishedAt,
			})
		}
		return newTerminalFeedService(
				newTerminalFeedEngine(candidates),
				fixtureFeedReader{posts: posts},
				WithFeedCursorCodec(codec),
				readyActiveSupplyOption(),
			), ListFeedRequest{
				UserID: "cursor-boundary-user", ViewerPersonaID: "cursor-boundary-persona", SessionID: "cursor-boundary-session",
				ChannelID: "following", Limit: 1,
			}
	}

	t.Run("expired", func(t *testing.T) {
		cursorNow := time.Now().UTC()
		service, request := newService(t, WithFeedCursorClock(func() time.Time { return cursorNow }))
		first, err := service.ListFeed(context.Background(), request)
		if err != nil {
			t.Fatalf("initial feed page: %v", err)
		}
		cursorNow = cursorNow.Add(rtrec.RankedFeedWindowTTL + time.Second)
		request.Cursor = first.NextCursor
		assertInvalidFeedCursor(t, service, request)
	})

	t.Run("maximum continuation depth", func(t *testing.T) {
		service, request := newService(t, WithFeedCursorDepthLimit(1))
		first, err := service.ListFeed(context.Background(), request)
		if err != nil {
			t.Fatalf("initial feed page: %v", err)
		}
		if first.NextCursor == "" {
			t.Fatal("initial feed page must expose the first continuation")
		}
		request.Cursor = first.NextCursor
		continued, err := service.ListFeed(context.Background(), request)
		if err != nil {
			t.Fatalf("final allowed continuation: %v", err)
		}
		if continued.NextCursor != "" {
			t.Fatalf("continuation depth limit leaked another cursor: %+v", continued)
		}
	})
}

func assertInvalidFeedCursor(t *testing.T, service *FeedService, request ListFeedRequest) {
	t.Helper()
	_, err := service.ListFeed(context.Background(), request)
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.USER.invalid_argument",
		rtrec.FailureStageNone,
	)
}
