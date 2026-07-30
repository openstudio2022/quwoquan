package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	accountenforcementhttp "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/adapters/inbound/http"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/persistence"
	accountenforcementuser "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/useraccount"
	userapisupport "quwoquan_service/services/user-service/tests/support"
)

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-001
// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
func TestAccountEnforcementCaseAtomicProducerDispatchReplayConflictAndRecovery(t *testing.T) {
	if accountEnforcementPGPool == nil {
		t.Fatal("real PostgreSQL pool was not initialized")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	store, err := persistence.NewPostgresStore(accountEnforcementPGPool)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	appealIntakes, err := accountenforcementuser.NewAppealIntakeHTTPClient(
		accountenforcementuser.AppealIntakeHTTPClientConfig{
			BaseURL:     accountEnforcementUserRuntime.BaseURL(),
			HTTPClient:  accountEnforcementUserRuntime.HTTPClient(),
			Credentials: accountEnforcementUserRuntime.AppealCredentials(),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	service := application.NewService(store, nil, appealIntakes)
	handler := accountenforcementhttp.NewHandler(service)
	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	accountID, err := userapisupport.NewCanonicalOwnerID(
		"ph",
		strings.Repeat("0", 26-len(suffix))+suffix,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := userapisupport.CreateAccount(
		ctx,
		accountEnforcementPGPool,
		accountID,
		"Account enforcement "+suffix,
	); err != nil {
		t.Fatal(err)
	}

	moderationCaseID := "moderation-" + suffix
	openModeration := map[string]any{
		"caseId": moderationCaseID, "accountId": accountID,
		"policyRef": "policy/account-safety", "evidenceRefs": []string{"evidence-a", "evidence-b"},
	}
	opened := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/moderation",
		"operator-opener", "open-moderation-"+suffix, openModeration)
	assertStatus(t, opened, http.StatusCreated)

	// Exact replay is stable; the same idempotency key with another command is rejected.
	replayedOpen := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/moderation",
		"operator-opener", "open-moderation-"+suffix, openModeration)
	assertStatus(t, replayedOpen, http.StatusCreated)
	driftedOpen := cloneMap(openModeration)
	driftedOpen["policyRef"] = "policy/drifted"
	conflict := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/moderation",
		"operator-opener", "open-moderation-"+suffix, driftedOpen)
	assertRuntimeErrorCode(t, conflict, http.StatusConflict, "OPS.USER.account_enforcement_idempotency_conflict")

	firstApproval := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/"+moderationCaseID+":review",
		"operator-1", "review-moderation-1-"+suffix, map[string]any{"verdict": "approve"})
	assertStatus(t, firstApproval, http.StatusOK)
	firstApprovalResult := decodeResult(t, firstApproval)
	if firstApprovalResult.Status != "pending_approval" || firstApprovalResult.ApprovalCount != 1 ||
		firstApprovalResult.DecisionID != "" || firstApprovalResult.DeliveryStatus != "" {
		t.Fatalf("unexpected first approval result: %+v", firstApprovalResult)
	}
	secondApproval := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/"+moderationCaseID+":review",
		"operator-2", "review-moderation-2-"+suffix, map[string]any{"verdict": "approve"})
	assertStatus(t, secondApproval, http.StatusOK)
	moderationResult := decodeResult(t, secondApproval)
	if moderationResult.Status != "approved" || moderationResult.DecisionID == "" ||
		moderationResult.DeliveryStatus != "pending" || moderationResult.ApprovalCount != 2 {
		t.Fatalf("unexpected moderation result: %+v", moderationResult)
	}
	secondReplay := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/"+moderationCaseID+":review",
		"operator-2", "review-moderation-2-"+suffix, map[string]any{"verdict": "approve"})
	assertStatus(t, secondReplay, http.StatusOK)
	if decodeResult(t, secondReplay).DecisionID != moderationResult.DecisionID {
		t.Fatal("review replay changed the immutable decision")
	}
	closedReview := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/"+moderationCaseID+":review",
		"operator-3", "review-closed-"+suffix, map[string]any{"verdict": "reject"})
	assertRuntimeErrorCode(t, closedReview, http.StatusConflict, "OPS.USER.account_enforcement_case_closed")
	assertAtomicCounts(t, ctx, moderationCaseID, 2, 1, 1)

	target, err := accountenforcementuser.NewHTTPClient(accountenforcementuser.HTTPClientConfig{
		BaseURL:     accountEnforcementUserRuntime.BaseURL(),
		HTTPClient:  accountEnforcementUserRuntime.HTTPClient(),
		Credentials: accountEnforcementUserRuntime.Credentials(),
	})
	if err != nil {
		t.Fatal(err)
	}
	dispatcher := newTestDispatcher(t, store, target, "dispatcher-success-"+suffix)
	delivered, err := dispatcher.DispatchOnce(ctx)
	if err != nil || delivered != 1 {
		t.Fatalf("dispatch suspend: delivered=%d err=%v", delivered, err)
	}
	assertDeliveryStatus(t, ctx, moderationResult.DecisionID, "delivered", 0)
	assertUserAccountState(t, ctx, accountID, "suspended", 2)
	assertUserEnforcementReceipt(t, ctx, moderationResult.DecisionID, "suspend", "suspended", 2)

	intakeRef, err := accountEnforcementUserRuntime.SubmitAppealIntakeFixture(
		ctx,
		accountID,
		"official-intake-"+suffix,
	)
	if err != nil {
		t.Fatal(err)
	}
	appealCaseID := "appeal-" + suffix
	openedAppeal := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/appeal",
		"operator-appeal", "open-appeal-"+suffix, map[string]any{
			"caseId": appealCaseID, "accountId": accountID,
			"sourceDecisionId": moderationResult.DecisionID,
			"intakeRef":        intakeRef,
			"evidenceRefs":     []string{"appeal-evidence"},
		})
	assertStatus(t, openedAppeal, http.StatusCreated)
	for index, actor := range []string{"appeal-reviewer-1", "appeal-reviewer-2"} {
		response := performJSON(t, handler, http.MethodPost,
			"/control-plane/product/account-enforcement-cases/"+appealCaseID+":review",
			actor, fmt.Sprintf("appeal-review-%d-%s", index, suffix), map[string]any{"verdict": "approve"})
		assertStatus(t, response, http.StatusOK)
	}
	appealResult := getCaseResult(t, handler, appealCaseID, "operator-reader")
	if appealResult.Status != "approved" || appealResult.DecisionID == "" {
		t.Fatalf("unexpected appeal result: %+v", appealResult)
	}
	delivered, err = dispatcher.DispatchOnce(ctx)
	if err != nil || delivered != 1 {
		t.Fatalf("dispatch restore: delivered=%d err=%v", delivered, err)
	}
	assertDeliveryStatus(t, ctx, appealResult.DecisionID, "delivered", 0)
	assertUserAccountState(t, ctx, accountID, "active", 3)
	assertUserEnforcementReceipt(t, ctx, appealResult.DecisionID, "restore", "active", 3)
	// Causal ordering is database-assigned. Wall-clock skew must not make an older
	// Suspend appear newer than the subsequently issued and delivered Restore.
	if _, err := accountEnforcementPGPool.Exec(ctx, `
UPDATE account_enforcement_delivery_receipts SET delivered_at='2030-01-01T00:00:00Z'
WHERE decision_id=$1`, moderationResult.DecisionID); err != nil {
		t.Fatal(err)
	}
	if _, err := accountEnforcementPGPool.Exec(ctx, `
UPDATE account_enforcement_delivery_receipts SET delivered_at='2000-01-01T00:00:00Z'
WHERE decision_id=$1`, appealResult.DecisionID); err != nil {
		t.Fatal(err)
	}

	// The old suspend decision is no longer the latest delivered action, so a stale appeal fails closed.
	staleAppeal := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/appeal",
		"operator-appeal", "open-stale-appeal-"+suffix, map[string]any{
			"caseId": "stale-appeal-" + suffix, "accountId": accountID,
			"sourceDecisionId": moderationResult.DecisionID,
			"intakeRef":        intakeRef,
			"evidenceRefs":     []string{"appeal-evidence"},
		})
	assertRuntimeErrorCode(t, staleAppeal, http.StatusConflict, "OPS.USER.account_enforcement_source_decision_conflict")

	// Concurrent distinct approvals use server-side locking/CAS; callers do not provide aggregate versions.
	recoveryCaseID := "moderation-recovery-" + suffix
	openedRecovery := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/moderation",
		"operator-opener", "open-recovery-"+suffix, map[string]any{
			"caseId": recoveryCaseID, "accountId": accountID,
			"policyRef": "policy/account-safety", "evidenceRefs": []string{"evidence-recovery"},
		})
	assertStatus(t, openedRecovery, http.StatusCreated)
	var wg sync.WaitGroup
	start := make(chan struct{})
	errorsByActor := make(chan error, 2)
	for index, actor := range []string{"concurrent-reviewer-1", "concurrent-reviewer-2"} {
		wg.Add(1)
		go func(index int, actor string) {
			defer wg.Done()
			<-start
			_, reviewErr := service.Review(ctx, application.ReviewCommand{
				CaseID: recoveryCaseID, Verdict: model.ReviewVerdictApprove,
				ActorID: actor, IdempotencyKey: fmt.Sprintf("concurrent-review-%d-%s", index, suffix),
			})
			errorsByActor <- reviewErr
		}(index, actor)
	}
	close(start)
	wg.Wait()
	close(errorsByActor)
	for reviewErr := range errorsByActor {
		if reviewErr != nil {
			t.Fatalf("concurrent review failed: %v", reviewErr)
		}
	}
	recoveryResult := getCaseResult(t, handler, recoveryCaseID, "operator-reader")
	if recoveryResult.Status != "approved" || recoveryResult.DecisionID == "" {
		t.Fatalf("concurrent approval did not issue decision: %+v", recoveryResult)
	}
	assertAtomicCounts(t, ctx, recoveryCaseID, 2, 1, 1)

	// Put the real UserAccount aggregate into a conflicting state through the
	// same authenticated HTTP boundary. The Product Ops suspend then receives a
	// real 409 from UserAccount and enters the terminal delivery path.
	applyUserSetupDecision(t, ctx, target, model.Decision{
		ID: "setup-suspend-" + suffix, CaseID: "setup-case-suspend-" + suffix,
		AccountID: accountID, Action: model.EnforcementActionSuspend,
		CaseRef:        "setup-case-suspend-" + suffix,
		DecisionDigest: strings.Repeat("a", 64), ApprovedAt: time.Now().UTC(),
	})
	assertUserAccountState(t, ctx, accountID, "suspended", 4)
	deadDispatcher := newTestDispatcher(t, store, target, "dispatcher-dead-"+suffix)
	delivered, err = deadDispatcher.DispatchOnce(ctx)
	if err != nil || delivered != 0 {
		t.Fatalf("permanent failure dispatch: delivered=%d err=%v", delivered, err)
	}
	// The first terminal failure belongs to generation zero. Only an explicit
	// RetryDelivery recovery advances the durable outbox to generation one.
	assertDeliveryStatus(t, ctx, recoveryResult.DecisionID, "dead_letter", 0)
	if err := deadDispatcher.CheckReadiness(ctx); err == nil {
		t.Fatal("terminal DLQ must fail readiness")
	}
	assertDeadLetterHasNoPIIColumns(t, ctx)

	retryResponse := performEmpty(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/"+recoveryCaseID+":retry-delivery",
		"operator-recovery", "retry-delivery-"+suffix)
	assertStatus(t, retryResponse, http.StatusOK)
	retryResult := decodeResult(t, retryResponse)
	if retryResult.DecisionID != recoveryResult.DecisionID || retryResult.DeliveryStatus != "pending" {
		t.Fatalf("retry changed decision or did not reset same outbox: before=%+v after=%+v", recoveryResult, retryResult)
	}
	retryReplay := performEmpty(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/"+recoveryCaseID+":retry-delivery",
		"operator-recovery", "retry-delivery-"+suffix)
	assertStatus(t, retryReplay, http.StatusOK)
	applyUserSetupDecision(t, ctx, target, model.Decision{
		ID: "setup-restore-" + suffix, CaseID: "setup-case-restore-" + suffix,
		AccountID: accountID, Action: model.EnforcementActionRestore,
		CaseRef:        "setup-case-restore-" + suffix,
		DecisionDigest: strings.Repeat("b", 64), ApprovedAt: time.Now().UTC(),
	})
	assertUserAccountState(t, ctx, accountID, "active", 5)
	delivered, err = deadDispatcher.DispatchOnce(ctx)
	if err != nil || delivered != 1 {
		t.Fatalf("recovered delivery: delivered=%d err=%v", delivered, err)
	}
	assertDeliveryStatus(t, ctx, recoveryResult.DecisionID, "delivered", 1)
	if err := deadDispatcher.CheckReadiness(ctx); err != nil {
		t.Fatalf("readiness after same-decision recovery: %v", err)
	}
	assertUserAccountState(t, ctx, accountID, "suspended", 6)
	assertStableRetryWire(t, ctx, recoveryResult.DecisionID)

	// Command receipts preserve the original non-PII result even after the aggregate
	// and delivery state advance. Current state remains available through GET.
	lateFirstApprovalReplay := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/"+moderationCaseID+":review",
		"operator-1", "review-moderation-1-"+suffix, map[string]any{"verdict": "approve"})
	assertStatus(t, lateFirstApprovalReplay, http.StatusOK)
	assertStableCommandResult(t, decodeResult(t, lateFirstApprovalReplay), firstApprovalResult)
	lateSecondApprovalReplay := performJSON(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/"+moderationCaseID+":review",
		"operator-2", "review-moderation-2-"+suffix, map[string]any{"verdict": "approve"})
	assertStatus(t, lateSecondApprovalReplay, http.StatusOK)
	assertStableCommandResult(t, decodeResult(t, lateSecondApprovalReplay), moderationResult)
	lateRetryReplay := performEmpty(t, handler, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/"+recoveryCaseID+":retry-delivery",
		"operator-recovery", "retry-delivery-"+suffix)
	assertStatus(t, lateRetryReplay, http.StatusOK)
	assertStableCommandResult(t, decodeResult(t, lateRetryReplay), retryResult)
}

