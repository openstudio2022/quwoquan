package local_contract

import (
	"context"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
	"quwoquan_service/services/content-service/internal/testsupport"
	commenttestsupport "quwoquan_service/services/content-service/internal/testsupport/comment"
)

// GWT5(V4)：sort 参数只接受 hot|latest（空值默认 hot），未知值返回稳定
// comment_sort_invalid，禁止静默回退成任何排序。
func TestListCommentsRejectsUnknownSortWithStableError(t *testing.T) {
	service, _ := newCommentAggregateService()
	_, err := service.ListComments(context.Background(), commentapp.ListCommentsQuery{
		PostID: "post-comment-owner",
		Sort:   "most_liked",
	})
	if err == nil {
		t.Fatalf("unknown sort must be rejected")
	}
	if !strings.Contains(err.Error(), contentgenerated.ErrCommentSortInvalid.Error()) {
		t.Fatalf("expected comment_sort_invalid, got %v", err)
	}
	for _, valid := range []string{"", "hot", "latest"} {
		if _, err := service.ListComments(context.Background(), commentapp.ListCommentsQuery{
			PostID: "post-comment-owner",
			Sort:   valid,
		}); err != nil {
			t.Fatalf("sort %q must be accepted: %v", valid, err)
		}
	}
}

// HotScoreFor 是 hotScore 投影分唯一公式：(like-dislike)+2*reply。
func TestHotScoreFormulaIsDeterministic(t *testing.T) {
	cases := []struct {
		like, dislike, reply, want int64
	}{
		{0, 0, 0, 0},
		{3, 1, 0, 2},
		{0, 0, 5, 10},
		{2, 5, 1, -1},
		{10, 0, 3, 16},
	}
	for _, testCase := range cases {
		got := commentmodel.HotScoreFor(testCase.like, testCase.dislike, testCase.reply)
		if got != testCase.want {
			t.Fatalf(
				"HotScoreFor(%d,%d,%d)=%d want %d",
				testCase.like, testCase.dislike, testCase.reply, got, testCase.want,
			)
		}
	}
}

// F15：CreateComment 频控按 authorId 滑动窗口拦截，超限返回稳定
// comment_rate_limited；其他作者不受影响。
func TestCreateCommentEnforcesAuthorRateWindow(t *testing.T) {
	store := commenttestsupport.NewStore()
	store.SeedPost("post-comment-owner", "persona-post-owner")
	service := commentapp.NewCommentService(
		commentapp.BindDataPorts(
			store,
			store,
			testsupport.NewReactionStore(),
			store,
			store,
		),
		commentapp.WithRateLimitConfig(commentapp.RateLimitConfig{
			BurstWindow: time.Minute,
			BurstMax:    2,
			DailyWindow: 24 * time.Hour,
			DailyMax:    100,
		}),
	)
	for index := 0; index < 2; index++ {
		createComment(t, service, "rate-key-"+string(rune('a'+index)), commentapp.CreateCommentCommand{
			PostID:  "post-comment-owner",
			ActorID: "persona-rate-limited",
			Content: "burst window comment",
		})
	}
	_, err := service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), "rate-key-blocked"),
		commentapp.CreateCommentCommand{
			PostID:  "post-comment-owner",
			ActorID: "persona-rate-limited",
			Content: "third comment must be limited",
		},
	)
	if err == nil {
		t.Fatalf("third comment within window must be rate limited")
	}
	if !strings.Contains(err.Error(), contentgenerated.ErrCommentRateLimited.Error()) {
		t.Fatalf("expected comment_rate_limited, got %v", err)
	}
	// 其他作者不受同窗限制。
	createComment(t, service, "rate-key-other", commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-unrelated",
		Content: "other persona is not limited",
	})
}

// F16：列表投影携带 authorIpLocation 快照与 viewerRelation/authorLiked 默认值；
// 未登录 viewer 恒 none，作者自赞不构成 authorLiked。
func TestListProjectionCarriesIpLocationAndRelationDefaults(t *testing.T) {
	store := commenttestsupport.NewStore()
	store.SeedPost("post-comment-owner", "persona-post-owner")
	service := commentapp.NewCommentService(
		commentapp.BindDataPorts(
			store,
			store,
			testsupport.NewReactionStore(),
			store,
			store,
		),
		commentapp.WithIPLocationResolver(fixedProvinceResolver{province: "浙江"}),
		commentapp.WithClientIPExtractor(func(context.Context) string { return "1.2.3.4" }),
	)
	created := createComment(t, service, "ip-key", commentapp.CreateCommentCommand{
		PostID:  "post-comment-owner",
		ActorID: "persona-ip-author",
		Content: "comment with ip snapshot",
	})
	page, err := service.ListComments(context.Background(), commentapp.ListCommentsQuery{
		PostID: "post-comment-owner",
	})
	if err != nil {
		t.Fatalf("list comments: %v", err)
	}
	var found bool
	for _, item := range page.Items {
		if item.ID != created.ID {
			continue
		}
		found = true
		if item.AuthorIPLocation != "浙江" {
			t.Fatalf("authorIpLocation snapshot missing, got %q", item.AuthorIPLocation)
		}
		if item.ViewerRelation != string(commentmodel.ViewerRelationNone) {
			t.Fatalf("anonymous viewerRelation must be none, got %q", item.ViewerRelation)
		}
		if item.AuthorLiked {
			t.Fatalf("authorLiked must default to false without post author like fact")
		}
	}
	if !found {
		t.Fatalf("created comment missing from projection")
	}
}

type fixedProvinceResolver struct{ province string }

func (r fixedProvinceResolver) Resolve(ip string) string {
	if strings.TrimSpace(ip) == "" {
		return ""
	}
	return r.province
}
