// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
package feed_test

import (
	"context"
	"encoding/json"
	"reflect"
	"sort"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	testsupport "quwoquan_service/services/content-service/tests/support"
)

func TestPremiumHealthyEmptyMarshalsCanonicalArrayEnvelope(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true, zeroPlayableVideo: true}
	service := newTerminalFeedService(
		newTerminalFeedEngine(nil),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "viewer-premium-empty", SessionID: "session-premium-empty",
		ChannelID: "premium", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed premium empty: %v", err)
	}
	if response.Outcome != FeedResponseOutcomeEmpty ||
		response.EmptyReason != FeedEmptyReasonNoEligibleContent {
		t.Fatalf("unexpected premium empty response: %+v", response)
	}
	wire, err := json.Marshal(response)
	if err != nil {
		t.Fatalf("marshal premium empty response: %v", err)
	}
	var envelope map[string]any
	if err := json.Unmarshal(wire, &envelope); err != nil {
		t.Fatalf("decode premium empty response: %v", err)
	}
	items, present := envelope["items"].([]any)
	if !present || len(items) != 0 {
		t.Fatalf("premium empty items = %#v, want required empty list", envelope["items"])
	}
	objectCards, present := envelope["objectCards"].([]any)
	if !present || len(objectCards) != 0 {
		t.Fatalf(
			"premium empty objectCards = %#v, want required empty list",
			envelope["objectCards"],
		)
	}
}

func TestFeedItemPublicProjectionHasExactCanonicalJSONKeys(t *testing.T) {
	now := time.Date(2026, time.August, 9, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		contentType string
		post        postmodel.Post
		wantKeys    []string
	}{
		{
			contentType: "article",
			post: postmodel.Post{
				Title: "article title",
				Body:  "article body",
			},
		},
		{
			contentType: "image",
			post: postmodel.Post{
				Title:        "image title",
				Body:         "image body",
				MediaUrls:    []string{"https://media.test/image.webp"},
				CoverUrl:     "https://media.test/image.webp",
				ThumbnailUrl: "https://media.test/image-thumb.webp",
			},
			wantKeys: []string{"mediaUrls", "coverUrl", "thumbnailUrl"},
		},
		{
			contentType: "video",
			post: postmodel.Post{
				Title:            "video title",
				Body:             "video body",
				MediaUrls:        []string{"https://media.test/video.mp4"},
				VideoUrl:         "https://media.test/video.mp4",
				CoverUrl:         "https://media.test/video-cover.webp",
				ThumbnailUrl:     "https://media.test/video-thumb.webp",
				DurationMs:       12_000,
				CoverStrategy:    "frame_time",
				CoverFrameTimeMs: 3_210,
				MediaItems: []postmodel.PostMediaItem{{
					Kind:                     "video",
					MediaAssetId:             "asset-video-public",
					MediaAssetVersion:        7,
					Url:                      "https://media.test/video.mp4",
					HlsCmafMasterManifestUrl: "https://media.test/master.m3u8",
					HlsCmafDescriptorVersion: 2,
				}},
			},
			wantKeys: []string{
				"mediaUrls", "videoUrl", "mediaAssetId", "mediaAssetVersion",
				"hlsCmafMasterManifestUrl", "hlsCmafDescriptorVersion", "coverUrl",
				"thumbnailUrl", "durationMs",
				// DEC-033：逐媒体交付绑定后，feed 卡 wire 携带 mediaItems。
				"mediaItems",
			},
		},
	}

	for _, test := range tests {
		t.Run(test.contentType, func(t *testing.T) {
			postID := "post-public-" + test.contentType
			post := test.post
			post.ID = postID
			post.ContentType = test.contentType
			post.ContentIdentity = "work"
			post.AuthorId = "author-public"
			post.Status = "published"
			post.Visibility = "public"
			post.TagRefs = []string{"travel.photography"}
			post.ContentVertical = "travel"
			post.SourceTaskId = "internal-source-task"
			post.LikeCount = 3
			post.CommentCount = 2
			post.ShareCount = 1
			post.CreatedAt = now
			post.UpdatedAt = now.Add(time.Minute)
			post.PublishedAt = now

			router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
			engine := rtrec.NewEngine(
				rtrec.NewSessionCache(
					rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
					2*time.Second,
					1000,
				),
				[]rtrec.CandidateSource{&captureRecallSource{
					candidates: []rtrec.ContentCandidate{{
						ContentID:       postID,
						ContentType:     test.contentType,
						PublishedAt:     now,
						RecallPath:      "canonical_release",
						QualityScore:    0.91,
						ContentVertical: "travel",
						SupplySource:    "data_engineering",
					}},
				}},
			)
			svc := NewFeedService(
				fixtureFeedReader{posts: []postmodel.Post{post}},
				testsupport.RankedRecommendationOptions(engine, readyActiveSupplyOption())...,
			)

			response, err := svc.ListFeed(context.Background(), ListFeedRequest{
				UserID: "viewer-public-projection", SessionID: "session-public-projection",
				Identity: "work", Type: test.contentType, Limit: 1,
			})
			if err != nil {
				t.Fatalf("ListFeed: %v", err)
			}
			if len(response.Items) != 1 {
				t.Fatalf("items = %d, want 1", len(response.Items))
			}

			encoded, err := json.Marshal(response.Items[0])
			if err != nil {
				t.Fatalf("marshal feed item: %v", err)
			}
			var decoded map[string]any
			if err := json.Unmarshal(encoded, &decoded); err != nil {
				t.Fatalf("decode feed item: %v", err)
			}
			gotKeys := make([]string, 0, len(decoded))
			for key := range decoded {
				gotKeys = append(gotKeys, key)
			}
			sort.Strings(gotKeys)
			wantKeys := append([]string{
				"postId", "contentType", "contentIdentity", "authorId", "title", "body",
				"likeCount", "commentCount", "shareCount", "createdAt", "updatedAt",
				"publishedAt", "recallPath", "contentVertical", "supplySource",
			}, test.wantKeys...)
			sort.Strings(wantKeys)
			if !reflect.DeepEqual(gotKeys, wantKeys) {
				t.Fatalf("JSON keys = %v, want %v; payload=%s", gotKeys, wantKeys, encoded)
			}
			for _, forbidden := range []string{
				"qualityScore", "sourceTaskId", "tagRefs", "visibility",
				"coverStrategy", "coverFrameTimeMs",
			} {
				if _, exists := decoded[forbidden]; exists {
					t.Fatalf("public feed item leaked %q: %s", forbidden, encoded)
				}
			}
		})
	}
}
