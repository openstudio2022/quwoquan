// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-032
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020
//
// DEC-032 匿名内容面收敛：active release 为 research 时，release 承载内容
// 的读面只对 research principal 在场；匿名与非 research 认证请求在内容
// query owner 单点收敛为 no_active_release 语义的缺席结果，且不回显
// releaseId/manifestDigest。commercial release 不受 research 标志影响。
package feed_test

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func researchSupplyService(reader *terminalActiveSupplyReader) *FeedService {
	now := time.Now().UTC()
	candidate := rtrec.ContentCandidate{
		ContentID: "post-research", ContentType: "image", AuthorID: "author-research",
		SupplySource: "data_engineering", SourceOwner: "qwq_data",
		ReleaseID: "rel_local_contract", ManifestDigest: terminalManifestDigest,
		LifecycleStatus: "active", PublishedAt: now,
	}
	post := postports.PostFeedItemSlice{
		PostID:          postports.NewPostID(candidate.ContentID),
		AuthorPersonaID: postports.NewPersonaID(candidate.AuthorID),
		ContentType:     "image", ContentIdentity: "work", Visibility: "public",
		CreatedAt: now, SourceOwner: "qwq_data", ReleaseID: "rel_local_contract",
		ManifestDigest: terminalManifestDigest, LifecycleStatus: "active",
	}
	return newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{candidate}),
		releaseHydrationFeedReader{post: post},
		WithActiveSupplyReader(reader),
		feedDeliveryPageStoreOption(),
	)
}

type multiResearchFeedReader struct {
	posts []postports.PostFeedItemSlice
}

func (reader multiResearchFeedReader) FindPublishedFeedPost(
	_ context.Context,
	postID postports.PostID,
) (postports.PostFeedItemSlice, bool, error) {
	for _, post := range reader.posts {
		if post.PostID == postID {
			return post, true, nil
		}
	}
	return postports.PostFeedItemSlice{}, false, nil
}

func (reader multiResearchFeedReader) FindPublishedFeedPosts(
	ctx context.Context,
	request postports.PostFeedHydrationRequest,
) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	result := make(map[postports.PostID]postports.PostFeedItemSlice)
	for _, postID := range request.PostIDs() {
		post, found, err := reader.FindPublishedFeedPost(ctx, postID)
		if err != nil {
			return nil, err
		}
		if found {
			result[postID] = post
		}
	}
	return result, nil
}

func (reader multiResearchFeedReader) ListPublishedFeedPosts(
	context.Context,
	postports.PostFeedReadRequest,
) (postports.PostFeedSlice, error) {
	return postports.PostFeedSlice{Items: append([]postports.PostFeedItemSlice(nil), reader.posts...)}, nil
}

func TestListFeedResearchReleaseConvergesForNonResearchPrincipal(t *testing.T) {
	for name, request := range map[string]ListFeedRequest{
		"anonymous initial": {
			UserID: "u-anon", SessionID: "s-anon", ChannelID: "recommend", Limit: 10,
		},
		"authenticated non-research": {
			UserID: "u-member", ViewerPersonaID: "persona-member",
			SessionID: "s-member", ChannelID: "recommend", Limit: 10,
		},
		// strict preflight 抓到的真实泄露路径：identity=work（无 type）走
		// PostReader 具名浏览时间线，不能绕过 query owner 的统一收敛。
		"anonymous named browse identity=work": {
			UserID: "u-anon", SessionID: "s-anon",
			Identity: "work", Sort: "recommend", Limit: 10,
		},
		"homepage recommend": {
			UserID: "u-anon", SessionID: "s-homepage",
			ChannelID: "recommend", Sort: "recommend", Limit: 10,
		},
		"anonymous video book identity=work type=video": {
			UserID: "u-anon", SessionID: "s-video",
			Identity: "work", Type: "video", Sort: "recommend", Limit: 10,
		},
		"premium": {
			UserID: "u-anon", SessionID: "s-premium",
			ChannelID: "premium", Sort: "recommend", Limit: 10,
		},
		"following": {
			UserID: "u-member", ViewerPersonaID: "persona-member",
			SessionID: "s-following", ChannelID: "following", Limit: 10,
		},
	} {
		t.Run(name, func(t *testing.T) {
			active := &terminalActiveSupplyReader{active: true, releaseClass: "research"}
			service := researchSupplyService(active)
			response, err := service.ListFeed(context.Background(), request)
			if err != nil {
				t.Fatalf("ListFeed: %v", err)
			}
			if response.Outcome != FeedResponseOutcomeEmpty ||
				response.EmptyReason != FeedEmptyReasonNoActiveRelease ||
				len(response.Items) != 0 {
				t.Fatalf("non-research view must converge to no_active_release: %+v", response)
			}
			wire, marshalErr := json.Marshal(response)
			if marshalErr != nil {
				t.Fatalf("marshal converged response: %v", marshalErr)
			}
			var envelope map[string]any
			if unmarshalErr := json.Unmarshal(wire, &envelope); unmarshalErr != nil {
				t.Fatalf("unmarshal converged response: %v", unmarshalErr)
			}
			// 收敛结果不得泄露 research release 的存在性。
			for _, forbidden := range []string{"releaseId", "manifestDigest"} {
				if _, has := envelope[forbidden]; has {
					t.Fatalf("converged wire must omit %s, got %#v", forbidden, envelope[forbidden])
				}
			}
			if active.calls != 1 {
				t.Fatalf("research convergence must read active release once, calls=%d", active.calls)
			}
		})
	}
}

