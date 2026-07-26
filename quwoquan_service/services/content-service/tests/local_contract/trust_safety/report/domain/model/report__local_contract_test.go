package model_test

import (
	"errors"
	"testing"
	"time"

	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
)

func TestReportStateMachineOwnsVersionedTransitions(t *testing.T) {
	t.Parallel()

	createdAt := time.Date(2026, 7, 13, 1, 0, 0, 0, time.UTC)
	report, err := reportmodel.Create(reportmodel.CreateParams{
		ID:                "report-1",
		ReporterID:        "persona-reporter",
		ReporterAccountID: "account-reporter",
		TargetType:        reportmodel.TargetPost,
		TargetID:          "post-1",
		Reason:            reportmodel.ReasonSpam,
		Description:       "重复广告",
		Now:               createdAt,
	})
	if err != nil {
		t.Fatalf("create report: %v", err)
	}
	if report.Version() != 1 || report.Status() != reportmodel.StatusPending {
		t.Fatalf(
			"unexpected initial state version=%d status=%s",
			report.Version(),
			report.Status(),
		)
	}

	if err := report.Resolve(
		"reviewer-1",
		reportmodel.ResolutionDeleteContent,
		createdAt.Add(time.Minute),
	); !errors.Is(err, reportmodel.ErrInvalidTransition) {
		t.Fatalf("pending report must not resolve directly, got %v", err)
	}
	if report.Version() != 1 || report.Status() != reportmodel.StatusPending {
		t.Fatal("rejected transition must not mutate aggregate state")
	}

	if err := report.BeginReview(
		"reviewer-1",
		createdAt.Add(time.Minute),
	); err != nil {
		t.Fatalf("begin review: %v", err)
	}
	if report.Version() != 2 || report.Status() != reportmodel.StatusReviewing {
		t.Fatalf(
			"unexpected reviewing state version=%d status=%s",
			report.Version(),
			report.Status(),
		)
	}

	if err := report.Resolve(
		"reviewer-1",
		reportmodel.ResolutionDeleteContent,
		createdAt.Add(2*time.Minute),
	); err != nil {
		t.Fatalf("resolve report: %v", err)
	}
	snapshot := report.Snapshot()
	if snapshot.Version != 3 ||
		snapshot.Status != reportmodel.StatusResolved ||
		snapshot.Resolution != reportmodel.ResolutionDeleteContent ||
		snapshot.ResolvedAt == nil {
		t.Fatalf("unexpected resolved snapshot: %+v", snapshot)
	}
	if err := report.Dismiss(
		"reviewer-1",
		createdAt.Add(3*time.Minute),
	); !errors.Is(err, reportmodel.ErrInvalidTransition) {
		t.Fatalf("terminal report must reject more transitions, got %v", err)
	}
}

func TestReportRestoreRejectsInconsistentTerminalState(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 13, 2, 0, 0, 0, time.UTC)
	_, err := reportmodel.Restore(reportmodel.Snapshot{
		ID:                "report-invalid",
		Version:           2,
		ReporterID:        "persona-reporter",
		ReporterAccountID: "account-reporter",
		TargetType:        reportmodel.TargetPost,
		TargetID:          "post-1",
		Reason:            reportmodel.ReasonSpam,
		Status:            reportmodel.StatusResolved,
		CreatedAt:         now,
		UpdatedAt:         now,
	})
	if !errors.Is(err, reportmodel.ErrInvalidReport) {
		t.Fatalf("inconsistent terminal snapshot must fail, got %v", err)
	}
}

func TestReportRequiresTrustedReporterAccountForResultDelivery(t *testing.T) {
	t.Parallel()

	_, err := reportmodel.Create(reportmodel.CreateParams{
		ID:         "report-without-account",
		ReporterID: "persona-reporter",
		TargetType: reportmodel.TargetPost,
		TargetID:   "post-1",
		Reason:     reportmodel.ReasonSpam,
		Now:        time.Date(2026, 7, 13, 3, 0, 0, 0, time.UTC),
	})
	if !errors.Is(err, reportmodel.ErrInvalidReport) {
		t.Fatalf("report without trusted reporter account must fail, got %v", err)
	}
}
