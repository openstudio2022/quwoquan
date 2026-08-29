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

func TestListFeedResearchReleaseConvergesForNonResearchPrincipal(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true, releaseClass: "research"}
	service := researchSupplyService(active)

	for name, request := range map[string]ListFeedRequest{
		"anonymous initial": {
			UserID: "u-anon", SessionID: "s-anon", ChannelID: "recommend", Limit: 10,
		},
		"authenticated non-research": {
			UserID: "u-member", ViewerPersonaID: "persona-member",
			SessionID: "s-member", ChannelID: "recommend", Limit: 10,
		},
		// s4-verify-011 抓到的真实泄露路径：identity=work（无 type）走
		// PostReader 具名浏览时间线，绕过只挂在推荐/视频书分支上的收敛。
		"anonymous named browse identity=work": {
			UserID: "u-anon", SessionID: "s-anon",
			Identity: "work", Sort: "recommend", Limit: 10,
		},
		"anonymous video book identity=work type=video": {
			UserID: "u-anon", SessionID: "s-anon",
			Identity: "work", Type: "video", Sort: "recommend", Limit: 10,
		},
	} {
		t.Run(name, func(t *testing.T) {
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
		})
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