func TestListFeedResearchReleaseConvergesPaginationBeforeRouteReplay(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true, releaseClass: "commercial"}
	now := time.Now().UTC()
	posts := []postports.PostFeedItemSlice{
		{
			PostID: postports.NewPostID("post-page-1"), AuthorPersonaID: postports.NewPersonaID("author-page-1"),
			ContentType: "image", ContentIdentity: "work", Visibility: "public", CreatedAt: now,
			SourceOwner: "qwq_data", ReleaseID: "rel_local_contract", ManifestDigest: terminalManifestDigest,
			LifecycleStatus: "active",
		},
		{
			PostID: postports.NewPostID("post-page-2"), AuthorPersonaID: postports.NewPersonaID("author-page-2"),
			ContentType: "image", ContentIdentity: "work", Visibility: "public", CreatedAt: now.Add(-time.Minute),
			SourceOwner: "qwq_data", ReleaseID: "rel_local_contract", ManifestDigest: terminalManifestDigest,
			LifecycleStatus: "active",
		},
	}
	candidates := []rtrec.ContentCandidate{
		{
			ContentID: "post-page-1", ContentType: "image", AuthorID: "author-page-1", PublishedAt: now,
			SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: "rel_local_contract",
			ManifestDigest: terminalManifestDigest, LifecycleStatus: "active",
		},
		{
			ContentID: "post-page-2", ContentType: "image", AuthorID: "author-page-2", PublishedAt: now.Add(-time.Minute),
			SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: "rel_local_contract",
			ManifestDigest: terminalManifestDigest, LifecycleStatus: "active",
		},
	}
	service := newTerminalFeedService(
		newTerminalFeedEngine(candidates),
		multiResearchFeedReader{posts: posts},
		WithActiveSupplyReader(active),
		feedDeliveryPageStoreOption(),
	)
	request := ListFeedRequest{
		UserID: "u-page", ViewerPersonaID: "persona-page", SessionID: "s-page",
		ChannelID: "following", Limit: 1, ResearchPrincipal: true,
	}
	first, err := service.ListFeed(context.Background(), request)
	if err != nil || first.NextCursor == "" {
		t.Fatalf("create commercial pagination cursor: response=%+v err=%v", first, err)
	}
	active.releaseClass = "research"
	request.Cursor = first.NextCursor
	request.FeedRequestID = first.FeedRequestID
	request.ResearchPrincipal = false

	response, err := service.ListFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("research pagination convergence: %v", err)
	}
	if response.Outcome != FeedResponseOutcomeEmpty ||
		response.EmptyReason != FeedEmptyReasonNoActiveRelease ||
		len(response.Items) != 0 {
		t.Fatalf("pagination must converge before delivery-page replay: %+v", response)
	}
	wire, marshalErr := json.Marshal(response)
	if marshalErr != nil {
		t.Fatalf("marshal pagination convergence: %v", marshalErr)
	}
	var envelope map[string]any
	if unmarshalErr := json.Unmarshal(wire, &envelope); unmarshalErr != nil {
		t.Fatalf("unmarshal pagination convergence: %v", unmarshalErr)
	}
	for _, forbidden := range []string{"releaseId", "manifestDigest"} {
		if _, has := envelope[forbidden]; has {
			t.Fatalf("pagination convergence must omit %s: %#v", forbidden, envelope)
		}
	}
	if active.calls != 2 {
		t.Fatalf("initial+pagination active supply calls=%d, want 2", active.calls)
	}
}

func TestListFeedResearchReleaseServesResearchPrincipal(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true, releaseClass: "research"}
	service := researchSupplyService(active)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-research", ViewerPersonaID: "persona-research",
		SessionID: "s-research", ChannelID: "recommend", Limit: 10,
		ResearchPrincipal: true,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	// research principal 不被收敛：release 承载内容正常在场。
	if len(response.Items) != 1 || response.Items[0].PostID != "post-research" {
		t.Fatalf("research principal must see release content: %+v", response)
	}
}

func TestListFeedCommercialReleaseIgnoresResearchConvergence(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true, releaseClass: "commercial"}
	service := researchSupplyService(active)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-anon", SessionID: "s-anon", ChannelID: "recommend", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(response.Items) != 1 || response.Items[0].PostID != "post-research" {
		t.Fatalf("commercial release must stay visible to anonymous viewers: %+v", response)
	}
}
