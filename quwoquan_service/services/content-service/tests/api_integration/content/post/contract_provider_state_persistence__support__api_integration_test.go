// Persistence-specialty provider state: direct Mongo construction is confined
// to aggregate-decoder and HTTP wire round-trip coverage. General API setup
// must continue to use submitPublishedPost/application commands.
package api_integration

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/commandmeta"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

type contractSeedEvidence struct {
	SeedRefs          []string
	ResetScope        string
	TargetStore       string
	InsertedCount     int
	VerifiedEndpoints []string
}

type contentFixtureSeedSet struct {
	Posts     []contentFixturePost     `json:"posts"`
	Comments  []contentFixtureComment  `json:"comments"`
	Reactions []contentFixtureReaction `json:"reactions"`
}

type contentFixturePost struct {
	PostID       string   `json:"postId"`
	ContentType  string   `json:"contentType"`
	Identity     string   `json:"contentIdentity"`
	AuthorID     string   `json:"authorId"`
	DisplayName  string   `json:"authorDisplayName"`
	AvatarURL    string   `json:"authorAvatarUrl"`
	Title        string   `json:"title"`
	Body         string   `json:"body"`
	Summary      string   `json:"summary"`
	Tags         []string `json:"tagRefs"`
	CoverURL     string   `json:"coverUrl"`
	ThumbnailURL string   `json:"thumbnailUrl"`
	MediaURLs    []string `json:"mediaUrls"`
	VideoURL     string   `json:"videoUrl"`
	Width        int64    `json:"width"`
	Height       int64    `json:"height"`
	DurationMS   int64    `json:"durationMs"`
	LocationName string   `json:"locationName"`
	LikeCount    int64    `json:"likeCount"`
	CommentCount int64    `json:"commentCount"`
	ShareCount   int64    `json:"shareCount"`
	CreatedAt    string   `json:"createdAt"`
	UpdatedAt    string   `json:"updatedAt"`
	PublishedAt  string   `json:"publishedAt"`
}

type contentFixtureComment struct {
	CommentID        string `json:"commentId"`
	PostID           string `json:"postId"`
	AuthorID         string `json:"authorId"`
	DisplayName      string `json:"authorDisplayNameSnapshot"`
	AvatarURL        string `json:"authorAvatarUrlSnapshot"`
	Content          string `json:"content"`
	ReplyToCommentID string `json:"replyToCommentId"`
}

type contentFixtureReaction struct {
	PostID string `json:"postId"`
	UserID string `json:"userId"`
	Liked  bool   `json:"liked"`
}

func contentFixturePostByID(
	t *testing.T,
	seedRef string,
	postID string,
) contentFixturePost {
	t.Helper()
	seedSet, ok := buildContentContractSeed(seedRef)
	if !ok {
		t.Fatalf("content seed ref not found: %s", seedRef)
	}
	for _, post := range seedSet.Posts {
		if post.PostID == postID {
			return post
		}
	}
	t.Fatalf("content fixture post not found: %s", postID)
	return contentFixturePost{}
}

func provisionContentPersistenceProviderState(t *testing.T, seedRefs ...string) contractSeedEvidence {
	t.Helper()
	if len(seedRefs) == 0 {
		t.Fatal("provisionContentPersistenceProviderState requires at least one seed ref")
	}
	ctx := context.Background()
	resetContentFixtureNamespace(t)
	inserted := 0
	mergedRefs := make([]string, 0, len(seedRefs))
	for _, seedRef := range seedRefs {
		seedSet, ok := buildContentContractSeed(seedRef)
		if !ok {
			t.Fatalf("content seed ref not found: %s", seedRef)
		}
		mergedRefs = append(mergedRefs, seedRef)
		inserted += seedContentFixtureSeedSet(t, ctx, seedSet)
	}
	return contractSeedEvidence{
		SeedRefs:      mergedRefs,
		ResetScope:    "fixture_* posts in content_test",
		TargetStore:   "mongodb:content_test.posts",
		InsertedCount: inserted,
		VerifiedEndpoints: []string{
			"/content/feed",
			"/content/posts/fixture_photo_001",
			"/content/posts/fixture_photo_001/comments",
			"/content/posts/fixture_photo_001/reaction",
		},
	}
}

