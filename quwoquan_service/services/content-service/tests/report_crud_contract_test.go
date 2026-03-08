package tests

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"quwoquan_service/runtime/testinfra"
	contenhttp "quwoquan_service/services/content-service/internal/adapters/http"
	"quwoquan_service/services/content-service/internal/application"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

func TestCreateAndResolveReportLifecycle(t *testing.T) {
	suite := testinfra.NewSuite(t, testinfra.WithPostgres())
	defer suite.TearDown(t)
	suite.CleanPG(t)

	reportRepo, spy, handler := newReportTestHandler(t, suite.PG)

	createReq := httptest.NewRequest(http.MethodPost, "/v1/content/reports", strings.NewReader(`{
	  "targetType":"post",
	  "targetId":"post_123",
	  "reason":"spam",
	  "description":"重复营销内容"
	}`))
	createReq.Header.Set("Content-Type", "application/json")
	createReq.Header.Set("X-Client-User-Id", "user_reporter")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", createRec.Code, createRec.Body.String())
	}

	var created map[string]any
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	reportID := created["id"].(string)

	report, ok, err := reportRepo.FindByID(context.Background(), reportID)
	if err != nil {
		t.Fatalf("query created report: %v", err)
	}
	if !ok {
		t.Fatalf("report not found after create")
	}
	if report.Status != "pending" {
		t.Fatalf("expected pending, got %s", report.Status)
	}
	if len(spy.EventsOfType("ReportCreated")) != 1 {
		t.Fatalf("expected ReportCreated event")
	}

	reviewReq := httptest.NewRequest(http.MethodPatch, "/v1/content/reports/"+reportID, strings.NewReader(`{
	  "status":"reviewing",
	  "reviewerId":"ops_reviewer_1"
	}`))
	reviewReq.Header.Set("Content-Type", "application/json")
	reviewRec := httptest.NewRecorder()
	handler.ServeHTTP(reviewRec, reviewReq)
	if reviewRec.Code != http.StatusOK {
		t.Fatalf("expected 200 when moving to reviewing, got %d: %s", reviewRec.Code, reviewRec.Body.String())
	}

	report, ok, err = reportRepo.FindByID(context.Background(), reportID)
	if err != nil || !ok {
		t.Fatalf("query reviewing report failed: ok=%v err=%v", ok, err)
	}
	if report.Status != "reviewing" {
		t.Fatalf("expected reviewing, got %s", report.Status)
	}

	resolveReq := httptest.NewRequest(http.MethodPatch, "/v1/content/reports/"+reportID, strings.NewReader(`{
	  "resolution":"resolved",
	  "reviewerId":"ops_reviewer_1"
	}`))
	resolveReq.Header.Set("Content-Type", "application/json")
	resolveRec := httptest.NewRecorder()
	handler.ServeHTTP(resolveRec, resolveReq)
	if resolveRec.Code != http.StatusOK {
		t.Fatalf("expected 200 when resolving report, got %d: %s", resolveRec.Code, resolveRec.Body.String())
	}

	report, ok, err = reportRepo.FindByID(context.Background(), reportID)
	if err != nil || !ok {
		t.Fatalf("query resolved report failed: ok=%v err=%v", ok, err)
	}
	if report.Status != "resolved" {
		t.Fatalf("expected resolved, got %s", report.Status)
	}
	if report.Resolution != "resolved" {
		t.Fatalf("expected resolution=resolved, got %s", report.Resolution)
	}
	if report.ReviewerID != "ops_reviewer_1" {
		t.Fatalf("expected reviewer id to be saved")
	}
	if report.ResolvedAt == nil {
		t.Fatalf("expected resolvedAt to be set")
	}
	if len(spy.EventsOfType("ReportResolved")) != 1 {
		t.Fatalf("expected ReportResolved event")
	}
}

func newReportTestHandler(t *testing.T, db *sql.DB) (persistence.ReportRepository, *testinfra.EventSpy, http.Handler) {
	t.Helper()
	reportRepo, err := persistence.NewPGReportStore(db)
	if err != nil {
		t.Fatalf("init pg report store: %v", err)
	}
	spy := testinfra.NewEventSpy()
	reportService := application.NewReportService(reportRepo, spy)
	handler := contenhttp.NewContentHandler(nil, nil, reportService, nil).Routes()
	return reportRepo, spy, handler
}
