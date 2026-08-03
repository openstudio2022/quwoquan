package post_test

import (
	"context"
	"testing"
	"time"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"quwoquan_service/runtime/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

// visitedAt 是作者声明的到访事实，「同地同期」交集直接以它为召回依据。
// 这组契约守住三件事：缺省不得被伪造成 createdAt、过去时间必须原样保留、
// 未来时间（计划出行）不得进入事实字段。

func newVisitedAtService(store *testsupport.PostStore) *PostService {
	return NewPostService(
		BindDataPorts(store),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
}

func visitedAtPublicationCommand(
	suffix string,
	visitedAt time.Time,
) SubmitPostPublicationCommand {
	return SubmitPostPublicationCommand{
		PublishIntentID: "intent-visited-" + suffix,
		LocalDraftID:    "draft-visited-" + suffix,
		AuthorID:        "persona-visited",
		Content: postmodel.Post{
			ContentType: "micro",
			Body:        "老君山观景台的日出",
			Visibility:  "public",
			GeoTagRef:   "entity:travel/sight/laojun-mountain",
			VisitedAt:   visitedAt,
		},
	}
}

func TestSubmitPostPublicationKeepsDeclaredVisitedAt(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := newVisitedAtService(store)
	visitedAt := time.Date(2026, time.April, 5, 6, 30, 0, 0, time.UTC)

	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"intent-visited-past",
		),
		visitedAtPublicationCommand("past", visitedAt),
	)
	if err != nil {
		t.Fatal(err)
	}

	stored, found := store.FindByID(context.Background(), receipt.PostID)
	if !found {
		t.Fatalf("published post is missing: %s", receipt.PostID)
	}
	if !stored.VisitedAt.Equal(visitedAt) {
		t.Fatalf(
			"declared visitedAt must survive publication, want %s got %s",
			visitedAt,
			stored.VisitedAt,
		)
	}
	if stored.VisitedAt.Equal(stored.CreatedAt) {
		t.Fatalf(
			"visitedAt must stay independent from createdAt, both are %s",
			stored.CreatedAt,
		)
	}
}

func TestSubmitPostPublicationLeavesVisitedAtEmptyWhenUndeclared(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := newVisitedAtService(store)

	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"intent-visited-absent",
		),
		visitedAtPublicationCommand("absent", time.Time{}),
	)
	if err != nil {
		t.Fatal(err)
	}

	stored, found := store.FindByID(context.Background(), receipt.PostID)
	if !found {
		t.Fatalf("published post is missing: %s", receipt.PostID)
	}
	if !stored.VisitedAt.IsZero() {
		t.Fatalf(
			"undeclared visit time must not be fabricated, got %s",
			stored.VisitedAt,
		)
	}
}

func TestSubmitPostPublicationNormalizesVisitedAtToUTC(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := newVisitedAtService(store)
	shanghai := time.FixedZone("CST", 8*60*60)
	local := time.Date(2026, time.May, 1, 9, 0, 0, 0, shanghai)

	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"intent-visited-zone",
		),
		visitedAtPublicationCommand("zone", local),
	)
	if err != nil {
		t.Fatal(err)
	}

	stored, found := store.FindByID(context.Background(), receipt.PostID)
	if !found {
		t.Fatalf("published post is missing: %s", receipt.PostID)
	}
	if stored.VisitedAt.Location() != time.UTC {
		t.Fatalf(
			"visitedAt must be stored in UTC, got location %s",
			stored.VisitedAt.Location(),
		)
	}
	if !stored.VisitedAt.Equal(local) {
		t.Fatalf(
			"UTC normalization must not shift the instant, want %s got %s",
			local.UTC(),
			stored.VisitedAt,
		)
	}
}

func TestSubmitPostPublicationRejectsUntrustworthyVisitedAt(t *testing.T) {
	for _, testCase := range []struct {
		name      string
		visitedAt time.Time
	}{
		{
			name:      "future visit is a plan, not a fact",
			visitedAt: time.Now().UTC().Add(72 * time.Hour),
		},
		{
			name:      "pre-epoch visit can only be a client bug",
			visitedAt: time.Date(1900, time.January, 1, 0, 0, 0, 0, time.UTC),
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			store := testsupport.NewPostStore(nil)
			service := newVisitedAtService(store)
			command := visitedAtPublicationCommand(
				testCase.name,
				testCase.visitedAt,
			)

			_, err := service.SubmitPostPublication(
				commandmeta.WithIdempotencyKey(
					context.Background(),
					command.PublishIntentID,
				),
				command,
			)

			requirePublicationErrorCode(t, err, "CONTENT.USER.invalid_argument")
			if posts, _ := store.ListAll(context.Background()); len(posts) != 0 {
				t.Fatalf(
					"rejected visitedAt must not persist a Post: %+v",
					posts,
				)
			}
		})
	}
}

func TestSubmitPostPublicationToleratesClientClockSkewOnVisitedAt(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := newVisitedAtService(store)
	skewed := time.Now().UTC().Add(time.Hour)

	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"intent-visited-skew",
		),
		visitedAtPublicationCommand("skew", skewed),
	)
	if err != nil {
		t.Fatalf("client clock skew must not block publication: %v", err)
	}
	if stored, found := store.FindByID(
		context.Background(),
		receipt.PostID,
	); !found || !stored.VisitedAt.Equal(skewed) {
		t.Fatalf("skewed visitedAt was not preserved: found=%v", found)
	}
}