func buildContentContractSeed(seedRef string) (contentFixtureSeedSet, bool) {
	post := func(id, contentType, authorID, displayName, title string, offset int) contentFixturePost {
		mediaBase := "media/image/s/archived-image/post/" + id + "/v1"
		createdAt := time.Date(2026, time.May, 1, offset, 0, 0, 0, time.UTC)
		return contentFixturePost{
			PostID: id, ContentType: contentType, Identity: "work",
			AuthorID: authorID, DisplayName: displayName,
			AvatarURL: "media/avatar/s/archived-avatar/user/" + authorID + "/v1/avatar.png",
			Title:     title, Body: title + "固定 seed 正文", Summary: title,
			Tags: []string{"fixture", contentType}, CoverURL: mediaBase + "/cover.png",
			ThumbnailURL: mediaBase + "/cover.png", MediaURLs: []string{mediaBase + "/cover.png", mediaBase + "/image-2.png"},
			Width: 1280, Height: 720, LikeCount: int64(80 + offset), CommentCount: 1, ShareCount: 3,
			CreatedAt: createdAt.Format(time.RFC3339), UpdatedAt: createdAt.Format(time.RFC3339),
			PublishedAt: createdAt.Add(24 * time.Hour).Format(time.RFC3339),
		}
	}
	comment := func(id, postID string, index int) contentFixtureComment {
		return contentFixtureComment{
			CommentID: id, PostID: postID,
			AuthorID: "fixture_user_current", DisplayName: "新同学",
			AvatarURL: "media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png",
			Content:   fmt.Sprintf("固定 seed 评论 %d", index+1),
		}
	}
	switch seedRef {
	case "content_discovery_core":
		posts := []contentFixturePost{
			post("fixture_photo_001", "image", "fixture_user_photo", "契约摄影师", "西湖晨光摄影测试详情", 0),
			post("fixture_photo_002", "image", "fixture_user_photo", "契约摄影师", "城市傍晚的光影层次", 1),
			post("fixture_video_001", "video", "fixture_user_travel", "契约旅行家", "杭州一日游契约视频", 2),
			post("fixture_article_001", "article", "fixture_user_article", "契约撰稿人", "契约驱动的发现页文章", 3),
			post("fixture_moment_001", "micro", "fixture_user_current", "新同学", "契约周末早餐", 4),
			post("fixture_post_photography_001", "image", "fixture_user_photo", "契约摄影师", "晨光 #1", 5),
			post("fixture_post_lifestyle_001", "image", "fixture_user_current", "新同学", "窗边 #1", 6),
		}
		posts[2].VideoURL = "media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4"
		posts[2].DurationMS = 45000
		comments := make([]contentFixtureComment, 0, 5)
		for index, postID := range []string{"fixture_photo_001", "fixture_photo_002", "fixture_video_001", "fixture_article_001", "fixture_moment_001"} {
			comments = append(comments, comment(fmt.Sprintf("fixture_comment_discovery_%03d", index+1), postID, index))
		}
		return contentFixtureSeedSet{
			Posts:    posts,
			Comments: comments,
			Reactions: []contentFixtureReaction{
				{PostID: "fixture_photo_001", UserID: "fixture_user_current", Liked: true},
				{PostID: "fixture_video_001", UserID: "fixture_user_friend", Liked: true},
			},
		}, true
	case "comment_thread_core":
		comments := make([]contentFixtureComment, 0, 182)
		for index := 0; index < 182; index++ {
			id := fmt.Sprintf("fixture_comment_boundary_%03d", index+1)
			if index == 0 {
				id = "fixture_comment_parent_001"
			}
			comments = append(comments, comment(id, "fixture_photo_001", index))
		}
		return contentFixtureSeedSet{Comments: comments}, true
	default:
		return contentFixtureSeedSet{}, false
	}
}

