package api_integration

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/contractfixture"
	postevent "quwoquan_service/services/content-service/generated/content/post/contract/event"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

type contractSeedEvidence struct {
	SeedRefs          []string
	ResetScope        string
	TargetStore       string
	InsertedCount     int
	VerifiedEndpoints []string
}

type contentFixturePack struct {
	SeedSets map[string]contentFixtureSeedSet `json:"seedSets"`
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
	pack, err := contractfixture.LoadRepositoryJSON[contentFixturePack](
		"quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load content fixture: %v", err)
	}
	seedSet, ok := pack.SeedSets[seedRef]
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

func seedContentContractFixture(t *testing.T, seedRefs ...string) contractSeedEvidence {
	t.Helper()
	if len(seedRefs) == 0 {
		t.Fatal("seedContentContractFixture requires at least one seed ref")
	}
	ctx := context.Background()
	pack, err := contractfixture.LoadRepositoryJSON[contentFixturePack](
		"quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load content fixture: %v", err)
	}

	resetContentFixtureNamespace(t)
	inserted := 0
	mergedRefs := make([]string, 0, len(seedRefs))
	for _, seedRef := range seedRefs {
		seedSet, ok := pack.SeedSets[seedRef]
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

func seedContentFixtureSeedSet(t *testing.T, ctx context.Context, seedSet contentFixtureSeedSet) int {
	t.Helper()
	inserted := 0
	discoveryProjector := recinfra.NewDiscoveryFeedProjector(mongoDB)
	for _, fp := range seedSet.Posts {
		post := contentPostFromFixture(fp)
		if _, err := mongoDB.Collection("posts").InsertOne(ctx, post); err != nil {
			t.Fatalf("seed content post %s: %v", post.ID, err)
		}
		if err := seedContentFixturePlaybackProjection(ctx, fp, post.ID); err != nil {
			t.Fatalf("seed content playback projection %s: %v", post.ID, err)
		}
		payload, err := contentFixtureProjectionPayload(post)
		if err != nil {
			t.Fatalf("encode content projection payload %s: %v", post.ID, err)
		}
		if err := discoveryProjector.Project(ctx, recinfra.ProjectorEvent{
			Type:          postevent.PostPublished,
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload:       payload,
			OccurredAt:    post.PublishedAt,
		}); err != nil {
			t.Fatalf("seed content discovery projection %s: %v", post.ID, err)
		}
		projected, err := mongoDB.Collection("rm_discovery_feed").CountDocuments(
			ctx,
			bson.M{"postId": post.ID},
		)
		if err != nil || projected != 1 {
			t.Fatalf(
				"seed content discovery projection %s missing (count=%d err=%v payload=%#v)",
				post.ID,
				projected,
				err,
				payload,
			)
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

func contentFixtureProjectionPayload(post *postmodel.Post) (map[string]any, error) {
	encoded, err := json.Marshal(post)
	if err != nil {
		return nil, err
	}
	payload := map[string]any{}
	if err := json.Unmarshal(encoded, &payload); err != nil {
		return nil, err
	}
	// PostPublished 的 canonical wire 主键是 postId；领域 aggregate 的 json
	// 序列化字段为 id，测试种子必须显式映射，不能让 projector 静默 no-op。
	payload["postId"] = post.ID
	delete(payload, "id")
	return payload, nil
}

func resetContentFixtureNamespace(t *testing.T) {
	t.Helper()
	for _, coll := range []string{"posts", "rm_discovery_feed"} {
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
		AssistantUsePolicy:        "allow",
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
