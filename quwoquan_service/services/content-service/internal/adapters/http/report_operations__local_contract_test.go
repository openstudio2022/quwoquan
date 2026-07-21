package http

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	reportapp "quwoquan_service/services/content-service/internal/application/report"
	"quwoquan_service/services/content-service/internal/testsupport"
)

func TestReportOperationsRejectAnonymousForgedAndUnauthorizedPrincipals(t *testing.T) {
	handler, _ := newReportOperationsLocalContractHandler(t)
	operations := []struct {
		name   string
		method string
		target string
		body   string
	}{
		{
			name:   "list",
			method: http.MethodGet,
			target: "/content/reports?limit=10",
		},
		{
			name:   "get",
			method: http.MethodGet,
			target: "/content/reports/rpt_missing",
		},
		{
			name:   "begin review",
			method: http.MethodPost,
			target: "/content/reports/rpt_missing/review",
			body:   `{}`,
		},
		{
			name:   "resolve",
			method: http.MethodPatch,
			target: "/content/reports/rpt_missing",
			body:   `{"resolution":"warn"}`,
		},
	}
	for _, operation := range operations {
		t.Run(operation.name, func(t *testing.T) {
			anonymous := httptest.NewRequest(
				operation.method,
				operation.target,
				bytes.NewBufferString(operation.body),
			)
			anonymousRecorder := httptest.NewRecorder()
			handler.ServeHTTP(anonymousRecorder, anonymous)
			if anonymousRecorder.Code != http.StatusUnauthorized {
				t.Fatalf(
					"anonymous status=%d want=%d body=%s",
					anonymousRecorder.Code,
					http.StatusUnauthorized,
					anonymousRecorder.Body.String(),
				)
			}

			forged := httptest.NewRequest(
				operation.method,
				operation.target,
				bytes.NewBufferString(operation.body),
			)
			forged.Header.Set("X-Client-Account-Id", "forged-operator")
			forged.Header.Set("X-Client-User-Id", "forged-operator")
			forged.Header.Set("X-Client-Role", "operator")
			forged.Header.Set("X-Client-Scope", "ops.case.read ops.case.write")
			forged.Header.Set("X-Client-Permission", "content.report.read content.report.review content.report.resolve")
			forgedRecorder := httptest.NewRecorder()
			handler.ServeHTTP(forgedRecorder, forged)
			if forgedRecorder.Code != http.StatusUnauthorized {
				t.Fatalf(
					"forged headers status=%d want=%d body=%s",
					forgedRecorder.Code,
					http.StatusUnauthorized,
					forgedRecorder.Body.String(),
				)
			}

			regularUser := newAuthenticatedReportRequest(
				t,
				operation.method,
				operation.target,
				bytes.NewBufferString(operation.body),
				rtauth.TokenSubject{
					AccountID: "regular-account",
					PersonaID: "regular-persona",
				},
			)
			regularUserRecorder := httptest.NewRecorder()
			handler.ServeHTTP(regularUserRecorder, regularUser)
			if regularUserRecorder.Code != http.StatusForbidden {
				t.Fatalf(
					"regular user status=%d want=%d body=%s",
					regularUserRecorder.Code,
					http.StatusForbidden,
					regularUserRecorder.Body.String(),
				)
			}
		})
	}

	operatorWithoutPermission := newAuthenticatedReportRequest(
		t,
		http.MethodGet,
		"/content/reports?limit=10",
		nil,
		rtauth.TokenSubject{
			AccountID: "operator-without-permission",
			Roles:     []string{"operator"},
			Scopes:    []string{"ops.case.read"},
		},
	)
	operatorWithoutPermissionRecorder := httptest.NewRecorder()
	handler.ServeHTTP(operatorWithoutPermissionRecorder, operatorWithoutPermission)
	if operatorWithoutPermissionRecorder.Code != http.StatusForbidden {
		t.Fatalf(
			"operator without permission report queue status=%d want=%d body=%s",
			operatorWithoutPermissionRecorder.Code,
			http.StatusForbidden,
			operatorWithoutPermissionRecorder.Body.String(),
		)
	}
}

