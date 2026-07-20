package report_test

import (
	"context"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	reportapp "quwoquan_service/services/content-service/internal/application/report"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
	"quwoquan_service/services/content-service/internal/testsupport"
)

func TestReportCommandAndQueryFacetsStaySeparated(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	createCommand := reportapp.CreateReportCommand{
		ReporterID:  "persona-reporter",
		TargetType:  reportmodel.TargetPost,
		TargetID:    "post-1",
		Reason:      reportmodel.ReasonSpam,
		Description: "重复广告",
	}

	createContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"create-report-1",
	)
	created, err := service.CreateReport(createContext, createCommand)
	if err != nil {
		t.Fatalf("create report: %v", err)
	}
	replayed, err := service.CreateReport(createContext, createCommand)
	if err != nil {
		t.Fatalf("replay create report: %v", err)
	}
	if !replayed.Replayed ||
		replayed.ID != created.ID ||
		replayed.Version != created.Version {
		t.Fatalf("unexpected idempotent replay: %+v vs %+v", replayed, created)
	}
	_, err = service.CreateReport(
		createContext,
		reportapp.CreateReportCommand{
			ReporterID:  createCommand.ReporterID,
			TargetType:  createCommand.TargetType,
			TargetID:    createCommand.TargetID,
			Reason:      createCommand.Reason,
			Description: "不同的命令摘要",
		},
	)
	if err == nil || !strings.Contains(err.Error(), "idempotency_conflict") {
		t.Fatalf("different command must preserve idempotency conflict, got %v", err)
	}

	detail, err := service.GetReport(
		context.Background(),
		reportapp.GetReportQuery{ReportID: created.ID},
	)
	if err != nil {
		t.Fatalf("query report detail: %v", err)
	}
	if detail.ID != created.ID ||
		detail.Status != reportmodel.StatusPending ||
		detail.ReporterID != createCommand.ReporterID {
		t.Fatalf("unexpected detail slice: %+v", detail)
	}

	if _, err := service.Resolve(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"resolve-pending-report-1",
		),
		reportapp.ResolveReportCommand{
			ReportID:   created.ID,
			ReviewerID: "persona-reviewer",
			Resolution: reportmodel.ResolutionDeleteContent,
		},
	); err == nil {
		t.Fatal("pending report must not skip the begin-review command")
	}

	reviewContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"begin-review-report-1",
	)
	reviewCommand := reportapp.BeginReviewReportCommand{
		ReportID:   created.ID,
		ReviewerID: "persona-reviewer",
	}
	reviewing, err := service.BeginReview(
		reviewContext,
		reviewCommand,
	)
	if err != nil {
		t.Fatalf("begin review: %v", err)
	}
	if reviewing.Version != 2 ||
		reviewing.Status != reportmodel.StatusReviewing {
		t.Fatalf("unexpected reviewing result: %+v", reviewing)
	}
	replayedReview, err := service.BeginReview(reviewContext, reviewCommand)
	if err != nil {
		t.Fatalf("replay begin review: %v", err)
	}
	if !replayedReview.Replayed ||
		replayedReview.ID != reviewing.ID ||
		replayedReview.Version != reviewing.Version {
		t.Fatalf("unexpected begin-review replay: %+v vs %+v", replayedReview, reviewing)
	}

	resolveContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"resolve-report-1",
	)
	resolveCommand := reportapp.ResolveReportCommand{
		ReportID:   created.ID,
		ReviewerID: "persona-reviewer",
		Resolution: reportmodel.ResolutionDeleteContent,
	}
	resolved, err := service.Resolve(
		resolveContext,
		resolveCommand,
	)
	if err != nil {
		t.Fatalf("resolve report: %v", err)
	}
	if resolved.Version != 3 || resolved.Status != reportmodel.StatusResolved {
		t.Fatalf("unexpected resolved result: %+v", resolved)
	}
	replayedResolve, err := service.Resolve(resolveContext, resolveCommand)
	if err != nil {
		t.Fatalf("replay resolve report: %v", err)
	}
	if !replayedResolve.Replayed ||
		replayedResolve.ID != resolved.ID ||
		replayedResolve.Version != resolved.Version {
		t.Fatalf("unexpected resolve replay: %+v vs %+v", replayedResolve, resolved)
	}

	queue, err := service.ListReports(
		context.Background(),
		reportapp.ListReportsQuery{Limit: 20},
	)
	if err != nil {
		t.Fatalf("query report queue: %v", err)
	}
	if queue.Total != 1 ||
		len(queue.Items) != 1 ||
		queue.Items[0].Status != reportmodel.StatusResolved {
		t.Fatalf("unexpected queue slice: %+v", queue)
	}
}

