package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/content-service/internal/application/commandmeta"
	moderationapp "quwoquan_service/services/content-service/internal/application/moderation"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	reportapp "quwoquan_service/services/content-service/internal/application/report"
	moderationmodel "quwoquan_service/services/content-service/internal/domain/moderation/model"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// TestReportOutboxOpensModerationCase 验证举报 → 审核闭环：
// content.report.created 事实经 moderation-projection consumer 幂等打开
// PostModerationCase；同一事实重放与同一 post revision 的第二条举报都归并到
// 同一个 Case（一次创建语义 + revision 唯一约束）。
func TestReportOutboxOpensModerationCase(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })
	cleanModerationCases(t)

	suite := testinfra.NewSuite(t, testinfra.WithPostgres())
	defer suite.TearDown(t)
	suite.CleanPG(t)

	postID := publishModerationTargetPost(t, "被举报的正文内容")

	reportRepo, err := persistence.NewPGReportStore(suite.PG)
	if err != nil {
		t.Fatalf("init pg report store: %v", err)
	}
	reportService := reportapp.NewReportService(reportapp.BindDataPorts(reportRepo))
	opener := moderationapp.NewReportCaseOpener(
		testModerationFacades,
		persistence.NewMongoPostQueryReader(mongoDB.Collection("posts")),
	)
	relay := reportapp.NewOutboxRelay(
		reportRepo,
		reportRepo,
		opener,
		"content-report-moderation-projection",
	)

	firstContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"moderation-report-first",
	)
	if _, err := reportService.CreateReport(firstContext, reportapp.CreateReportCommand{
		ReporterID:  "moderation-reporter-1",
		TargetType:  "post",
		TargetID:    postID,
		Reason:      "spam",
		Description: "疑似垃圾内容",
	}); err != nil {
		t.Fatalf("create first report: %v", err)
	}
	if _, err := relay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain report outbox into moderation projection: %v", err)
	}
	caseAfterFirst := loadModerationCaseByPost(t, postID)
	if caseAfterFirst.Status != string(moderationmodel.StatusPending) {
		t.Fatalf("moderation case must open pending: %+v", caseAfterFirst)
	}

	// 同一批事实重放（新 consumer 从零 checkpoint 重扫，模拟 at-least-once 重投）
	// 不产生第二个 Case。
	replayRelay := reportapp.NewOutboxRelay(
		reportRepo,
		reportRepo,
		opener,
		"content-report-moderation-projection-replay",
	)
	if _, err := replayRelay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("replay report outbox: %v", err)
	}

	// 同一 post revision 的第二条举报归并到既有 Case。
	secondContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"moderation-report-second",
	)
	if _, err := reportService.CreateReport(secondContext, reportapp.CreateReportCommand{
		ReporterID:  "moderation-reporter-2",
		TargetType:  "post",
		TargetID:    postID,
		Reason:      "harassment",
		Description: "另一位用户的举报",
	}); err != nil {
		t.Fatalf("create second report: %v", err)
	}
	if _, err := relay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain second report: %v", err)
	}

	count, err := mongoDB.Collection("post_moderation_cases").CountDocuments(
		context.Background(),
		bson.M{"postId": postID},
	)
	if err != nil || count != 1 {
		t.Fatalf("post revision must own exactly one moderation case: count=%d err=%v", count, err)
	}
	outboxCount, err := mongoDB.Collection("post_moderation_case_outbox").CountDocuments(
		context.Background(),
		bson.M{"aggregateId": caseAfterFirst.ID},
	)
	if err != nil || outboxCount != 1 {
		t.Fatalf("opened case must emit exactly one outbox fact: count=%d err=%v", outboxCount, err)
	}
}