func TestReportOperatorQueueReviewResolveTransitionAndIdempotency(t *testing.T) {
	handler, store := newReportOperationsLocalContractHandler(t)
	reporter := rtauth.TokenSubject{
		AccountID: "reporter-account",
		PersonaID: "reporter-persona",
	}
	create := newAuthenticatedReportRequest(
		t,
		http.MethodPost,
		"/content/reports",
		bytes.NewBufferString(`{
			"targetType":"post",
			"targetId":"report-target-post",
			"reason":"spam"
		}`),
		reporter,
	)
	create.Header.Set("Content-Type", "application/json")
	create.Header.Set("Idempotency-Key", "create-report-local-contract")
	createRecorder := httptest.NewRecorder()
	handler.ServeHTTP(createRecorder, create)
	if createRecorder.Code != http.StatusNoContent {
		t.Fatalf(
			"create report status=%d want=%d body=%s",
			createRecorder.Code,
			http.StatusNoContent,
			createRecorder.Body.String(),
		)
	}

	readOperator := rtauth.TokenSubject{
		AccountID:   "review-operator",
		Roles:       []string{"operator"},
		Scopes:      []string{"ops.case.read"},
		Permissions: []string{"content.report.read"},
	}
	list := newAuthenticatedReportRequest(
		t,
		http.MethodGet,
		"/content/reports?limit=10",
		nil,
		readOperator,
	)
	listRecorder := httptest.NewRecorder()
	handler.ServeHTTP(listRecorder, list)
	if listRecorder.Code != http.StatusOK {
		t.Fatalf("list reports status=%d body=%s", listRecorder.Code, listRecorder.Body.String())
	}
	var queue reportapp.ReportQueueSlice
	if err := json.Unmarshal(listRecorder.Body.Bytes(), &queue); err != nil {
		t.Fatalf("decode report queue: %v", err)
	}
	if queue.Total != 1 || len(queue.Items) != 1 {
		t.Fatalf("unexpected report queue: %+v", queue)
	}
	reportID := queue.Items[0].ID
	if reportID == "" {
		t.Fatalf("report queue item is missing ID: %+v", queue.Items[0])
	}
	if bytes.Contains(listRecorder.Body.Bytes(), []byte(`"reporterId"`)) {
		t.Fatalf("report queue leaked reporter identity: %s", listRecorder.Body.String())
	}

	detail := newAuthenticatedReportRequest(
		t,
		http.MethodGet,
		"/content/reports/"+reportID,
		nil,
		readOperator,
	)
	detailRecorder := httptest.NewRecorder()
	handler.ServeHTTP(detailRecorder, detail)
	if detailRecorder.Code != http.StatusOK {
		t.Fatalf("get report status=%d body=%s", detailRecorder.Code, detailRecorder.Body.String())
	}
	if bytes.Contains(detailRecorder.Body.Bytes(), []byte(`"reporterAccountId"`)) {
		t.Fatalf(
			"operator report detail leaked reporter account identity: %s",
			detailRecorder.Body.String(),
		)
	}

	writeOperator := rtauth.TokenSubject{
		AccountID:   "review-operator",
		Roles:       []string{"operator"},
		Scopes:      []string{"ops.case.write"},
		Permissions: []string{"content.report.review", "content.report.resolve"},
	}
	beginReview := newAuthenticatedReportRequest(
		t,
		http.MethodPost,
		"/content/reports/"+reportID+"/review",
		bytes.NewBufferString(`{}`),
		writeOperator,
	)
	beginReview.Header.Set("Content-Type", "application/json")
	beginReview.Header.Set("Idempotency-Key", "begin-review-local-contract")
	beginReviewRecorder := httptest.NewRecorder()
	handler.ServeHTTP(beginReviewRecorder, beginReview)
	if beginReviewRecorder.Code != http.StatusOK {
		t.Fatalf(
			"begin review status=%d body=%s",
			beginReviewRecorder.Code,
			beginReviewRecorder.Body.String(),
		)
	}
	var reviewResult reportapp.ReportCommandResult
	if err := json.Unmarshal(beginReviewRecorder.Body.Bytes(), &reviewResult); err != nil {
		t.Fatalf("decode begin review response: %v", err)
	}
	if string(reviewResult.Status) != "reviewing" {
		t.Fatalf("begin review status=%q want reviewing", reviewResult.Status)
	}

	forgedReviewer := newAuthenticatedReportRequest(
		t,
		http.MethodPatch,
		"/content/reports/"+reportID,
		bytes.NewBufferString(`{"resolution":"warn","reviewerId":"forged-reviewer"}`),
		writeOperator,
	)
	forgedReviewer.Header.Set("Content-Type", "application/json")
	forgedReviewer.Header.Set("Idempotency-Key", "forged-reviewer-local-contract")
	forgedReviewerRecorder := httptest.NewRecorder()
	handler.ServeHTTP(forgedReviewerRecorder, forgedReviewer)
	if forgedReviewerRecorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"forged reviewer payload status=%d want=%d body=%s",
			forgedReviewerRecorder.Code,
			http.StatusBadRequest,
			forgedReviewerRecorder.Body.String(),
		)
	}

	var firstResolve reportapp.ReportCommandResult
	for attempt := 0; attempt < 2; attempt++ {
		resolve := newAuthenticatedReportRequest(
			t,
			http.MethodPatch,
			"/content/reports/"+reportID,
			bytes.NewBufferString(`{"resolution":"warn"}`),
			writeOperator,
		)
		resolve.Header.Set("Content-Type", "application/json")
		resolve.Header.Set("Idempotency-Key", "resolve-report-local-contract")
		resolveRecorder := httptest.NewRecorder()
		handler.ServeHTTP(resolveRecorder, resolve)
		if resolveRecorder.Code != http.StatusOK {
			t.Fatalf(
				"resolve attempt=%d status=%d body=%s",
				attempt,
				resolveRecorder.Code,
				resolveRecorder.Body.String(),
			)
		}
		var result reportapp.ReportCommandResult
		if err := json.Unmarshal(resolveRecorder.Body.Bytes(), &result); err != nil {
			t.Fatalf("decode resolve attempt=%d response: %v", attempt, err)
		}
		if string(result.Status) != "resolved" {
			t.Fatalf("resolve attempt=%d status=%q want resolved", attempt, result.Status)
		}
		if attempt == 0 {
			firstResolve = result
		} else if !result.Replayed ||
			result.ID != firstResolve.ID ||
			result.Version != firstResolve.Version {
			t.Fatalf(
				"resolve replay=%+v first=%+v",
				result,
				firstResolve,
			)
		}
	}

	finalDetail := newAuthenticatedReportRequest(
		t,
		http.MethodGet,
		"/content/reports/"+reportID,
		nil,
		readOperator,
	)
	finalDetailRecorder := httptest.NewRecorder()
	handler.ServeHTTP(finalDetailRecorder, finalDetail)
	if finalDetailRecorder.Code != http.StatusOK {
		t.Fatalf(
			"get resolved report status=%d body=%s",
			finalDetailRecorder.Code,
			finalDetailRecorder.Body.String(),
		)
	}
	var resolved reportapp.ReportDetailSlice
	if err := json.Unmarshal(finalDetailRecorder.Body.Bytes(), &resolved); err != nil {
		t.Fatalf("decode resolved report: %v", err)
	}
	if string(resolved.Status) != "resolved" || resolved.ReviewerID != "review-operator" {
		t.Fatalf("resolved report=%+v", resolved)
	}
	resolvedEvents := 0
	for _, event := range store.OutboxEvents() {
		if event.EventType == "content.report.resolved" {
			resolvedEvents++
			var payload map[string]any
			if err := json.Unmarshal(event.Payload, &payload); err != nil {
				t.Fatalf("decode resolved report event: %v", err)
			}
			if got, _ := payload["reporterAccountId"].(string); got != reporter.AccountID {
				t.Fatalf(
					"resolved event reporterAccountId=%q want trusted account %q; payload=%#v",
					got,
					reporter.AccountID,
					payload,
				)
			}
		}
	}
	if resolvedEvents != 1 {
		t.Fatalf("resolved outbox events=%d want=1", resolvedEvents)
	}
}