func seedContentFixtureSeedSet(t *testing.T, ctx context.Context, seedSet contentFixtureSeedSet) int {
	t.Helper()
	inserted := 0
	for _, fp := range seedSet.Posts {
		post := contentPostFromFixture(fp)
		if _, err := mongoDB.Collection("posts").InsertOne(ctx, post); err != nil {
			t.Fatalf("seed content post %s: %v", post.ID, err)
		}
		if err := seedContentFixturePlaybackProjection(ctx, fp, post.ID); err != nil {
			t.Fatalf("seed content playback projection %s: %v", post.ID, err)
		}
		inserted++
	}
	for _, reaction := range seedSet.Reactions {
		if reaction.Liked {
			actor, err := reactiondomain.NewActor(
				reactiondomain.ActorDimensionPersona,
				reaction.UserID,
			)
			if err != nil {
				t.Fatalf("seed content reaction actor %s: %v", reaction.UserID, err)
			}
			commandContext := commandmeta.WithIdempotencyKey(
				ctx,
				"fixture-reaction:"+reaction.PostID+":"+reaction.UserID,
			)
			if _, err := testReactionService.LikePost(commandContext, reactionapp.LikePostCommand{
				PostID: reaction.PostID,
				Actor:  actor,
			}); err != nil {
				t.Fatalf("seed content like %s: %v", reaction.PostID, err)
			}
			inserted++
		}
	}
	if len(seedSet.Reactions) > 0 {
		drainReactionOutbox(t)
	}
	fixtureCommentIDs := make(map[string]string, len(seedSet.Comments))
	for _, comment := range seedSet.Comments {
		fixtureCommentID := strings.TrimSpace(comment.CommentID)
		if fixtureCommentID == "" {
			t.Fatalf("content fixture comment for post %s has no commentId", comment.PostID)
		}
		replyToCommentID := strings.TrimSpace(comment.ReplyToCommentID)
		if replyToCommentID != "" {
			var found bool
			replyToCommentID, found = fixtureCommentIDs[replyToCommentID]
			if !found {
				t.Fatalf("content fixture comment %s references unavailable reply target", fixtureCommentID)
			}
		}
		commandContext := commandmeta.WithIdempotencyKey(
			ctx,
			"fixture-comment:"+fixtureCommentID,
		)
		result, err := testCommentService.CreateComment(commandContext, commentapp.CreateCommentCommand{
			PostID:                    comment.PostID,
			ActorID:                   comment.AuthorID,
			AuthorDisplayNameSnapshot: comment.DisplayName,
			AuthorAvatarURLSnapshot:   comment.AvatarURL,
			Content:                   comment.Content,
			ReplyToCommentID:          replyToCommentID,
		})
		if err != nil {
			t.Fatalf("seed content comment %s: %v", fixtureCommentID, err)
		}
		fixtureCommentIDs[fixtureCommentID] = result.ID
		inserted++
	}
	if len(seedSet.Comments) > 0 {
		if err := drainCommentOutboxForHarness(ctx); err != nil {
			t.Fatalf("drain seeded Comment outbox: %v", err)
		}
	}
	return inserted
}