type caseResult struct {
	CaseID         string `json:"caseId"`
	Status         string `json:"status"`
	Version        int64  `json:"version"`
	ApprovalCount  int    `json:"approvalCount"`
	DecisionID     string `json:"decisionId"`
	DeliveryStatus string `json:"deliveryStatus"`
}

func performJSON(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	actor string,
	idempotencyKey string,
	payload any,
) *httptest.ResponseRecorder {
	t.Helper()
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request = request.WithContext(operatorContext(request.Context(), actor))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func performEmpty(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	actor string,
	idempotencyKey string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, nil)
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request = request.WithContext(operatorContext(request.Context(), actor))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func operatorContext(ctx context.Context, actor string) context.Context {
	return rtauth.WithPrincipal(ctx, rtauth.Principal{
		Claims: rtauth.Claims{Roles: []string{"operator"}},
		Actor:  operation.ActorContext{AccountID: actor},
	})
}

func assertStatus(t *testing.T, response *httptest.ResponseRecorder, expected int) {
	t.Helper()
	if response.Code != expected {
		t.Fatalf("status=%d want=%d body=%s", response.Code, expected, response.Body.String())
	}
}

func assertRuntimeErrorCode(t *testing.T, response *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	assertStatus(t, response, status)
	var payload struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload.Code != code {
		t.Fatalf("error code=%q want=%q body=%s", payload.Code, code, response.Body.String())
	}
}

func decodeResult(t *testing.T, response *httptest.ResponseRecorder) caseResult {
	t.Helper()
	var result caseResult
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func assertStableCommandResult(t *testing.T, actual, expected caseResult) {
	t.Helper()
	if actual != expected {
		t.Fatalf("command replay changed immutable result: actual=%+v expected=%+v", actual, expected)
	}
}

func getCaseResult(t *testing.T, handler http.Handler, caseID string, actor string) caseResult {
	t.Helper()
	request := httptest.NewRequest(http.MethodGet,
		"/control-plane/product/account-enforcement-cases/"+caseID, nil)
	request = request.WithContext(operatorContext(request.Context(), actor))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	assertStatus(t, recorder, http.StatusOK)
	return decodeResult(t, recorder)
}

func cloneMap(source map[string]any) map[string]any {
	out := make(map[string]any, len(source))
	for key, value := range source {
		out[key] = value
	}
	return out
}

func assertAtomicCounts(t *testing.T, ctx context.Context, caseID string, reviews, decisions, outbox int) {
	t.Helper()
	var reviewCount, decisionCount, outboxCount int
	if err := accountEnforcementPGPool.QueryRow(ctx,
		`SELECT COUNT(*) FROM account_enforcement_case_reviews WHERE case_id=$1`, caseID).Scan(&reviewCount); err != nil {
		t.Fatal(err)
	}
	if err := accountEnforcementPGPool.QueryRow(ctx,
		`SELECT COUNT(*) FROM account_enforcement_decisions WHERE case_id=$1`, caseID).Scan(&decisionCount); err != nil {
		t.Fatal(err)
	}
	if err := accountEnforcementPGPool.QueryRow(ctx, `
SELECT COUNT(*) FROM account_enforcement_delivery_outbox o
JOIN account_enforcement_decisions d ON d.decision_id=o.decision_id
WHERE d.case_id=$1`, caseID).Scan(&outboxCount); err != nil {
		t.Fatal(err)
	}
	if reviewCount != reviews || decisionCount != decisions || outboxCount != outbox {
		t.Fatalf("atomic counts reviews=%d/%d decisions=%d/%d outbox=%d/%d",
			reviewCount, reviews, decisionCount, decisions, outboxCount, outbox)
	}
}

func assertDeliveryStatus(t *testing.T, ctx context.Context, decisionID, status string, generation int) {
	t.Helper()
	var actual string
	var retryGeneration int
	if err := accountEnforcementPGPool.QueryRow(ctx, `
SELECT status, retry_generation FROM account_enforcement_delivery_outbox WHERE decision_id=$1`, decisionID).
		Scan(&actual, &retryGeneration); err != nil {
		t.Fatal(err)
	}
	if actual != status || retryGeneration != generation {
		t.Fatalf("delivery status=%s generation=%d want=%s/%d", actual, retryGeneration, status, generation)
	}
}

func assertDeadLetterHasNoPIIColumns(t *testing.T, ctx context.Context) {
	t.Helper()
	rows, err := accountEnforcementPGPool.Query(ctx, `
SELECT column_name FROM information_schema.columns
WHERE table_schema='public' AND table_name='account_enforcement_delivery_dead_letters'
ORDER BY ordinal_position`)
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()
	var columns []string
	for rows.Next() {
		var column string
		if err := rows.Scan(&column); err != nil {
			t.Fatal(err)
		}
		columns = append(columns, column)
	}
	expected := []string{"decision_id", "retry_generation", "error_class", "attempt_count", "failed_at"}
	if strings.Join(columns, ",") != strings.Join(expected, ",") {
		t.Fatalf("terminal DLQ columns=%v, want only non-PII %v", columns, expected)
	}
}

func newTestDispatcher(
	t *testing.T,
	store *persistence.PostgresStore,
	target *accountenforcementuser.HTTPClient,
	owner string,
) *application.Dispatcher {
	t.Helper()
	dispatcher, err := application.NewDispatcher(store, target, nil, application.DispatcherConfig{
		Owner: owner, PollInterval: time.Second, LeaseDuration: 5 * time.Second,
		RequestTimeout: 2 * time.Second, InitialBackoff: time.Millisecond,
		MaxBackoff: time.Second, MaxPendingAge: time.Minute, MaxAttempts: 3, BatchSize: 10,
	})
	if err != nil {
		t.Fatal(err)
	}
	return dispatcher
}

func applyUserSetupDecision(
	t *testing.T,
	ctx context.Context,
	target *accountenforcementuser.HTTPClient,
	decision model.Decision,
) {
	t.Helper()
	receipt, err := target.Apply(ctx, decision)
	if err != nil {
		t.Fatalf("apply real UserAccount setup decision: %v", err)
	}
	if receipt.DecisionID != decision.ID || receipt.IdempotentReplay {
		t.Fatalf("unexpected UserAccount setup receipt: %+v", receipt)
	}
}

func assertUserAccountState(
	t *testing.T,
	ctx context.Context,
	accountID string,
	expectedState string,
	expectedEpoch int64,
) {
	t.Helper()
	var state string
	var epoch int64
	if err := accountEnforcementPGPool.QueryRow(ctx, `
SELECT account_state, auth_epoch FROM user_profiles WHERE user_id=$1`, accountID).
		Scan(&state, &epoch); err != nil {
		t.Fatal(err)
	}
	if state != expectedState || epoch != expectedEpoch {
		t.Fatalf("UserAccount state=%s epoch=%d want=%s/%d",
			state, epoch, expectedState, expectedEpoch)
	}
}

func assertUserEnforcementReceipt(
	t *testing.T,
	ctx context.Context,
	decisionID string,
	expectedAction string,
	expectedState string,
	expectedEpoch int64,
) {
	t.Helper()
	var action, state string
	var epoch int64
	if err := accountEnforcementPGPool.QueryRow(ctx, `
SELECT action, account_state, auth_epoch
FROM user_account_enforcement_receipts
WHERE decision_id=$1`, decisionID).Scan(&action, &state, &epoch); err != nil {
		t.Fatal(err)
	}
	if action != expectedAction || state != expectedState || epoch != expectedEpoch {
		t.Fatalf("UserAccount receipt action=%s state=%s epoch=%d want=%s/%s/%d",
			action, state, epoch, expectedAction, expectedState, expectedEpoch)
	}
}

func assertStableRetryWire(t *testing.T, ctx context.Context, decisionID string) {
	t.Helper()
	var (
		productAccountID string
		productAction    string
		productCaseRef   string
		productDigest    string
		userAccountID    string
		userAction       string
		userCaseRef      string
		userDigest       string
		attempts         int
		retryGeneration  int
		deadLetterCount  int
	)
	if err := accountEnforcementPGPool.QueryRow(ctx, `
SELECT account_id, action, case_ref, decision_digest
FROM account_enforcement_decisions WHERE decision_id=$1`, decisionID).
		Scan(&productAccountID, &productAction, &productCaseRef, &productDigest); err != nil {
		t.Fatal(err)
	}
	if err := accountEnforcementPGPool.QueryRow(ctx, `
SELECT account_id, action, case_ref, decision_digest
FROM user_account_enforcement_receipts WHERE decision_id=$1`, decisionID).
		Scan(&userAccountID, &userAction, &userCaseRef, &userDigest); err != nil {
		t.Fatal(err)
	}
	if err := accountEnforcementPGPool.QueryRow(ctx, `
SELECT attempts, retry_generation
FROM account_enforcement_delivery_outbox WHERE decision_id=$1`, decisionID).
		Scan(&attempts, &retryGeneration); err != nil {
		t.Fatal(err)
	}
	if err := accountEnforcementPGPool.QueryRow(ctx, `
SELECT COUNT(*) FROM account_enforcement_delivery_dead_letters
WHERE decision_id=$1 AND retry_generation=0 AND attempt_count=1`, decisionID).
		Scan(&deadLetterCount); err != nil {
		t.Fatal(err)
	}
	if attempts != 0 || retryGeneration != 1 || deadLetterCount != 1 ||
		productAccountID != userAccountID || productAction != userAction ||
		productCaseRef != userCaseRef || productDigest != userDigest {
		t.Fatalf(
			"retry wire drift: attempts=%d generation=%d deadLetters=%d product=%q/%q/%q/%q user=%q/%q/%q/%q",
			attempts,
			retryGeneration,
			deadLetterCount,
			productAccountID,
			productAction,
			productCaseRef,
			productDigest,
			userAccountID,
			userAction,
			userCaseRef,
			userDigest,
		)
	}
}