func TestReportPostRevisionDecodeFailureDoesNotAdvanceCheckpoint(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })
	cleanModerationCases(t)

	suite := testinfra.NewSuite(t, testinfra.WithPostgres())
	defer suite.TearDown(t)
	suite.CleanPG(t)

	const postID = "post-malformed-moderation-revision"
	if _, err := mongoDB.Collection("posts").InsertOne(context.Background(), bson.M{
		"_id":           postID,
		"version":       "not-an-int64",
		"contentDigest": "digest-malformed-revision",
	}); err != nil {
		t.Fatalf("insert malformed Post revision: %v", err)
	}
	reportRepo, err := persistence.NewPGReportStore(suite.PG)
	if err != nil {
		t.Fatalf("init pg report store: %v", err)
	}
	reportService := reportapp.NewReportService(reportapp.BindDataPorts(reportRepo))
	if _, err := reportService.CreateReport(
		commandmeta.WithIdempotencyKey(context.Background(), "report-malformed-revision"),
		reportapp.CreateReportCommand{
			ReporterID:  "reporter-malformed-revision",
			TargetType:  "post",
			TargetID:    postID,
			Reason:      "spam",
			Description: "触发真实 BSON revision 解码错误",
		},
	); err != nil {
		t.Fatalf("create report for malformed Post: %v", err)
	}
	const consumer = "content-report-moderation-malformed-revision"
	relay := reportapp.NewOutboxRelay(
		reportRepo,
		reportRepo,
		moderationapp.NewReportCaseOpener(
			testModerationFacades,
			persistence.NewMongoPostQueryReader(mongoDB.Collection("posts")),
		),
		consumer,
	)
	if delivered, err := relay.Drain(context.Background(), 100); err == nil {
		t.Fatalf("malformed Post revision must fail relay, delivered=%d", delivered)
	}
	lease, acquired, err := reportRepo.AcquireCheckpoint(context.Background(), consumer)
	if err != nil || !acquired {
		t.Fatalf("reacquire failed checkpoint: acquired=%v err=%v", acquired, err)
	}
	if checkpoint := lease.Checkpoint(); checkpoint != "" {
		t.Fatalf("decode failure advanced report checkpoint to %q", checkpoint)
	}
	if err := lease.Rollback(); err != nil {
		t.Fatalf("rollback checkpoint probe: %v", err)
	}
	if count, err := mongoDB.Collection("post_moderation_cases").CountDocuments(
		context.Background(),
		bson.M{"postId": postID},
	); err != nil || count != 0 {
		t.Fatalf("decode failure must not open case: count=%d err=%v", count, err)
	}

	if _, err := mongoDB.Collection("posts").UpdateOne(
		context.Background(),
		bson.M{"_id": postID},
		bson.M{"$set": bson.M{"version": int64(1)}},
	); err != nil {
		t.Fatalf("repair Post revision fixture: %v", err)
	}
	if delivered, err := relay.Drain(context.Background(), 100); err != nil || delivered != 1 {
		t.Fatalf("repaired Post revision must replay report: delivered=%d err=%v", delivered, err)
	}
	opened := loadModerationCaseByPost(t, postID)
	if opened.Status != string(moderationmodel.StatusPending) {
		t.Fatalf("replayed report did not open pending case: %+v", opened)
	}
}

