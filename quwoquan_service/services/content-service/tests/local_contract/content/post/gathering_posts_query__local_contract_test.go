// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-008
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-001
package local_contract

import (
	"context"
	"testing"
	"time"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	postpersistence "quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// ListPostsByGathering 是行动详情共同经历聚合区的公开读入口：
// 只返回 public + published + approved 且作者主动写入 gatheringRef 的内容；
// 无 viewer 私有分支——作者删除、转私密或未过审的内容一律不进入聚合区。

type fakeGatheringPostReader struct {
	page    postports.GatheringPostPageSlice
	err     error
	calls   int
	request postports.GatheringPostReadRequest
}

func (r *fakeGatheringPostReader) ListGatheringPosts(
	_ context.Context,
	request postports.GatheringPostReadRequest,
) (postports.GatheringPostPageSlice, error) {
	r.calls++
	r.request = request
	return r.page, r.err
}

func TestListPostsByGatheringRequiresGatheringID(t *testing.T) {
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Gathering: &fakeGatheringPostReader{},
	})

	_, err := facade.ListPostsByGathering(
		context.Background(),
		postports.NewGatheringPostPageQuery("  ", "", 20),
	)

	assertPostQueryErrorCode(
		t,
		err,
		contentgenerated.AppErrorFromInvalidArgument(""),
	)
}

func TestListPostsByGatheringFailsClosedWithoutReader(t *testing.T) {
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{})

	_, err := facade.ListPostsByGathering(
		context.Background(),
		postports.NewGatheringPostPageQuery("gathering-1", "", 20),
	)

	assertPostQueryErrorCode(
		t,
		err,
		contentgenerated.AppErrorFromRequiredDependencyUnavailable(""),
	)
}

func TestListPostsByGatheringRejectsForeignCursorScope(t *testing.T) {
	reader := &fakeGatheringPostReader{}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Gathering: reader,
	})
	foreignCursor := postports.NewAuthorPostCursor(
		postports.NewGatheringPostReadRequest(
			"gathering-other",
			postports.AuthorPostCursor{},
			20,
		).CursorScope(),
		time.Now().UTC(),
		postports.NewPostID("post-1"),
	).Encode()

	_, err := facade.ListPostsByGathering(
		context.Background(),
		postports.NewGatheringPostPageQuery("gathering-1", foreignCursor, 20),
	)

	assertPostQueryErrorCode(
		t,
		err,
		contentgenerated.AppErrorFromInvalidArgument(""),
	)
	if reader.calls != 0 {
		t.Fatalf("foreign cursor must fail before reaching reader")
	}
}

func TestListPostsByGatheringPassesNormalizedRequest(t *testing.T) {
	reader := &fakeGatheringPostReader{
		page: postports.GatheringPostPageSlice{
			Items: []postports.AuthorPostItemSlice{
				{
					PostID:          postports.NewPostID("post-1"),
					AuthorPersonaID: postports.NewPersonaID("persona-a"),
					Status:          postports.PostStatus("published"),
					Visibility:      postports.PostVisibility("public"),
				},
			},
			HasMore: false,
		},
	}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Gathering: reader,
	})

	page, err := facade.ListPostsByGathering(
		context.Background(),
		postports.NewGatheringPostPageQuery(" gathering-1 ", "", 0),
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if reader.calls != 1 {
		t.Fatalf("reader calls = %d, want 1", reader.calls)
	}
	if got := reader.request.GatheringID(); got != "gathering-1" {
		t.Fatalf("gatheringId = %q, want normalized value", got)
	}
	if got := reader.request.Limit(); got != postports.DefaultPostQueryPageSize {
		t.Fatalf("limit = %d, want default %d", got, postports.DefaultPostQueryPageSize)
	}
	if len(page.Items) != 1 || page.Items[0].PostID != "post-1" {
		t.Fatalf("unexpected page: %+v", page)
	}
}

func TestGatheringPostFilterOnlyAllowsPublicPublishedApproved(t *testing.T) {
	filter := postpersistence.GatheringPostFilter(
		postports.NewGatheringPostReadRequest(
			"gathering-1",
			postports.AuthorPostCursor{},
			20,
		),
	)

	want := map[string]any{
		"gatheringRef":      "gathering-1",
		"status":            "published",
		"visibility":        "public",
		"moderationStatus":  "approved",
		"accountRestricted": bson.M{"$ne": true},
	}
	if len(filter) != len(want) {
		t.Fatalf("filter has %d conditions, want %d: %+v", len(filter), len(want), filter)
	}
	for _, condition := range filter {
		expected, ok := want[condition.Key]
		if !ok {
			t.Fatalf("unexpected filter key %q", condition.Key)
		}
		switch expectedValue := expected.(type) {
		case string:
			if condition.Value != expectedValue {
				t.Fatalf("filter[%q] = %v, want %v", condition.Key, condition.Value, expectedValue)
			}
		case bson.M:
			got, isMap := condition.Value.(bson.M)
			if !isMap || len(got) != len(expectedValue) || got["$ne"] != expectedValue["$ne"] {
				t.Fatalf("filter[%q] = %v, want %v", condition.Key, condition.Value, expectedValue)
			}
		}
	}
}
