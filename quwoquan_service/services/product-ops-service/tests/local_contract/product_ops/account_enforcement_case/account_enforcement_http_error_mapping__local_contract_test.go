// AccountEnforcementCase HTTP 边界的错误码契约：errors.yaml 声明的对象错误
// 必须经 runtime error envelope 以稳定 code 发射。
//
// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	enforcementhttp "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/adapters/inbound/http"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
)

func TestAccountEnforcementHTTPBoundaryMapsDeclaredUserErrorCodes(t *testing.T) {
	now := time.Date(2026, 8, 10, 9, 0, 0, 0, time.UTC)
	opened, err := model.OpenModeration(model.OpenModerationParams{
		CaseID: "moderation-error-mapping", AccountID: "account-error-mapping",
		PolicyRef: "policy/account-safety", EvidenceRefs: []string{"evidence-1"},
		OpenedBy: "operator-opener", OpenedAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	reviewed, _, _, err := opened.Review(
		"operator-1",
		model.ReviewVerdictApprove,
		now.Add(time.Minute),
	)
	if err != nil {
		t.Fatal(err)
	}
	store := &errorMappingCaseStore{current: reviewed}
	mux := newEnforcementErrorMappingMux(store)

	invalidBody := performEnforcementRequest(
		t, mux, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/moderation",
		"operator-opener", "open-invalid-body", "{",
	)
	assertEnforcementErrorCode(
		t,
		invalidBody,
		http.StatusBadRequest,
		"OPS.USER.account_enforcement_case_invalid_argument",
	)

	missingCase := performEnforcementRequest(
		t, mux, http.MethodGet,
		"/control-plane/product/account-enforcement-cases/missing-case",
		"operator-opener", "", "",
	)
	assertEnforcementErrorCode(
		t,
		missingCase,
		http.StatusNotFound,
		"OPS.USER.account_enforcement_case_not_found",
	)

	sameReviewer := performEnforcementRequest(
		t, mux, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/moderation-error-mapping:review",
		"operator-1", "review-same-reviewer", `{"verdict":"approve"}`,
	)
	assertEnforcementErrorCode(
		t,
		sameReviewer,
		http.StatusConflict,
		"OPS.USER.account_enforcement_review_conflict",
	)
}

func TestAccountEnforcementHTTPBoundaryMapsStorageFailureCodes(t *testing.T) {
	readStore := &errorMappingCaseStore{loadErr: errors.New("postgres read timeout")}
	readMux := newEnforcementErrorMappingMux(readStore)
	readFailure := performEnforcementRequest(
		t, readMux, http.MethodGet,
		"/control-plane/product/account-enforcement-cases/any-case",
		"operator-opener", "", "",
	)
	assertEnforcementErrorCode(
		t,
		readFailure,
		http.StatusInternalServerError,
		"OPS.SYSTEM.account_enforcement_case_storage_read_failed",
	)

	writeStore := &errorMappingCaseStore{commitOpenErr: errors.New("postgres write timeout")}
	writeMux := newEnforcementErrorMappingMux(writeStore)
	writeFailure := performEnforcementRequest(
		t, writeMux, http.MethodPost,
		"/control-plane/product/account-enforcement-cases/moderation",
		"operator-opener", "open-write-failure",
		`{"caseId":"moderation-write-failure","accountId":"account-1","policyRef":"policy/account-safety","evidenceRefs":["evidence-1"]}`,
	)
	assertEnforcementErrorCode(
		t,
		writeFailure,
		http.StatusInternalServerError,
		"OPS.SYSTEM.account_enforcement_case_storage_write_failed",
	)
}

func newEnforcementErrorMappingMux(store ports.CaseStore) *http.ServeMux {
	mux := http.NewServeMux()
	enforcementhttp.NewHandler(application.NewService(store, nil, nil)).Register(mux)
	return mux
}

func performEnforcementRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	target string,
	actorID string,
	idempotencyKey string,
	body string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, target, strings.NewReader(body))
	request.Header.Set("X-Request-Id", "enforcement-error-mapping-request")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{AccountID: actorID}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertEnforcementErrorCode(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	status int,
	code string,
) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("status=%d want=%d body=%s", recorder.Code, status, recorder.Body.String())
	}
	var response struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response %s: %v", recorder.Body.String(), err)
	}
	if response.Code != code {
		t.Fatalf("code=%q want=%q body=%s", response.Code, code, recorder.Body.String())
	}
}

// errorMappingCaseStore 是对象级 typed double：按需注入读/写存储故障,
// 其余语义与 canonical CaseStore 对齐。
type errorMappingCaseStore struct {
	current       model.Case
	loadErr       error
	commitOpenErr error
}

func (*errorMappingCaseStore) Replay(
	context.Context,
	string,
	string,
) (ports.CaseSnapshot, bool, error) {
	return ports.CaseSnapshot{}, false, nil
}

func (store *errorMappingCaseStore) CommitOpen(
	_ context.Context,
	current model.Case,
	_ ports.CommandReceipt,
) (ports.CaseSnapshot, error) {
	if store.commitOpenErr != nil {
		return ports.CaseSnapshot{}, store.commitOpenErr
	}
	return ports.CaseSnapshot{Case: current}, nil
}

func (store *errorMappingCaseStore) Load(
	_ context.Context,
	caseID string,
) (model.Case, error) {
	if store.loadErr != nil {
		return model.Case{}, store.loadErr
	}
	if caseID != store.current.ID {
		return model.Case{}, model.ErrCaseNotFound
	}
	return store.current, nil
}

func (*errorMappingCaseStore) CommitReview(
	context.Context,
	int64,
	model.Case,
	model.Review,
	*model.Decision,
	ports.CommandReceipt,
) (ports.CaseSnapshot, error) {
	return ports.CaseSnapshot{}, errors.New("unexpected CommitReview")
}

func (*errorMappingCaseStore) RecoverDelivery(
	context.Context,
	string,
	ports.CommandReceipt,
	time.Time,
) (ports.CaseSnapshot, error) {
	return ports.CaseSnapshot{}, model.ErrCaseNotFound
}

var _ ports.CaseStore = (*errorMappingCaseStore)(nil)