func newReportOperationsLocalContractHandler(
	t *testing.T,
) (http.Handler, *testsupport.ReportStore) {
	t.Helper()
	store := testsupport.NewReportStore()
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	next := NewContentHandler(
		nil,
		nil,
		nil,
		nil,
		nil,
		reportapp.BindFacades(service),
		nil,
	).Routes()
	verifier, err := rtauth.NewHS256Verifier(reportOperationsTokenConfig())
	if err != nil {
		t.Fatalf("build report operations verifier: %v", err)
	}
	return rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: verifier,
	})(
		rtauth.RequireGeneratedOperationAuthorization(
			operationsecurity.ForDomain("content"),
		)(next),
	), store
}

func newAuthenticatedReportRequest(
	t *testing.T,
	method string,
	target string,
	body *bytes.Buffer,
	subject rtauth.TokenSubject,
) *http.Request {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(reportOperationsTokenConfig())
	if err != nil {
		t.Fatalf("build report operations signer: %v", err)
	}
	token, err := signer.Sign(subject)
	if err != nil {
		t.Fatalf("sign report operations token: %v", err)
	}
	var requestBody *bytes.Buffer
	if body == nil {
		requestBody = bytes.NewBuffer(nil)
	} else {
		requestBody = body
	}
	request := httptest.NewRequest(method, target, requestBody)
	request.Header.Set("Authorization", "Bearer "+token)
	return request
}

func reportOperationsTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("0123456789abcdef0123456789abcdef"),
		Issuer:       "https://auth.quwoquan.test",
		Audience:     "quwoquan-api",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          30 * time.Minute,
		ClockSkew:    30 * time.Second,
	}
}
