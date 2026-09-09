// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-032
// 历史类别不能进入 active 读面，不能靠身份标志恢复旧轨。
package feed_test

import (
	"context"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type releaseGateFeedReader struct {
	posts []postports.PostFeedItemSlice
	calls int
}

func (reader *releaseGateFeedReader) FindPublishedFeedPost(_ context.Context, id postports.PostID) (postports.PostFeedItemSlice, bool, error) {
	reader.calls++
	for _, post := range reader.posts {
		if post.PostID == id {
			return post, true, nil
		}
	}
	return postports.PostFeedItemSlice{}, false, nil
}
func (reader *releaseGateFeedReader) FindPublishedFeedPosts(ctx context.Context, request postports.PostFeedHydrationRequest) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	result := map[postports.PostID]postports.PostFeedItemSlice{}
	for _, id := range request.PostIDs() {
		post, found, _ := reader.FindPublishedFeedPost(ctx, id)
		if found {
			result[id] = post
		}
	}
	return result, nil
}
func (reader *releaseGateFeedReader) ListPublishedFeedPosts(context.Context, postports.PostFeedReadRequest) (postports.PostFeedSlice, error) {
	reader.calls++
	return postports.PostFeedSlice{Items: append([]postports.PostFeedItemSlice(nil), reader.posts...)}, nil
}

func productionGateService(active *terminalActiveSupplyReader) (*FeedService, *releaseGateFeedReader) {
	now := time.Date(2026, 9, 9, 0, 0, 0, 0, time.UTC)
	reader := &releaseGateFeedReader{}
	var candidates []rtrec.ContentCandidate
	for _, id := range []string{"post-first", "post-second"} {
		candidates = append(candidates, rtrec.ContentCandidate{ContentID: id, ContentType: "image", AuthorID: "author", PublishedAt: now, SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: "rel_local_contract", ManifestDigest: terminalManifestDigest, LifecycleStatus: "active"})
		reader.posts = append(reader.posts, postports.PostFeedItemSlice{PostID: postports.NewPostID(id), AuthorPersonaID: "author", ContentType: "image", ContentIdentity: "work", Visibility: "public", CreatedAt: now, SourceOwner: "qwq_data", ReleaseID: "rel_local_contract", ManifestDigest: terminalManifestDigest, LifecycleStatus: "active"})
		now = now.Add(-time.Minute)
	}
	return newTerminalFeedService(newTerminalFeedEngine(candidates), reader, WithActiveSupplyReader(active), feedDeliveryPageStoreOption()), reader
}

func TestFeedRejectsRetiredReleaseBeforeAnyContentReader(t *testing.T) {
	for _, releaseClass := range []string{"research", "commercial"} {
		for name, request := range map[string]ListFeedRequest{
			"anonymous":     {UserID: "anon", SessionID: "session", ChannelID: "recommend", Limit: 10},
			"authenticated": {UserID: "member", ViewerPersonaID: "persona", SessionID: "session", ChannelID: "recommend", Limit: 10},
			"named browse":  {UserID: "anon", SessionID: "session", Identity: "work", Sort: "recommend", Limit: 10},
			"video book":    {UserID: "anon", SessionID: "session", Identity: "work", Type: "video", Sort: "recommend", Limit: 10},
			"premium":       {UserID: "anon", SessionID: "session", ChannelID: "premium", Limit: 10},
			"following":     {UserID: "member", ViewerPersonaID: "persona", SessionID: "session", ChannelID: "following", Limit: 10},
		} {
			t.Run(releaseClass+"/"+name, func(t *testing.T) {
				active := &terminalActiveSupplyReader{active: true, releaseClass: releaseClass}
				service, reader := productionGateService(active)
				response, err := service.ListFeed(context.Background(), request)
				if err == nil || response != nil || reader.calls != 0 || active.calls != 1 {
					t.Fatalf("retired release reached read path: response=%+v err=%v calls=%d active=%d", response, err, reader.calls, active.calls)
				}
			})
		}
	}
}

func TestFeedProductionPaginationRejectsRetiredPointerBeforeReplay(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true, releaseClass: "production"}
	service, reader := productionGateService(active)
	request := ListFeedRequest{UserID: "member", ViewerPersonaID: "persona", SessionID: "session", ChannelID: "following", Limit: 1}
	first, err := service.ListFeed(context.Background(), request)
	if err != nil || first.NextCursor == "" {
		t.Fatalf("production first page=%+v err=%v", first, err)
	}
	calls := reader.calls
	active.releaseClass = "research"
	request.Cursor, request.FeedRequestID = first.NextCursor, first.FeedRequestID
	response, err := service.ListFeed(context.Background(), request)
	if err == nil || response != nil || reader.calls != calls || active.calls != 2 {
		t.Fatalf("retired pointer replayed old page: response=%+v err=%v", response, err)
	}
}

func TestFeedProductionRemainsPublic(t *testing.T) {
	service, _ := productionGateService(&terminalActiveSupplyReader{active: true, releaseClass: "production"})
	response, err := service.ListFeed(context.Background(), ListFeedRequest{UserID: "anon", SessionID: "session", ChannelID: "recommend", Limit: 10})
	if err != nil || len(response.Items) != 2 {
		t.Fatalf("production feed=%+v err=%v", response, err)
	}
}