// TestModerationDecisionGatesPublicationEligibility 验证审核状态机与发布资格
// 读模型：pending 不可发布，review → approve 后当前 revision 可发布，
// 决定命令幂等重放返回首个结果。
func TestModerationDecisionGatesPublicationEligibility(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })
	cleanModerationCases(t)

	opened, err := testModerationFacades.OpenPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "moderation-open-flow"),
		moderationapp.OpenPostModerationCaseCommand{
			PostID:        "post-moderation-flow",
			PostVersion:   1,
			ContentDigest: "digest-flow-v1",
		},
	)
	if err != nil {
		t.Fatalf("open case: %v", err)
	}
	replayOpen, err := testModerationFacades.OpenPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "moderation-open-flow-second"),
		moderationapp.OpenPostModerationCaseCommand{
			PostID:        "post-moderation-flow",
			PostVersion:   1,
			ContentDigest: "digest-flow-v1",
		},
	)
	if err != nil || !replayOpen.Replayed || replayOpen.CaseID != opened.CaseID {
		t.Fatalf("same revision open must merge: replay=%+v err=%v", replayOpen, err)
	}

	pending, err := testModerationFacades.GetPostPublicationEligibility(
		context.Background(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID: "post-moderation-flow", PostVersion: 1, ContentDigest: "digest-flow-v1",
		},
	)
	if err != nil || pending.Eligible {
		t.Fatalf("pending case must be ineligible: %+v err=%v", pending, err)
	}

	if _, err := testModerationFacades.ReviewPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "moderation-review-flow"),
		moderationapp.ReviewPostModerationCaseCommand{
			CaseID: opened.CaseID, ReviewerID: "operator-flow",
		},
	); err != nil {
		t.Fatalf("review case: %v", err)
	}
	decideContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"moderation-decide-flow",
	)
	decided, err := testModerationFacades.DecidePostModerationCase(
		decideContext,
		moderationapp.DecidePostModerationCaseCommand{
			CaseID: opened.CaseID, ReviewerID: "operator-flow",
			Decision: moderationmodel.DecisionApprove, DecisionReason: "内容安全",
		},
	)
	if err != nil {
		t.Fatalf("decide case: %v", err)
	}
	replayDecide, err := testModerationFacades.DecidePostModerationCase(
		decideContext,
		moderationapp.DecidePostModerationCaseCommand{
			CaseID: opened.CaseID, ReviewerID: "operator-flow",
			Decision: moderationmodel.DecisionApprove, DecisionReason: "内容安全",
		},
	)
	if err != nil || !replayDecide.Replayed || replayDecide.Version != decided.Version {
		t.Fatalf("decide replay mismatch: decided=%+v replay=%+v err=%v", decided, replayDecide, err)
	}

	approved, err := testModerationFacades.GetPostPublicationEligibility(
		context.Background(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID: "post-moderation-flow", PostVersion: 1, ContentDigest: "digest-flow-v1",
		},
	)
	if err != nil || !approved.Eligible || approved.CaseID != opened.CaseID {
		t.Fatalf("approved current revision must be eligible: %+v err=%v", approved, err)
	}
	stale, err := testModerationFacades.GetPostPublicationEligibility(
		context.Background(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID: "post-moderation-flow", PostVersion: 2, ContentDigest: "digest-flow-v2",
		},
	)
	if err != nil || stale.Eligible {
		t.Fatalf("stale revision must stay ineligible: %+v err=%v", stale, err)
	}
}

