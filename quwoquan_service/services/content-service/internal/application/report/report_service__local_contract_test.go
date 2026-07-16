package report_test

import (
	"context"
	"strings"
	"testing"

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
