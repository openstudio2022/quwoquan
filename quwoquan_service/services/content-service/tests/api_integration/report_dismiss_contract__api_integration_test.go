package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
)

func TestDismissReportRequiresOperatorAndClosesLifecycle(t *testing.T) {
	suite := testinfra.NewSuite(t, testinfra.WithPostgres())
	defer suite.TearDown(t)
	suite.CleanPG(t)

	reportRepo, handler := newReportTestHandler(t, suite.PG)
	protected := newAuthenticatedReportHandler(t, handler)
	reporterToken := newReportAccessToken(
		t,
		rtauth.TokenSubject{
			AccountID: "reporter-account",
			PersonaID: "reporter-persona",
		},
	)
	create := httptest.NewRequest(
		http.MethodPost,
		"/content/reports",
		strings.NewReader(
			`{"targetType":"post","targetId":"post-dismiss","reason":"spam"}`,
		),
	)
	create.Header.Set("Authorization", "Bearer "+reporterToken)
	create.Header.Set("Content-Type", "application/json")
	create.Header.Set("Idempotency-Key", "create-report-dismiss")
	createResponse := httptest.NewRecorder()
	protected.ServeHTTP(createResponse, create)
	if createResponse.Code != http.StatusNoContent {
		t.Fatalf(
			"create report status=%d want=%d body=%s",
			createResponse.Code,
			http.StatusNoContent,
			createResponse.Body.String(),
		)
	}

	var reportID string
	if err := suite.PG.QueryRow(
		`SELECT id FROM reports WHERE reporter_id = $1 AND target_id = $2`,
		"reporter-persona",
		"post-dismiss",
	).Scan(&reportID); err != nil {
		t.Fatalf("query created report ID: %v", err)
	}

	forbidden := httptest.NewRequest(
		http.MethodPost,
		"/content/reports/"+reportID+":dismiss",
		nil,
	)
	forbidden.Header.Set("Authorization", "Bearer "+reporterToken)
	forbidden.Header.Set("Idempotency-Key", "reporter-cannot-dismiss")
	forbiddenResponse := httptest.NewRecorder()
	protected.ServeHTTP(forbiddenResponse, forbidden)
	if forbiddenResponse.Code != http.StatusForbidden {
		t.Fatalf(
			"reporter dismiss status=%d want=%d body=%s",
			forbiddenResponse.Code,
			http.StatusForbidden,
			forbiddenResponse.Body.String(),
		)
	}

	operatorToken := newReportAccessToken(
		t,
		rtauth.TokenSubject{
			AccountID: "operator-account",
			Scopes:    []string{"ops.case.write"},
			Permissions: []string{
				"content.report.review",
				"content.report.resolve",
			},
			Roles: []string{"operator"},
		},
	)
	beginReview := httptest.NewRequest(
		http.MethodPost,
		"/content/reports/"+reportID+"/review",
		nil,
	)
	beginReview.Header.Set("Authorization", "Bearer "+operatorToken)
	beginReview.Header.Set("Idempotency-Key", "begin-review-dismiss")
	beginReviewResponse := httptest.NewRecorder()
	protected.ServeHTTP(beginReviewResponse, beginReview)
	if beginReviewResponse.Code != http.StatusOK {
		t.Fatalf(
			"begin review status=%d want=%d body=%s",
			beginReviewResponse.Code,
			http.StatusOK,
			beginReviewResponse.Body.String(),
		)
	}

	dismiss := httptest.NewRequest(
		http.MethodPost,
		"/content/reports/"+reportID+":dismiss",
		nil,
	)
	dismiss.Header.Set("Authorization", "Bearer "+operatorToken)
	dismiss.Header.Set("Idempotency-Key", "dismiss-report")
	dismissResponse := httptest.NewRecorder()
	protected.ServeHTTP(dismissResponse, dismiss)
	if dismissResponse.Code != http.StatusOK {
		t.Fatalf(
			"dismiss report status=%d want=%d body=%s",
			dismissResponse.Code,
			http.StatusOK,
			dismissResponse.Body.String(),
		)
	}

	report, found, err := reportRepo.FindByID(context.Background(), reportID)
	if err != nil {
		t.Fatalf("query dismissed report: %v", err)
	}
	if !found || report.Status != reportmodel.StatusDismissed {
		t.Fatalf("dismissed report mismatch: found=%v report=%+v", found, report)
	}
	if report.ReviewerID != "operator-account" {
		t.Fatalf(
			"dismissed report reviewer=%q want operator-account",
			report.ReviewerID,
		)
	}
	assertReportOutboxCount(t, suite.PG, "content.report.dismissed", 1)

	var rawPayload []byte
	if err := suite.PG.QueryRow(
		`SELECT payload_json FROM report_outbox WHERE event_type = $1`,
		"content.report.dismissed",
	).Scan(&rawPayload); err != nil {
		t.Fatalf("query dismissed report event payload: %v", err)
	}
	var payload struct {
		ReporterID string `json:"reporterId"`
		TargetType string `json:"targetType"`
		TargetID   string `json:"targetId"`
		ReviewerID string `json:"reviewerId"`
	}
	if err := json.Unmarshal(rawPayload, &payload); err != nil {
		t.Fatalf("decode dismissed report event payload: %v", err)
	}
	if payload.ReporterID != "reporter-persona" ||
		payload.TargetType != "post" ||
		payload.TargetID != "post-dismiss" ||
		payload.ReviewerID != "operator-account" {
		t.Fatalf("dismissed report event context mismatch: %+v", payload)
	}
}
