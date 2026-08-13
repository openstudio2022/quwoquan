// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-004
// 错误契约语义双向锁：public web 探索的 errors.yaml 错误码由真实依赖失败注入触发，
// 并断言 canonical code 与失败语义。
package assistant_run

import (
	"context"
	"errors"
	"testing"

	publicwebtool "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/outbound/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	publicweb "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

type failingBudgetGate struct{ err error }

func (gate failingBudgetGate) ReserveFetch(
	context.Context,
	string,
	int64,
) (publicweb.BudgetReservation, error) {
	return nil, gate.err
}

type failingNetworkFetcher struct{}

func (failingNetworkFetcher) Fetch(
	context.Context,
	publicweb.NetworkRequest,
) (publicweb.NetworkResult, error) {
	return publicweb.NetworkResult{}, errors.New("upstream connection reset")
}

type failingEvidenceStore struct{ recordingEvidenceStore }

func (*failingEvidenceStore) CommitEvidence(
	context.Context,
	publicweb.EvidenceRecord,
) error {
	return errors.New("evidence store write failed")
}

func TestWebOpenEmitsCanonicalPublicWebFailureCodes(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		service  *publicweb.Service
		wantCode string
	}{
		{
			name: "exhausted run budget is web_budget_exhausted",
			service: publicweb.NewService(
				fixedTargetResolver{},
				longDocumentFetcher{body: []byte("evidence")},
				&recordingEvidenceStore{},
				failingBudgetGate{err: publicweb.ErrBudgetExhausted},
				publicweb.DefaultDocumentParser(),
			),
			wantCode: "ASSISTANT.MIDDLEWARE.web_budget_exhausted",
		},
		{
			name: "budget ledger outage is web_budget_unavailable",
			service: publicweb.NewService(
				fixedTargetResolver{},
				longDocumentFetcher{body: []byte("evidence")},
				&recordingEvidenceStore{},
				failingBudgetGate{err: errors.New("budget ledger unreachable")},
				publicweb.DefaultDocumentParser(),
			),
			wantCode: "ASSISTANT.SYSTEM.web_budget_unavailable",
		},
		{
			name: "evidence commit failure is web_evidence_unavailable",
			service: publicweb.NewService(
				fixedTargetResolver{},
				longDocumentFetcher{body: []byte("evidence")},
				&failingEvidenceStore{},
				publicweb.NewRunBudgetGate(publicweb.RunBudgetLimits{
					MaxPages: 2, MaxBytes: 2 << 20,
				}),
				publicweb.DefaultDocumentParser(),
			),
			wantCode: "ASSISTANT.SYSTEM.web_evidence_unavailable",
		},
		{
			name: "network fetch failure is web_fetch_unavailable",
			service: publicweb.NewService(
				fixedTargetResolver{},
				failingNetworkFetcher{},
				&recordingEvidenceStore{},
				publicweb.NewRunBudgetGate(publicweb.RunBudgetLimits{
					MaxPages: 2, MaxBytes: 2 << 20,
				}),
				publicweb.DefaultDocumentParser(),
			),
			wantCode: "ASSISTANT.MIDDLEWARE.web_fetch_unavailable",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			registry := toolpkg.BaseRegistry()
			registry.Register(
				toolpkg.WebOpenMetadata(),
				publicwebtool.OpenHandler(test.service),
			)
			execution, err := (orchestration.DefaultToolCoordinator{
				Registry: registry,
			}).Execute(t.Context(), orchestration.ToolRequest{
				Turn: assistant.AssistantTurn{
					TurnID: "run_web_failure",
					Input:  assistant.AssistantTurnInput{Text: "open"},
				},
				Skill:    orchestration.SkillSelection{SkillID: "knowledge_general"},
				ToolName: "web_open",
				Input: map[string]any{
					"target": map[string]any{
						"kind":  "url",
						"value": "https://example.com",
					},
				},
			})
			if err != nil {
				t.Fatalf("execute web_open: %v", err)
			}
			if execution.Failure == nil || execution.Failure.Code != test.wantCode {
				t.Fatalf("failure=%+v, want code %s", execution.Failure, test.wantCode)
			}
		})
	}
}
