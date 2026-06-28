package tests

import (
	"context"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/contractfixture"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
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
	ID           string   `json:"id"`
	PostID       string   `json:"postId"`
	ContentType  string   `json:"contentType"`
	Identity     string   `json:"contentIdentity"`
	AuthorID     string   `json:"authorId"`
	DisplayName  string   `json:"displayName"`
	AvatarURL    string   `json:"authorAvatarUrl"`
	Title        string   `json:"title"`
	Body         string   `json:"body"`
	Summary      string   `json:"summary"`
	Tags         []string `json:"tagRefs"`
	CoverURL     string   `json:"coverUrl"`
	ImageURLs    []string `json:"imageUrls"`
	VideoURL     string   `json:"videoUrl"`
	LocationName string   `json:"locationName"`
	LikeCount    int64    `json:"likeCount"`
	CommentCount int64    `json:"commentCount"`
	ShareCount   int64    `json:"shareCount"`
	CreatedAt    string   `json:"createdAt"`
	UpdatedAt    string   `json:"updatedAt"`
	PublishedAt  string   `json:"publishedAt"`
}

type contentFixtureComment struct {
	PostID      string `json:"postId"`
	AuthorID    string `json:"authorId"`
	DisplayName string `json:"authorDisplayNameSnapshot"`
	Content     string `json:"content"`
}

type contentFixtureReaction struct {
	PostID string `json:"postId"`
	UserID string `json:"userId"`
	Liked  bool   `json:"liked"`
}

func seedContentContractFixture(t *testing.T, seedRefs ...string) contractSeedEvidence {
	t.Helper()
	if len(seedRefs) == 0 {
		t.Fatal("seedContentContractFixture requires at least one seed ref")
	}
	ctx := context.Background()
	pack, err := contractfixture.LoadMetadataJSON[contentFixturePack](
		"content/test_fixtures/scenarios/content_scenarios.json",
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
			"/v1/content/feed",
			"/v1/content/posts/fixture_photo_001",
			"/v1/content/posts/fixture_photo_001/comments",
			"/v1/content/posts/fixture_photo_001/reaction",
		},
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
		inserted++
	}
	for _, reaction := range seedSet.Reactions {
		if reaction.Liked {
			if _, _, err := testPostService.LikePost(ctx, reaction.PostID, reaction.UserID, ""); err != nil {
				t.Fatalf("seed content like %s: %v", reaction.PostID, err)
			}
			inserted++
		}
	}
	for _, comment := range seedSet.Comments {
		if _, _, err := testPostService.AddComment(
			ctx,
			comment.PostID,
			comment.AuthorID,
			comment.Content,
			"",
			comment.AuthorID,
			"",
			nil,
			nil,
		); err != nil {
			t.Fatalf("seed content comment %s: %v", comment.PostID, err)
		}
		inserted++
	}
	return inserted
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
	if id == "" {
		id = strings.TrimSpace(fp.ID)
	}
	createdAt := parseFixtureTime(fp.CreatedAt)
	updatedAt := createdAt
	if value := strings.TrimSpace(fp.UpdatedAt); value != "" {
		updatedAt = parseFixtureTime(value)
	}
	publishedAt := createdAt
	if value := strings.TrimSpace(fp.PublishedAt); value != "" {
		publishedAt = parseFixtureTime(value)
	}
	mediaURLs := append([]string{}, fp.ImageURLs...)
	if len(mediaURLs) == 0 && fp.CoverURL != "" && fp.ContentType == "image" {
		mediaURLs = []string{fp.CoverURL}
	}
	return &postmodel.Post{
		ID:                        id,
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
