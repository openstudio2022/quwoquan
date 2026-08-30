// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// feed 应用层的媒体交付绑定装配（DEC-033，OPEN-015 App 消费面缺口）：feed 卡
// wire 必须逐媒体透传 mediaItems（含 mediaAssetId/accessMode/coverAssetId），
// 并携带作者头像的 authorAvatarAssetId/authorAvatarAccessMode——修复前 feed
// 仅从首个 video 提取单个 mediaAssetId，逐图与头像的资产标识在 App 侧缺席。
package feed_test

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	testsupport "quwoquan_service/services/content-service/tests/support"
)

// deliveryBindingFeedReader 直接以 typed PostFeedItemSlice 供数，验证读投影
// 新字段经 ListFeed 装配透传到 wire，且不经 postmodel.Post 中转丢字段。
type deliveryBindingFeedReader struct {
	items []postports.PostFeedItemSlice
}

func (r deliveryBindingFeedReader) FindPublishedFeedPost(
	_ context.Context,
	postID postports.PostID,
) (postports.PostFeedItemSlice, bool, error) {
	for _, item := range r.items {
		if item.PostID == postID {
			return item, true, nil
		}
	}
	return postports.PostFeedItemSlice{}, false, nil
}

func (r deliveryBindingFeedReader) FindPublishedFeedPosts(
	ctx context.Context,
	request postports.PostFeedHydrationRequest,
) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	out := make(map[postports.PostID]postports.PostFeedItemSlice, len(request.PostIDs()))
	for _, id := range request.PostIDs() {
		item, found, err := r.FindPublishedFeedPost(ctx, id)
		if err != nil {
			return nil, err
		}
		if found {
			out[id] = bindActiveRelease(item, request.ActiveReleaseID(), request.ManifestDigest())
		}
	}
	return out, nil
}

func (r deliveryBindingFeedReader) ListPublishedFeedPosts(
	_ context.Context,
	request postports.PostFeedReadRequest,
) (postports.PostFeedSlice, error) {
	items := make([]postports.PostFeedItemSlice, 0, len(r.items))
	for _, item := range r.items {
		items = append(items, bindActiveRelease(item, request.ActiveReleaseID(), request.ManifestDigest()))
	}
	return postports.PostFeedSlice{Items: items}, nil
}

func bindActiveRelease(
	item postports.PostFeedItemSlice,
	activeReleaseID string,
	manifestDigest string,
) postports.PostFeedItemSlice {
	if strings.TrimSpace(activeReleaseID) == "" {
		return item
	}
	item.SourceOwner = "qwq_data"
	item.ReleaseID = strings.TrimSpace(activeReleaseID)
	item.ManifestDigest = strings.TrimSpace(manifestDigest)
	item.LifecycleStatus = "active"
	return item
}

func TestListFeedCarriesPerMediaDeliveryBindingAndAuthorAvatarAsset(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	publishedAt := time.Date(2026, time.August, 20, 12, 0, 0, 0, time.UTC)
	engine := rtrec.NewEngine(
		rtrec.NewSessionCache(
			rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
			2*time.Second,
			1000,
		),
		[]rtrec.CandidateSource{&captureRecallSource{
			candidates: []rtrec.ContentCandidate{{
				ContentID:       "data_post_delivery_binding",
				ContentType:     "video",
				PublishedAt:     publishedAt,
				RecallPath:      "canonical_release",
				QualityScore:    0.9,
				ContentVertical: "travel",
				SupplySource:    "data_engineering",
			}},
		}},
	)
	reader := deliveryBindingFeedReader{items: []postports.PostFeedItemSlice{{
		PostID:                 postports.NewPostID("data_post_delivery_binding"),
		AuthorPersonaID:        postports.NewPersonaID("builtin_travel_blogger"),
		AuthorAvatarURL:        "media/objects/sha256/ee/ff/avatar.webp",
		AuthorAvatarAssetID:    "avatar_travel_blogger",
		AuthorAvatarAccessMode: "signed_grant",
		ContentType:            postports.ContentType("video"),
		ContentIdentity:        postports.ContentIdentity("work"),
		VideoURL:               "media/objects/sha256/aa/bb/clip.mp4",
		MediaURLs:              []string{"media/objects/sha256/aa/bb/clip.mp4"},
		DurationMS:             12_000,
		MediaItems: []postports.PostMediaItemSlice{{
			Kind:              "video",
			MediaAssetID:      "clip_main",
			MediaAssetVersion: 3,
			AccessMode:        "signed_grant",
			URL:               "media/objects/sha256/aa/bb/clip.mp4",
			CoverURL:          "media/objects/sha256/cc/dd/poster.webp",
			CoverAssetID:      "poster_main",
		}, {
			Kind:         "image",
			MediaAssetID: "poster_main",
			AccessMode:   "signed_grant",
			URL:          "media/objects/sha256/cc/dd/poster.webp",
		}},
		Visibility:  postports.PostVisibility("public"),
		CreatedAt:   publishedAt,
		UpdatedAt:   publishedAt,
		PublishedAt: publishedAt,
	}}}

	response, err := NewFeedService(
		reader,
		testsupport.RankedRecommendationOptions(engine, readyActiveSupplyOption())...,
	).ListFeed(ctx, ListFeedRequest{
		UserID: "user_delivery_binding", SessionID: "session_delivery_binding",
		Identity: "work", Type: "video", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed delivery binding: %v", err)
	}
	if len(response.Items) != 1 {
		t.Fatalf("expected one feed card, got %+v", response.Items)
	}
	card := response.Items[0]
	if card.AuthorAvatarAssetID != "avatar_travel_blogger" ||
		card.AuthorAvatarAccessMode != "signed_grant" {
		t.Fatalf("author avatar delivery binding is absent on feed card: %+v", card)
	}
	if len(card.MediaItems) != 2 {
		t.Fatalf("feed card must carry the per-media sequence, got %+v", card.MediaItems)
	}
	video := card.MediaItems[0]
	if video.MediaAssetID != "clip_main" || video.AccessMode != "signed_grant" ||
		video.CoverAssetID != "poster_main" {
		t.Fatalf("per-media delivery binding drifted: %+v", video)
	}
	if card.MediaItems[1].MediaAssetID != "poster_main" {
		t.Fatalf("non-first media identity is absent: %+v", card.MediaItems[1])
	}

	// wire 键名对齐契约投影（content_post_projection.yaml）。
	wire, err := json.Marshal(card)
	if err != nil {
		t.Fatalf("marshal feed card: %v", err)
	}
	for _, key := range []string{
		`"authorAvatarAssetId":"avatar_travel_blogger"`,
		`"authorAvatarAccessMode":"signed_grant"`,
		`"mediaAssetId":"clip_main"`,
		`"accessMode":"signed_grant"`,
		`"coverAssetId":"poster_main"`,
	} {
		if !strings.Contains(string(wire), key) {
			t.Fatalf("feed wire lacks %s: %s", key, wire)
		}
	}
}
