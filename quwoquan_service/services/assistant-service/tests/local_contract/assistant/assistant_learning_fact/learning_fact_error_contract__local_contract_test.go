// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
// 错误契约语义双向锁：AssistantLearningFact errors.yaml 声明的错误码由真实触发条件
// 经 HTTP 边界发射，并断言 canonical code 与 http_status。
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	learninghttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/adapters/inbound/http"
	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
)

type learningFactErrorContractStore struct{ appendErr error }

func (store learningFactErrorContractStore) Append(
	context.Context,
	learningmodel.Fact,
) (learningmodel.Receipt, error) {
	if store.appendErr != nil {
		return learningmodel.Receipt{}, store.appendErr
	}
	return learningmodel.Receipt{EventID: "evt-error-contract", Accepted: true}, nil
}

type learningFactErrorContractOwners struct {
	owner rundomain.Owner
	found bool
	err   error
}

func (owners learningFactErrorContractOwners) ResolveRunOwner(
	context.Context,
	string,
) (rundomain.Owner, bool, error) {
	return owners.owner, owners.found, owners.err
}

func validLearningFactBody() map[string]any {
	return map[string]any{
		"eventId":          "evt-error-contract",
		"factType":         "user_feedback",
		"assistantTurnId":  "turn-error-contract",
		"referralSource":   "assistant_session",
		"domainId":         "assistant",
		"feedbackType":     "thumbs_up",
		"trainingEligible": false,
		"occurredAt":       "2026-08-13T09:00:00Z",
	}
}

func TestLearningFactHTTPEmitsCanonicalErrorContract(t *testing.T) {
	t.Parallel()
	trustedOwner := rundomain.Owner{
		UserID:    "account-learning-error",
		PersonaID: "persona-learning-error",
	}
	tests := []struct {
		name          string
		store         learningFactErrorContractStore
		owners        learningFactErrorContractOwners
		body          map[string]any
		rawBody       string
		withPrincipal bool
		wantStatus    int
		wantCode      string
	}{
		{
			name:          "missing persona principal is learning_fact_unauthorized",
			owners:        learningFactErrorContractOwners{owner: trustedOwner, found: true},
			body:          validLearningFactBody(),
			withPrincipal: false,
			wantStatus:    http.StatusUnauthorized,
			wantCode:      "ASSISTANT.USER.learning_fact_unauthorized",
		},
		{
			name:          "missing trainingEligible is learning_fact_invalid",
			owners:        learningFactErrorContractOwners{owner: trustedOwner, found: true},
			rawBody:       `{"eventId":"evt-invalid","factType":"user_feedback"}`,
			withPrincipal: true,
			wantStatus:    http.StatusBadRequest,
			wantCode:      "ASSISTANT.USER.learning_fact_invalid",
		},
		{
			name:          "unknown run is learning_fact_run_not_found",
			owners:        learningFactErrorContractOwners{found: false},
			body:          validLearningFactBody(),
			withPrincipal: true,
			wantStatus:    http.StatusNotFound,
			wantCode:      "ASSISTANT.USER.learning_fact_run_not_found",
		},
		{
			name: "foreign run owner is learning_fact_owner_mismatch",
			owners: learningFactErrorContractOwners{
				owner: rundomain.Owner{
					UserID:    "another-account",
					PersonaID: "another-persona",
				},
				found: true,
			},
			body:          validLearningFactBody(),
			withPrincipal: true,
			wantStatus:    http.StatusForbidden,
			wantCode:      "ASSISTANT.USER.learning_fact_owner_mismatch",
		},
		{
			name: "duplicate identity with different payload is learning_fact_identity_conflict",
			store: learningFactErrorContractStore{
				appendErr: fmt.Errorf(
					"%w: event evt-error-contract already stores a different fact",
					learningapplication.ErrIdentityConflict,
				),
			},
			owners:        learningFactErrorContractOwners{owner: trustedOwner, found: true},
			body:          validLearningFactBody(),
			withPrincipal: true,
			wantStatus:    http.StatusConflict,
			wantCode:      "ASSISTANT.USER.learning_fact_identity_conflict",
		},
		{
			name: "run owner storage failure is learning_fact_sink_unavailable",
			owners: learningFactErrorContractOwners{
				err: errors.New("mongo topology closed"),
			},
			body:          validLearningFactBody(),
			withPrincipal: true,
			wantStatus:    http.StatusServiceUnavailable,
			wantCode:      "ASSISTANT.SYSTEM.learning_fact_sink_unavailable",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			mux := http.NewServeMux()
			learninghttp.NewHandler(
				learningapplication.NewAssistantLearningFactAppender(
					test.store,
					test.owners,
					func() time.Time {
						return time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
					},
				),
			).RegisterRoutes(mux)
			payload := []byte(test.rawBody)
			if test.body != nil {
				encoded, err := json.Marshal(test.body)
				if err != nil {
					t.Fatalf("marshal learning fact body: %v", err)
				}
				payload = encoded
			}
			request := httptest.NewRequest(
				http.MethodPost,
				"/assistant/learning/facts",
				bytes.NewReader(payload),
			)
			request.Header.Set("Content-Type", "application/json")
			if test.withPrincipal {
				request = request.WithContext(rtauth.WithPrincipal(
					request.Context(),
					rtauth.Principal{Actor: operation.ActorContext{
						AccountID: "account-learning-error",
						PersonaID: "persona-learning-error",
					}},
				))
			}
			recorder := httptest.NewRecorder()
			mux.ServeHTTP(recorder, request)
			assertLearningFactWireError(t, recorder, test.wantStatus, test.wantCode)
		})
	}
}

func TestLearningOpsSummaryWithoutQueryServiceIsLearningOpsUnavailable(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	learninghttp.NewHandler(
		learningapplication.NewAssistantLearningFactAppender(
			learningFactErrorContractStore{},
			learningFactErrorContractOwners{},
			nil,
		),
	).RegisterRoutes(mux)
	request := httptest.NewRequest(
		http.MethodGet,
		"/assistant/ops/learning-summary",
		nil,
	)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "operator-learning-error",
		}},
	))
	recorder := httptest.NewRecorder()
	mux.ServeHTTP(recorder, request)
	assertLearningFactWireError(
		t,
		recorder,
		http.StatusServiceUnavailable,
		"ASSISTANT.SYSTEM.learning_ops_unavailable",
	)
}

func assertLearningFactWireError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	wantStatus int,
	wantCode string,
) {
	t.Helper()
	var response struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response %q: %v", recorder.Body.String(), err)
	}
	if recorder.Code != wantStatus || response.Code != wantCode {
		t.Fatalf(
			"response=%d/%s, want %d/%s body=%s",
			recorder.Code,
			response.Code,
			wantStatus,
			wantCode,
			recorder.Body.String(),
		)
	}
}
