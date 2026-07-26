package api_integration

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
)

func TestResolvedCommentReportHidesMongoCommentExactlyOnce(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)

	postID := createCommentTestPost(t, "report-comment-post-owner")
	comment := createCommentThroughAPI(
		t,
		postID,
		"report-comment-author",
		"comment requiring verified moderation",
		"",
	)

	suite := newReportPostgresSuite(t)
	defer suite.TearDown(t)
	suite.CleanPG(t)
	reportStore, err := persistence.NewPGReportStore(suite.PG)
	if err != nil {
		t.Fatalf("initialize Report PostgreSQL store: %v", err)
	}
	reportService := reportapp.NewReportService(
		reportapp.BindDataPorts(reportStore),
	)
	created, err := reportService.CreateReport(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"comment-report-create",
		),
		reportapp.CreateReportCommand{
			ReporterID:        "comment-report-reporter",
			ReporterAccountID: "account-comment-report-reporter",
			TargetType:        reportmodel.TargetComment,
			TargetID:          comment.ID,
			Reason:            reportmodel.ReasonHarassment,
			Description:       "verified integration moderation target",
		},
	)
	if err != nil {
		t.Fatalf("create Comment Report: %v", err)
	}
	const reviewerID = "comment-report-operator"
	if _, err := reportService.BeginReview(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"comment-report-begin-review",
		),
		reportapp.BeginReviewReportCommand{
			ReportID:   created.ID,
			ReviewerID: reviewerID,
		},
	); err != nil {
		t.Fatalf("begin Comment Report review: %v", err)
	}
	if _, err := reportService.Resolve(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"comment-report-resolve",
		),
		reportapp.ResolveReportCommand{
			ReportID:   created.ID,
			ReviewerID: reviewerID,
			Resolution: reportmodel.ResolutionDeleteContent,
		},
	); err != nil {
		t.Fatalf("resolve Comment Report: %v", err)
	}

	relay := reportapp.NewOutboxRelay(
		reportStore,
		reportStore,
		moderationapp.NewCommentReportResolutionProjector(testCommentService),
		"api-integration-comment-report-moderation",
	)
	drained, err := relay.Drain(context.Background(), 100)
	if err != nil {
		t.Fatalf("project resolved Comment Report: %v", err)
	}
	if drained != 3 {
		t.Fatalf("Report moderation relay drained=%d events, want 3", drained)
	}
	if err := drainCommentOutboxForHarness(context.Background()); err != nil {
		t.Fatalf("drain CommentModerated outbox: %v", err)
	}

	var persisted struct {
		Status  string `bson:"status"`
		Version int64  `bson:"version"`
	}
	if err := requireMongoDB(t).Collection("comments").FindOne(
		context.Background(),
		bson.M{"_id": comment.ID},
	).Decode(&persisted); err != nil {
		t.Fatalf("read moderated Mongo Comment: %v", err)
	}
	if persisted.Status != "hidden" || persisted.Version != comment.Version+1 {
		t.Fatalf("resolved Report did not hide Comment once: %+v", persisted)
	}
	assertCommentCounter(t, postID, 0)

	replayed, err := relay.Drain(context.Background(), 100)
	if err != nil || replayed != 0 {
		t.Fatalf("Report moderation checkpoint replay count=%d err=%v", replayed, err)
	}
	var afterReplay struct {
		Status  string `bson:"status"`
		Version int64  `bson:"version"`
	}
	if err := requireMongoDB(t).Collection("comments").FindOne(
		context.Background(),
		bson.M{"_id": comment.ID},
	).Decode(&afterReplay); err != nil {
		t.Fatalf("read Comment after Report replay: %v", err)
	}
	if afterReplay != persisted {
		t.Fatalf(
			"Report moderation replay mutated Comment: before=%+v after=%+v",
			persisted,
			afterReplay,
		)
	}
}