func TestDismissReportClosesLifecycleAndObservesSLO(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	observer := &recordingReportObserver{}
	service := reportapp.NewReportService(
		reportapp.BindDataPorts(store),
		reportapp.WithLifecycleObserver(observer),
	)
	created, err := service.CreateReport(
		commandmeta.WithIdempotencyKey(context.Background(), "dismiss-create"),
		reportapp.CreateReportCommand{
			ReporterID: "persona-reporter",
			TargetType: reportmodel.TargetPost,
			TargetID:   "post-dismiss",
			Reason:     reportmodel.ReasonSpam,
		},
	)
	if err != nil {
		t.Fatalf("create report: %v", err)
	}
	if _, err := service.BeginReview(
		commandmeta.WithIdempotencyKey(context.Background(), "dismiss-review"),
		reportapp.BeginReviewReportCommand{
			ReportID: created.ID, ReviewerID: "operator-1",
		},
	); err != nil {
		t.Fatalf("begin report review: %v", err)
	}
	dismissed, err := service.Dismiss(
		commandmeta.WithIdempotencyKey(context.Background(), "dismiss-close"),
		reportapp.DismissReportCommand{
			ReportID: created.ID, ReviewerID: "operator-1",
		},
	)
	if err != nil {
		t.Fatalf("dismiss report: %v", err)
	}
	if dismissed.Status != reportmodel.StatusDismissed {
		t.Fatalf("status=%s want dismissed", dismissed.Status)
	}
	if observer.created != 1 ||
		len(observer.closed) != 1 ||
		observer.closed[0] != string(reportmodel.StatusDismissed) {
		t.Fatalf("unexpected lifecycle observation: %+v", observer)
	}
}

type recordingReportObserver struct {
	created int
	closed  []string
}

func (observer *recordingReportObserver) ReportCreated(context.Context) {
	observer.created++
}

func (observer *recordingReportObserver) ReportClosed(
	_ context.Context,
	status string,
	_ time.Time,
	_ time.Time,
) {
	observer.closed = append(observer.closed, status)
}

