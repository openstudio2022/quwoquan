// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md#gwt-001
// 错误契约语义双向锁：AssistantPolicyRelease errors.yaml 声明的每个错误码都由真实
// 触发条件经 HTTP 边界发射，并断言 canonical code 与 http_status。
package assistant_policy_release_test

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

	releasehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
)

// releaseErrorContractStore 是对象级 typed double：按场景注入幂等冲突或存储失败。
type releaseErrorContractStore struct {
	stageErr error
}

func (store *releaseErrorContractStore) Stage(
	_ context.Context,
	release model.Release,
	_ string,
) (model.Release, bool, error) {
	if store.stageErr != nil {
		return model.Release{}, false, store.stageErr
	}
	return release, false, nil
}

func (store *releaseErrorContractStore) Get(
	_ context.Context,
	_ string,
	_ string,
) (model.Release, bool, error) {
	return model.Release{}, false, nil
}

func stageablePolicyRelease(t *testing.T) model.Release {
	t.Helper()
	input := model.Release{
		PolicyID:          "assistant-default",
		ReleaseDigest:     "pending",
		DefaultTemplateID: "default",
		Templates: []model.Template{{
			TemplateID:      "default",
			SkillID:         "assistant.general",
			DomainID:        "assistant",
			PromptPolicy:    "answer with grounded citations",
			AllowedTools:    []string{"search"},
			SearchIntensity: "medium",
		}},
		LearningContextPolicy: model.LearningContextPolicy{
			Enabled:                true,
			AllowedSignals:         []string{"feedback_counts"},
			AllowedMetricIDs:       []string{"turn_completion"},
			AllowedReasonCodes:     []string{"clear"},
			MinimumFeedbackSamples: 3,
			WindowDays:             30,
		},
	}
	digest, err := model.Digest(input)
	if err != nil {
		t.Fatalf("digest stageable release: %v", err)
	}
	input.ReleaseDigest = digest
	return input
}

func TestPolicyReleaseHTTPEmitsCanonicalErrorContract(t *testing.T) {
	t.Parallel()
	valid := stageablePolicyRelease(t)
	tampered := valid
	tampered.ReleaseDigest = strings.Repeat("f", 64)
	tests := []struct {
		name       string
		store      *releaseErrorContractStore
		rawBody    string
		body       *model.Release
		wantStatus int
		wantCode   string
	}{
		{
			name:       "malformed stage body is policy_release_invalid",
			store:      &releaseErrorContractStore{},
			rawBody:    "{malformed",
			wantStatus: http.StatusBadRequest,
			wantCode:   "ASSISTANT.USER.policy_release_invalid",
		},
		{
			name:       "tampered digest is policy_release_digest_mismatch",
			store:      &releaseErrorContractStore{},
			body:       &tampered,
			wantStatus: http.StatusBadRequest,
			wantCode:   "ASSISTANT.USER.policy_release_digest_mismatch",
		},
		{
			name: "reused command with different payload is policy_release_idempotency_conflict",
			store: &releaseErrorContractStore{
				stageErr: model.ErrIdempotencyConflict,
			},
			body:       &valid,
			wantStatus: http.StatusConflict,
			wantCode:   "ASSISTANT.USER.policy_release_idempotency_conflict",
		},
		{
			name: "storage failure is policy_release_storage_unavailable",
			store: &releaseErrorContractStore{
				stageErr: errors.New("mongo topology closed"),
			},
			body:       &valid,
			wantStatus: http.StatusServiceUnavailable,
			wantCode:   "ASSISTANT.SYSTEM.policy_release_storage_unavailable",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			mux := http.NewServeMux()
			releasehttp.NewHandler(application.NewService(
				test.store,
				func() time.Time {
					return time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
				},
			)).RegisterRoutes(mux)
			payload := []byte(test.rawBody)
			if test.body != nil {
				encoded, err := json.Marshal(test.body)
				if err != nil {
					t.Fatalf("marshal release: %v", err)
				}
				payload = encoded
			}
			request := httptest.NewRequest(
				http.MethodPost,
				"/internal/assistant/policy-releases",
				bytes.NewReader(payload),
			)
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("Idempotency-Key", "policy-release-error-contract")
			recorder := httptest.NewRecorder()
			mux.ServeHTTP(recorder, request)
			var response struct {
				Code string `json:"code"`
			}
			if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
				t.Fatalf("decode error response %q: %v", recorder.Body.String(), err)
			}
			if recorder.Code != test.wantStatus || response.Code != test.wantCode {
				t.Fatalf(
					"response=%d/%s, want %d/%s body=%s",
					recorder.Code,
					response.Code,
					test.wantStatus,
					test.wantCode,
					recorder.Body.String(),
				)
			}
		})
	}
}