func TestModerationDecisionOutboxAppliesPostLifecycleAndVisibility(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })
	cleanModerationCases(t)

	suite := testinfra.NewSuite(t, testinfra.WithPostgres())
	defer suite.TearDown(t)
	suite.CleanPG(t)

	published := submitPublishedPostWithAuthor(
		t,
		"moderation-lifecycle-author",
		`{"contentType":"micro","title":"审核可见性目标","body":"moderation-lifecycle-unique-term","visibility":"public"}`,
	)
	postID := asTestString(published["postId"])
	if postID == "" {
		t.Fatalf("published Post response has no postId: %+v", published)
	}
	postReader := persistence.NewMongoPostQueryReader(mongoDB.Collection("posts"))
	revision, found, err := postReader.FindPostRevision(
		context.Background(),
		postports.NewPostID(postID),
	)
	if err != nil || !found {
		t.Fatalf("read initial Post revision: found=%v err=%v", found, err)
	}

	reportRepo, err := persistence.NewPGReportStore(suite.PG)
	if err != nil {
		t.Fatalf("init pg report store: %v", err)
	}
	reportService := reportapp.NewReportService(reportapp.BindDataPorts(reportRepo))
	reportRelay := reportapp.NewOutboxRelay(
		reportRepo,
		reportRepo,
		moderationapp.NewReportCaseOpener(testModerationFacades, postReader),
		"content-report-moderation-post-lifecycle",
	)
	moderationRelay := moderationapp.NewOutboxRelay(
		testModerationStore,
		testModerationStore,
		postapp.NewPostModerationDecisionConsumer(testPostService),
		"content-moderation-post-lifecycle-api-integration",
	)

	createModerationReport(
		t,
		reportService,
		"moderation-lifecycle-report-reject",
		"moderation-lifecycle-reporter-1",
		postID,
		"spam",
	)
	if delivered, err := reportRelay.Drain(context.Background(), 100); err != nil || delivered != 1 {
		t.Fatalf("report outbox did not open first case: delivered=%d err=%v", delivered, err)
	}
	rejectCase := loadModerationCaseByRevision(t, postID, revision.Version)
	if _, err := testModerationFacades.ReviewPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "moderation-lifecycle-review-reject"),
		moderationapp.ReviewPostModerationCaseCommand{
			CaseID: rejectCase.ID, ReviewerID: "moderation-lifecycle-reviewer",
		},
	); err != nil {
		t.Fatalf("review rejection case: %v", err)
	}
	if _, err := testModerationFacades.DecidePostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "moderation-lifecycle-decide-reject"),
		moderationapp.DecidePostModerationCaseCommand{
			CaseID:         rejectCase.ID,
			ReviewerID:     "moderation-lifecycle-reviewer",
			Decision:       moderationmodel.DecisionReject,
			DecisionReason: "policy violation",
		},
	); err != nil {
		t.Fatalf("reject moderation case: %v", err)
	}
	if delivered, err := moderationRelay.Drain(context.Background(), 100); err != nil || delivered != 3 {
		t.Fatalf("moderation outbox did not apply rejection: delivered=%d err=%v", delivered, err)
	}
	postStore := persistence.NewMongoPostStore(mongoDB.Collection("posts"))
	rejected, found, err := postStore.Load(context.Background(), postID)
	if err != nil || !found {
		t.Fatalf("load rejected Post: found=%v err=%v", found, err)
	}
	if rejected.Version != revision.Version+1 || rejected.ModerationStatus != "rejected" {
		t.Fatalf("rejection did not update exact Post revision: %+v", rejected)
	}
	assertModeratedPostVisibility(t, postID, false)

	rejectedRevision, found, err := postReader.FindPostRevision(
		context.Background(),
		postports.NewPostID(postID),
	)
	if err != nil || !found {
		t.Fatalf("read rejected Post revision: found=%v err=%v", found, err)
	}
	createModerationReport(
		t,
		reportService,
		"moderation-lifecycle-report-approve",
		"moderation-lifecycle-reporter-2",
		postID,
		"harassment",
	)
	if delivered, err := reportRelay.Drain(context.Background(), 100); err != nil || delivered != 1 {
		t.Fatalf("report outbox did not open approval case: delivered=%d err=%v", delivered, err)
	}
	approveCase := loadModerationCaseByRevision(t, postID, rejectedRevision.Version)
	if approveCase.ID == rejectCase.ID {
		t.Fatalf("new Post revision must own a new moderation case: %+v", approveCase)
	}
	if _, err := testModerationFacades.ReviewPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "moderation-lifecycle-review-approve"),
		moderationapp.ReviewPostModerationCaseCommand{
			CaseID: approveCase.ID, ReviewerID: "moderation-lifecycle-reviewer",
		},
	); err != nil {
		t.Fatalf("review approval case: %v", err)
	}
	if _, err := testModerationFacades.DecidePostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "moderation-lifecycle-decide-approve"),
		moderationapp.DecidePostModerationCaseCommand{
			CaseID:         approveCase.ID,
			ReviewerID:     "moderation-lifecycle-reviewer",
			Decision:       moderationmodel.DecisionApprove,
			DecisionReason: "content restored",
		},
	); err != nil {
		t.Fatalf("approve moderation case: %v", err)
	}
	if delivered, err := moderationRelay.Drain(context.Background(), 100); err != nil || delivered != 3 {
		t.Fatalf("moderation outbox did not apply approval: delivered=%d err=%v", delivered, err)
	}
	approved, found, err := postStore.Load(context.Background(), postID)
	if err != nil || !found {
		t.Fatalf("load approved Post: found=%v err=%v", found, err)
	}
	if approved.Version != rejectedRevision.Version+1 || approved.ModerationStatus != "approved" {
		t.Fatalf("approval did not restore exact Post revision: %+v", approved)
	}
	assertModeratedPostVisibility(t, postID, true)

	eligibility, err := testModerationFacades.GetPostPublicationEligibility(
		context.Background(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID:        postID,
			PostVersion:   rejectedRevision.Version,
			ContentDigest: rejectedRevision.ContentDigest,
		},
	)
	if err != nil || !eligibility.Eligible || eligibility.CaseID != approveCase.ID {
		t.Fatalf("approved revision publication eligibility mismatch: %+v err=%v", eligibility, err)
	}
	postModerationEvents, err := mongoDB.Collection("content_outbox").CountDocuments(
		context.Background(),
		bson.M{
			"aggregateId": postID,
			"$or": bson.A{
				bson.M{
					"eventType":        "PostModerationRejected",
					"aggregateVersion": revision.Version + 1,
				},
				bson.M{
					"eventType":        "PostPublished",
					"aggregateVersion": rejectedRevision.Version + 1,
				},
			},
		},
	)
	if err != nil || postModerationEvents != 2 {
		t.Fatalf("Post lifecycle must emit one durable fact per applied decision: count=%d err=%v", postModerationEvents, err)
	}
}