// TestReportNoopIntentPersistsReceiptBeforeLaterStateChange 锁定命名状态
// 迁移的 no-op 规则（design.md）：目标状态已满足的首个 Idempotency-Key 仍持久化
// no-op receipt（不递增版本、不产伪事实事件），后续状态继续演进后同 key 仍只
// 重放该次 no-op 的原始结果。
func TestReportNoopIntentPersistsReceiptBeforeLaterStateChange(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	created, err := service.CreateReport(
		commandmeta.WithIdempotencyKey(context.Background(), "noop-report-create"),
		reportapp.CreateReportCommand{
			ReporterID:  "persona-reporter",
			TargetType:  reportmodel.TargetPost,
			TargetID:    "post-noop",
			Reason:      reportmodel.ReasonSpam,
			Description: "no-op receipt 契约",
		},
	)
	if err != nil {
		t.Fatalf("create report: %v", err)
	}
	begin := reportapp.BeginReviewReportCommand{
		ReportID:   created.ID,
		ReviewerID: "operator-1",
	}
	first, err := service.BeginReview(
		commandmeta.WithIdempotencyKey(context.Background(), "noop-begin-first"),
		begin,
	)
	if err != nil {
		t.Fatalf("begin review: %v", err)
	}
	// 目标状态（reviewing/operator-1）已满足：新 key 的首次到达持久化 no-op
	// receipt，返回当前版本且不递增。
	noopContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"noop-begin-second",
	)
	noop, err := service.BeginReview(noopContext, begin)
	if err != nil {
		t.Fatalf("record begin-review no-op: %v", err)
	}
	if noop.Replayed || noop.Version != first.Version {
		t.Fatalf("first no-op must persist its current result: %+v vs %+v", noop, first)
	}
	// 状态继续演进（resolve）。
	resolve := reportapp.ResolveReportCommand{
		ReportID:   created.ID,
		ReviewerID: "operator-1",
		Resolution: reportmodel.ResolutionDeleteContent,
	}
	resolved, err := service.Resolve(
		commandmeta.WithIdempotencyKey(context.Background(), "noop-resolve-first"),
		resolve,
	)
	if err != nil {
		t.Fatalf("resolve report: %v", err)
	}
	// 同一 no-op key 重放：必须返回原 no-op 结果（reviewing 版本），
	// 而不是演进后的 resolved 状态。
	replayed, err := service.BeginReview(noopContext, begin)
	if err != nil {
		t.Fatalf("replay begin-review no-op: %v", err)
	}
	if !replayed.Replayed || replayed.Version != noop.Version {
		t.Fatalf("no-op retry must replay its original result: %+v", replayed)
	}
	// resolve 的目标状态已满足（同 reviewer 同 resolution）：no-op receipt。
	resolveNoop, err := service.Resolve(
		commandmeta.WithIdempotencyKey(context.Background(), "noop-resolve-second"),
		resolve,
	)
	if err != nil {
		t.Fatalf("record resolve no-op: %v", err)
	}
	if resolveNoop.Replayed || resolveNoop.Version != resolved.Version {
		t.Fatalf("resolve no-op must persist current result: %+v vs %+v", resolveNoop, resolved)
	}
}

func TestReportCommandRequiresTransportIdempotencyContext(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	_, err := service.CreateReport(
		context.Background(),
		reportapp.CreateReportCommand{
			ReporterID: "persona-reporter",
			TargetType: reportmodel.TargetPost,
			TargetID:   "post-1",
			Reason:     reportmodel.ReasonSpam,
		},
	)
	if err == nil {
		t.Fatal("command without idempotency context must fail")
	}
}

func TestListMyReportsReturnsOnlyVerifiedPersonaReports(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	create := func(key, reporterID, targetID string) {
		t.Helper()
		if _, err := service.CreateReport(
			commandmeta.WithIdempotencyKey(context.Background(), key),
			reportapp.CreateReportCommand{
				ReporterID: reporterID,
				TargetType: reportmodel.TargetPost,
				TargetID:   targetID,
				Reason:     reportmodel.ReasonSpam,
			},
		); err != nil {
			t.Fatalf("create report %s: %v", targetID, err)
		}
	}
	create("my-report-1", "persona-owner", "post-1")
	create("other-report", "persona-other", "post-other")
	create("my-report-2", "persona-owner", "post-2")

	first, err := service.ListMyReports(
		context.Background(),
		reportapp.ListMyReportsQuery{
			ReporterID: "persona-owner",
			Limit:      1,
		},
	)
	if err != nil {
		t.Fatalf("list first page: %v", err)
	}
	if len(first.Items) != 1 || first.NextCursor == "" {
		t.Fatalf("unexpected first page: %+v", first)
	}
	if first.Items[0].TargetID == "post-other" {
		t.Fatalf("other persona report leaked: %+v", first.Items[0])
	}

	second, err := service.ListMyReports(
		context.Background(),
		reportapp.ListMyReportsQuery{
			ReporterID: "persona-owner",
			Cursor:     first.NextCursor,
			Limit:      1,
		},
	)
	if err != nil {
		t.Fatalf("list second page: %v", err)
	}
	if len(second.Items) != 1 ||
		second.Items[0].ID == first.Items[0].ID ||
		second.Items[0].TargetID == "post-other" {
		t.Fatalf("unexpected second page: %+v", second)
	}
	if second.NextCursor != "" {
		t.Fatalf("last page must not expose next cursor: %+v", second)
	}

	if _, err := service.ListMyReports(
		context.Background(),
		reportapp.ListMyReportsQuery{ReporterID: "persona-owner", Cursor: "bad"},
	); err == nil {
		t.Fatal("invalid cursor must fail closed")
	}
}
