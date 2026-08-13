// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md#gwt-001
// 错误契约语义双向锁：每个 errors.yaml 声明的 AssistantPolicyRollout 错误码都必须
// 由真实触发条件经 HTTP 边界发射，并断言 canonical code 与 http_status。
package assistant_policy_rollout_test

import (
	"bytes"
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
	rollouthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
)

// rolloutErrorContractStore 是对象级 typed double：按场景注入当前聚合或存储失败。
type rolloutErrorContractStore struct {
	current   model.Rollout
	found     bool
	getErr    error
	replayErr error
}

func (store *rolloutErrorContractStore) Get(
	_ context.Context,
	_ string,
) (model.Rollout, bool, error) {
	return store.current, store.found, store.getErr
}

func (store *rolloutErrorContractStore) GetCommandResult(
	_ context.Context,
	_ string,
	_ string,
	_ string,
) (model.Rollout, bool, error) {
	return model.Rollout{}, false, store.replayErr
}

func (store *rolloutErrorContractStore) Commit(
	_ context.Context,
	_ string,
	_ string,
	_ int,
	next model.Rollout,
	_ string,
) (model.Rollout, bool, error) {
	return next, false, nil
}

func TestPolicyRolloutHTTPEmitsCanonicalErrorContract(t *testing.T) {
	t.Parallel()
	activeRollout := model.Rollout{
		PolicyID: "assistant-default",
		Revision: 1,
		Status:   "active",
		BucketDefinitions: []model.BucketDefinition{
			{Cohort: "all", WeightBasisPoints: 10000},
		},
		Assignments: []model.CohortAssignment{
			{Cohort: "all", ReleaseDigest: releaseDigestOne},
		},
	}
	activateBody := map[string]any{
		"revision": 1,
		"bucketDefinitions": []map[string]any{
			{"cohort": "all", "weightBasisPoints": 10000},
		},
		"assignments": []map[string]any{
			{"cohort": "all", "releaseDigest": releaseDigestTwo},
		},
	}
	tests := []struct {
		name       string
		store      *rolloutErrorContractStore
		releases   application.ReleaseReader
		path       string
		rawBody    string
		body       map[string]any
		wantStatus int
		wantCode   string
	}{
		{
			name:       "malformed activate body is policy_rollout_invalid",
			store:      &rolloutErrorContractStore{},
			releases:   releaseReader{},
			path:       "/internal/assistant/policy-rollouts/assistant-default/activate",
			rawBody:    "{malformed",
			wantStatus: http.StatusBadRequest,
			wantCode:   "ASSISTANT.USER.policy_rollout_invalid",
		},
		{
			name:  "activate with absent release is policy_rollout_release_not_found",
			store: &rolloutErrorContractStore{},
			releases: releaseReader{
				releaseDigestOne: {},
			},
			path: "/internal/assistant/policy-rollouts/assistant-default/activate",
			body: map[string]any{
				"revision": 0,
				"bucketDefinitions": []map[string]any{
					{"cohort": "all", "weightBasisPoints": 10000},
				},
				"assignments": []map[string]any{
					{"cohort": "all", "releaseDigest": missingDigest},
				},
			},
			wantStatus: http.StatusNotFound,
			wantCode:   "ASSISTANT.USER.policy_rollout_release_not_found",
		},
		{
			name:       "rollback without rollout is policy_rollout_not_found",
			store:      &rolloutErrorContractStore{},
			releases:   releaseReader{},
			path:       "/internal/assistant/policy-rollouts/assistant-default/rollback",
			body:       map[string]any{"revision": 1},
			wantStatus: http.StatusNotFound,
			wantCode:   "ASSISTANT.USER.policy_rollout_not_found",
		},
		{
			name: "rollback without previous mapping is policy_rollout_no_previous_mapping",
			store: &rolloutErrorContractStore{
				current: activeRollout,
				found:   true,
			},
			releases:   releaseReader{},
			path:       "/internal/assistant/policy-rollouts/assistant-default/rollback",
			body:       map[string]any{"revision": 1},
			wantStatus: http.StatusConflict,
			wantCode:   "ASSISTANT.USER.policy_rollout_no_previous_mapping",
		},
		{
			name: "stale activate revision is policy_rollout_revision_conflict",
			store: &rolloutErrorContractStore{
				current: activeRollout,
				found:   true,
			},
			releases: releaseReader{
				releaseDigestOne: {},
				releaseDigestTwo: {},
			},
			path: "/internal/assistant/policy-rollouts/assistant-default/activate",
			body: map[string]any{
				"revision": 7,
				"bucketDefinitions": []map[string]any{
					{"cohort": "all", "weightBasisPoints": 10000},
				},
				"assignments": []map[string]any{
					{"cohort": "all", "releaseDigest": releaseDigestTwo},
				},
			},
			wantStatus: http.StatusConflict,
			wantCode:   "ASSISTANT.USER.policy_rollout_revision_conflict",
		},
		{
			name: "reused command with different payload is policy_rollout_idempotency_conflict",
			store: &rolloutErrorContractStore{
				replayErr: model.ErrIdempotencyConflict,
			},
			releases:   releaseReader{releaseDigestTwo: {}},
			path:       "/internal/assistant/policy-rollouts/assistant-default/activate",
			body:       activateBody,
			wantStatus: http.StatusConflict,
			wantCode:   "ASSISTANT.USER.policy_rollout_idempotency_conflict",
		},
		{
			name: "storage failure is policy_rollout_storage_unavailable",
			store: &rolloutErrorContractStore{
				getErr: errors.New("mongo topology closed"),
			},
			releases:   releaseReader{releaseDigestTwo: {}},
			path:       "/internal/assistant/policy-rollouts/assistant-default/activate",
			body:       activateBody,
			wantStatus: http.StatusServiceUnavailable,
			wantCode:   "ASSISTANT.SYSTEM.policy_rollout_storage_unavailable",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			mux := http.NewServeMux()
			rollouthttp.NewHandler(application.NewService(
				test.store,
				test.releases,
				func() time.Time {
					return time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
				},
			)).RegisterRoutes(mux)
			payload := []byte(test.rawBody)
			if test.body != nil {
				encoded, err := json.Marshal(test.body)
				if err != nil {
					t.Fatalf("marshal request: %v", err)
				}
				payload = encoded
			}
			request := httptest.NewRequest(
				http.MethodPost,
				test.path,
				bytes.NewReader(payload),
			)
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("Idempotency-Key", "policy-rollout-error-contract")
			request = request.WithContext(rtauth.WithPrincipal(
				request.Context(),
				rtauth.Principal{Actor: operation.ActorContext{
					AccountID: "service:policy-publisher",
				}},
			))
			recorder := httptest.NewRecorder()
			mux.ServeHTTP(recorder, request)
			assertRolloutWireError(t, recorder, test.wantStatus, test.wantCode)
		})
	}
}

func assertRolloutWireError(
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
	if recorder.Code != wantStatus || strings.TrimSpace(response.Code) != wantCode {
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
