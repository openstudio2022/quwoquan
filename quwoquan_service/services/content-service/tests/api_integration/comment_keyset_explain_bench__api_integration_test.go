package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
)

func TestCommentMongoAdapter_ListQueryUsesDeclaredIndex(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "comment-index-post-owner")
	for index := 0; index < 4; index++ {
		createCommentDirect(t, postID, fmt.Sprintf("index-author-%d", index), fmt.Sprintf("index-%d", index))
	}

	cases := []struct {
		name      string
		indexName string
		sort      bson.D
	}{
		{
			name:      "latest",
			indexName: "idx_comments_post_page",
			sort: bson.D{
				{Key: "isPinned", Value: -1},
				{Key: "pinnedAt", Value: -1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
		},
		{
			name:      "hot",
			indexName: "idx_comments_post_hot_page",
			sort: bson.D{
				{Key: "isPinned", Value: -1},
				{Key: "pinnedAt", Value: -1},
				{Key: "hotScore", Value: -1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
		},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			var plan struct {
				QueryPlanner struct {
					WinningPlan bson.M `bson:"winningPlan"`
				} `bson:"queryPlanner"`
			}
			err := mongoDB.RunCommand(context.Background(), bson.D{
				{Key: "explain", Value: bson.D{
					{Key: "find", Value: "comments"},
					{Key: "filter", Value: bson.D{
						{Key: "postId", Value: postID},
						{Key: "parentCommentId", Value: ""},
						{Key: "status", Value: "active"},
					}},
					{Key: "sort", Value: testCase.sort},
					{Key: "limit", Value: 20},
				}},
				{Key: "verbosity", Value: "queryPlanner"},
			}).Decode(&plan)
			if err != nil {
				t.Fatalf("explain Comment %s query: %v", testCase.name, err)
			}
			if len(plan.QueryPlanner.WinningPlan) == 0 {
				t.Fatalf("Comment %s explain has no winningPlan: %+v", testCase.name, plan)
			}
			encoded, _ := json.Marshal(plan.QueryPlanner.WinningPlan)
			planText := string(encoded)
			if !strings.Contains(planText, testCase.indexName) ||
				!strings.Contains(planText, "IXSCAN") {
				t.Fatalf(
					"Comment %s query does not use %s: %s",
					testCase.name,
					testCase.indexName,
					planText,
				)
			}
			if strings.Contains(planText, "COLLSCAN") ||
				strings.Contains(planText, `"stage":"SORT"`) {
				t.Fatalf(
					"Comment %s query regressed to collection scan or blocking sort: %s",
					testCase.name,
					planText,
				)
			}
		})
	}
}

func TestCommentMongoAdapter_KeysetNoTruncation(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "comment-keyset-post-owner")

	const total = 257
	for index := 0; index < total; index++ {
		createCommentDirect(t, postID, "keyset-author", fmt.Sprintf("keyset-%03d", index))
	}

	seen := map[string]struct{}{}
	cursor := ""
	for pageNumber := 0; ; pageNumber++ {
		page, err := testCommentService.ListComments(context.Background(), commentapp.ListCommentsQuery{
			PostID: postID, Cursor: cursor, Limit: 31,
		})
		if err != nil {
			t.Fatalf("list Comment keyset page %d: %v", pageNumber, err)
		}
		for _, item := range page.Items {
			if _, duplicate := seen[item.ID]; duplicate {
				t.Fatalf("duplicate Comment across keyset pages: %s", item.ID)
			}
			seen[item.ID] = struct{}{}
		}
		if page.NextCursor == "" {
			break
		}
		cursor = page.NextCursor
		if pageNumber > total {
			t.Fatal("Comment keyset pagination did not terminate")
		}
	}
	if len(seen) != total {
		t.Fatalf("Comment keyset pagination returned %d unique rows, want %d", len(seen), total)
	}
}

func createCommentDirect(
	t *testing.T,
	postID string,
	actorID string,
	content string,
) commentapp.CommentCommandResult {
	t.Helper()
	ctx := commandmeta.WithIdempotencyKey(
		context.Background(),
		fmt.Sprintf("comment-direct-%s-%d", t.Name(), helperRequestSequence.Add(1)),
	)
	result, err := testCommentService.CreateComment(ctx, commentapp.CreateCommentCommand{
		PostID: postID, ActorID: actorID, Content: content,
	})
	if err != nil {
		t.Fatalf("create direct Comment: %v", err)
	}
	return result
}