func seedContentFixturePlaybackProjection(
	ctx context.Context,
	fixture contentFixturePost,
	postID string,
) error {
	fields := bson.M{}
	if fixture.ThumbnailURL != "" {
		fields["thumbnailUrl"] = fixture.ThumbnailURL
	}
	if fixture.Width > 0 {
		fields["width"] = fixture.Width
	}
	if fixture.Height > 0 {
		fields["height"] = fixture.Height
	}
	if fixture.DurationMS > 0 {
		fields["durationMs"] = fixture.DurationMS
	}
	if fixture.ContentType == "video" && fixture.VideoURL != "" {
		fields["mediaItems"] = []bson.M{{
			"kind":       "video",
			"url":        fixture.VideoURL,
			"coverUrl":   fixture.ThumbnailURL,
			"durationMs": fixture.DurationMS,
			"width":      fixture.Width,
			"height":     fixture.Height,
		}}
	}
	if len(fields) == 0 {
		return nil
	}
	_, err := mongoDB.Collection("posts").UpdateOne(
		ctx,
		bson.M{"_id": postID},
		bson.M{"$set": fields},
	)
	return err
}

func resetContentFixtureNamespace(t *testing.T) {
	t.Helper()
	for _, coll := range []string{"posts"} {
		_, err := mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{
			"$or": []bson.M{
				{"_id": bson.M{"$regex": "^fixture_"}},
				{"postId": bson.M{"$regex": "^fixture_"}},
			},
		})
		if err != nil {
			t.Fatalf("reset content fixture namespace %s: %v", coll, err)
		}
	}
	eventSpy.Reset()
}

func contentPostFromFixture(fp contentFixturePost) *postmodel.Post {
	id := strings.TrimSpace(fp.PostID)
	createdAt := parseFixtureTime(fp.CreatedAt)
	updatedAt := createdAt
	if value := strings.TrimSpace(fp.UpdatedAt); value != "" {
		updatedAt = parseFixtureTime(value)
	}
	publishedAt := createdAt
	if value := strings.TrimSpace(fp.PublishedAt); value != "" {
		publishedAt = parseFixtureTime(value)
	}
	mediaURLs := append([]string{}, fp.MediaURLs...)
	if len(mediaURLs) == 0 && fp.CoverURL != "" && fp.ContentType == "image" {
		mediaURLs = []string{fp.CoverURL}
	}
	return &postmodel.Post{
		ID:                        id,
		PublishIntentId:           "fixture-publish-intent:" + id,
		LocalDraftId:              "fixture-local-draft:" + id,
		AuthorId:                  fp.AuthorID,
		AuthorDisplayNameSnapshot: fp.DisplayName,
		AuthorAvatarUrlSnapshot:   fp.AvatarURL,
		ContentType:               fp.ContentType,
		ContentIdentity:           fp.Identity,
		Title:                     fp.Title,
		Body:                      fp.Body,
		TagRefs:                   fp.Tags,
		MediaUrls:                 mediaURLs,
		CoverUrl:                  fp.CoverURL,
		VideoUrl:                  fp.VideoURL,
		LocationName:              fp.LocationName,
		Status:                    "published",
		Visibility:                "public",
		AssistantUsePolicy:        "inherit",
		Summary:                   fp.Summary,
		LikeCount:                 fp.LikeCount,
		CommentCount:              fp.CommentCount,
		ShareCount:                fp.ShareCount,
		ModerationStatus:          "approved",
		CreatedAt:                 createdAt,
		UpdatedAt:                 updatedAt,
		PublishedAt:               publishedAt,
		LastActiveAt:              updatedAt,
	}
}

func parseFixtureTime(value string) time.Time {
	if parsed, err := time.Parse(time.RFC3339, value); err == nil {
		return parsed
	}
	return time.Now().UTC()
}

func TestContentPostFromFixtureRequiresCanonicalPostID(t *testing.T) {
	t.Parallel()
	post := contentPostFromFixture(contentFixturePost{
		PostID:      "fixture-post-id",
		ContentType: "image",
		Identity:    "work",
		AuthorID:    "fixture-author",
		CreatedAt:   "2026-07-13T00:00:00Z",
	})
	if post.ID != "fixture-post-id" || post.AuthorId != "fixture-author" ||
		post.Status != "published" || post.Visibility != "public" {
		t.Fatalf("fixture mapper changed canonical Post identity: %+v", post)
	}
}