func createModerationReport(
	t *testing.T,
	service *reportapp.ReportService,
	idempotencyKey string,
	reporterID string,
	postID string,
	reason string,
) {
	t.Helper()
	if _, err := service.CreateReport(
		commandmeta.WithIdempotencyKey(context.Background(), idempotencyKey),
		reportapp.CreateReportCommand{
			ReporterID:  reporterID,
			TargetType:  "post",
			TargetID:    postID,
			Reason:      reportmodel.Reason(reason),
			Description: "moderation lifecycle integration",
		},
	); err != nil {
		t.Fatalf("create moderation report %s: %v", idempotencyKey, err)
	}
}

func assertModeratedPostVisibility(t *testing.T, postID string, visible bool) {
	t.Helper()
	request := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	response := httptest.NewRecorder()
	testHandler.ServeHTTP(response, request)
	wantStatus := http.StatusNotFound
	if visible {
		wantStatus = http.StatusOK
	}
	if response.Code != wantStatus {
		t.Fatalf(
			"Post detail visibility=%v status=%d want=%d body=%s",
			visible,
			response.Code,
			wantStatus,
			response.Body.String(),
		)
	}

	reader := persistence.NewMongoPostQueryReader(mongoDB.Collection("posts"))
	_, feedFound, err := reader.FindPublishedFeedPost(
		context.Background(),
		postports.NewPostID(postID),
	)
	if err != nil || feedFound != visible {
		t.Fatalf("Post feed visibility=%v found=%v err=%v", visible, feedFound, err)
	}
}

func publishModerationTargetPost(t *testing.T, body string) string {
	t.Helper()
	receipt := submitPostPublicationIntent(
		t,
		"moderation-intent-"+strings.ReplaceAll(t.Name(), "/", "-"),
		"moderation-draft-"+strings.ReplaceAll(t.Name(), "/", "-"),
		body,
	)
	postID, _ := receipt["postId"].(string)
	if strings.TrimSpace(postID) == "" {
		t.Fatalf("publication receipt has no postId: %v", receipt)
	}
	return postID
}

type moderationCaseRow struct {
	ID            string `bson:"_id"`
	PostID        string `bson:"postId"`
	PostVersion   int64  `bson:"postVersion"`
	ContentDigest string `bson:"contentDigest"`
	Status        string `bson:"status"`
}

func loadModerationCaseByPost(t *testing.T, postID string) moderationCaseRow {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for {
		var row moderationCaseRow
		err := mongoDB.Collection("post_moderation_cases").FindOne(
			context.Background(),
			bson.M{"postId": postID},
		).Decode(&row)
		if err == nil {
			return row
		}
		if time.Now().After(deadline) {
			t.Fatalf("moderation case for post %s not found: %v", postID, err)
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func loadModerationCaseByRevision(
	t *testing.T,
	postID string,
	postVersion int64,
) moderationCaseRow {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for {
		var row moderationCaseRow
		err := mongoDB.Collection("post_moderation_cases").FindOne(
			context.Background(),
			bson.M{"postId": postID, "postVersion": postVersion},
		).Decode(&row)
		if err == nil {
			return row
		}
		if time.Now().After(deadline) {
			t.Fatalf(
				"moderation case for post %s revision %d not found: %v",
				postID,
				postVersion,
				err,
			)
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func cleanModerationCases(t *testing.T) {
	t.Helper()
	for _, name := range []string{
		"post_moderation_cases",
		"post_moderation_case_command_receipts",
		"post_moderation_case_outbox",
		"post_moderation_case_audit",
		"post_moderation_case_projection_checkpoints",
	} {
		if _, err := mongoDB.Collection(name).DeleteMany(context.Background(), bson.M{}); err != nil {
			t.Fatalf("clean %s: %v", name, err)
		}
	}
}
