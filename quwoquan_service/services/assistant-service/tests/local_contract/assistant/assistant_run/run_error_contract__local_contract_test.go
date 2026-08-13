// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
// 错误契约语义双向锁：AssistantRun errors.yaml 声明的错误码由真实触发条件或对象级
// 依赖失败注入触发，并断言 canonical code 与恢复语义。
package assistant_run_test

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tooling"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	runports "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

type failingSkillPackageResolver struct{}

func (failingSkillPackageResolver) ResolveActiveSkillPackage(
	context.Context,
) (string, string, error) {
	return "", "", errors.New("skill package registry unreachable")
}

func (failingSkillPackageResolver) ContainsSkillInFrozenPackage(
	context.Context,
	string,
) (bool, error) {
	return false, nil
}

// journalCorruptRepository 注入聚合读取一致性失败：Load 冒出 ErrJournalCorrupt。
type journalCorruptRepository struct{ *memoryRunRepository }

func (journalCorruptRepository) Load(
	context.Context,
	string,
) (runruntime.Run, error) {
	return runruntime.Run{}, runruntime.ErrJournalCorrupt
}

// failingPreferenceSnapshots 让 Start 的偏好装配依赖冒出注入的 sentinel。
type failingPreferenceSnapshots struct{ err error }

func (reader failingPreferenceSnapshots) ResolveActiveSnapshots(
	context.Context,
	string,
	string,
) (
	[]preferencemodel.AssistantPreferenceSnapshot,
	[]preferencemodel.AssistantPreferenceSnapshot,
	error,
) {
	return nil, nil, reader.err
}

func assertRunAppError(t *testing.T, err error, code string, status int) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("error=%T %v, want *rterr.AppError", err, err)
	}
	if appErr.Code.String() != code || appErr.HTTPStatus != status {
		t.Fatalf(
			"error=%s/%d, want %s/%d",
			appErr.Code.String(),
			appErr.HTTPStatus,
			code,
			status,
		)
	}
}

func runErrorContractCommandService(
	repository runruntime.Repository,
	skillPackages runruntime.SkillPackageIdentityResolver,
	options ...runruntime.CommandServiceOption,
) *runruntime.CommandService {
	return runruntime.NewCommandService(
		repository,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		skillPackages,
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time { return time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC) },
		nil,
		options...,
	)
}

func runErrorContractStartInput(clientRequestID string) runapplication.StartInput {
	return runapplication.StartInput{
		ClientRequestID: clientRequestID,
		Intent: rundomain.Intent{
			Kind:   "answer",
			Answer: &rundomain.AnswerIntent{Text: "触发错误契约"},
		},
		TrustedPersonaID: "persona-run-error",
	}
}

func TestRunUseCasesEmitCanonicalErrorContract(t *testing.T) {
	t.Parallel()

	t.Run("failing package resolver is run_skill_package_unavailable", func(t *testing.T) {
		t.Parallel()
		useCases := runapplication.NewUseCases(runErrorContractCommandService(
			newMemoryRunRepository(),
			failingSkillPackageResolver{},
			runruntime.WithPolicyResolver(testPolicyResolver()),
		))
		_, err := useCases.Start(
			t.Context(),
			"user-run-error",
			"session-run-error",
			"trace-run-error",
			runErrorContractStartInput("run-package-unavailable"),
		)
		assertRunAppError(
			t, err, "ASSISTANT.SYSTEM.run_skill_package_unavailable", 503,
		)
	})

	t.Run("missing policy resolver is run_policy_unavailable", func(t *testing.T) {
		t.Parallel()
		useCases := runapplication.NewUseCases(runErrorContractCommandService(
			newMemoryRunRepository(),
			testSkillPackageIdentityResolver(),
		))
		_, err := useCases.Start(
			t.Context(),
			"user-run-error",
			"session-run-error",
			"trace-run-error",
			runErrorContractStartInput("run-policy-unavailable"),
		)
		assertRunAppError(t, err, "ASSISTANT.SYSTEM.run_policy_unavailable", 503)
	})

	t.Run("corrupt journal read is run_state_conflict", func(t *testing.T) {
		t.Parallel()
		useCases := runapplication.NewUseCases(runErrorContractCommandService(
			journalCorruptRepository{newMemoryRunRepository()},
			testSkillPackageIdentityResolver(),
			runruntime.WithPolicyResolver(testPolicyResolver()),
		))
		_, err := useCases.Get(t.Context(), "user-run-error", "run-any")
		assertRunAppError(t, err, "ASSISTANT.USER.run_state_conflict", 409)
	})

	t.Run("disabled skill sentinel maps to run_skill_disabled", func(t *testing.T) {
		t.Parallel()
		// 真实域触发：显式技能被账号设置关闭时，命令服务发射 ErrSkillDisabled。
		repository := newMemoryRunRepository()
		commands := runruntime.NewCommandService(
			repository,
			runruntime.SessionResolverFunc(func(
				context.Context,
				string,
				string,
			) (runruntime.SessionContinuity, error) {
				return runruntime.SessionContinuity{}, nil
			}),
			&rotatingSkillPackageResolver{
				packageID:     "assistant.session.skills",
				releaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			},
			runruntime.StartAccessPolicyFunc(func(
				context.Context,
				runruntime.StartAccessRequest,
			) error {
				return runruntime.ErrSkillDisabled
			}),
			func() time.Time { return time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC) },
			nil,
			runruntime.WithPolicyResolver(testPolicyResolver()),
		)
		_, err := commands.Start(t.Context(), runruntime.StartCommand{
			UserID:           "user-run-error",
			SessionID:        "session-run-error",
			ClientRequestID:  "run-skill-disabled-domain",
			InputText:        "用被关闭的技能执行",
			RequestedSkillID: "travel_companion",
		})
		if !errors.Is(err, runruntime.ErrSkillDisabled) {
			t.Fatalf("disabled skill sentinel = %v", err)
		}
		// 映射合同：同一 sentinel 从任何 Start 依赖冒出都必须发射 canonical code。
		useCases := runapplication.NewUseCases(
			runErrorContractCommandService(
				repository,
				testSkillPackageIdentityResolver(),
				runruntime.WithPolicyResolver(testPolicyResolver()),
			),
			runapplication.WithPreferenceSnapshots(failingPreferenceSnapshots{
				err: fmt.Errorf("%w: travel_companion", runruntime.ErrSkillDisabled),
			}),
		)
		_, err = useCases.Start(
			t.Context(),
			"user-run-error",
			"session-run-error",
			"trace-run-error",
			runErrorContractStartInput("run-skill-disabled-mapped"),
		)
		assertRunAppError(t, err, "ASSISTANT.USER.run_skill_disabled", 409)
	})

	t.Run("evidence reader outage is intersection_evidence_unavailable", func(t *testing.T) {
		t.Parallel()
		reader := &assistantRunIntersectionEvidenceGroundingRecordingIntersectionEvidenceReader{
			err: runapplication.ErrIntersectionEvidenceUnavailable,
		}
		input := runErrorContractStartInput("run-intersection-unavailable")
		input.TrustedPersonaID = "persona-owner"
		input.ContextSnapshot = map[string]any{
			"intersectionEvidenceRefs": []any{map[string]any{
				"intersectionId": "intersection-1",
				"evidenceId":     "snapshot-1",
				"sourceRef":      "same_school",
				"objectTypeRef":  "post",
				"objectId":       "post-1",
			}},
		}
		_, err := newIntersectionRunUseCases(reader).Start(
			t.Context(),
			"persona-owner",
			"session-run-error",
			"trace-run-error",
			input,
		)
		assertRunAppError(
			t, err, "ASSISTANT.MIDDLEWARE.intersection_evidence_unavailable", 503,
		)
	})
}

func TestGatheringBindingRejectionIsDelegatedApprovalInvalid(t *testing.T) {
	t.Parallel()
	_, err := tooling.MapGatheringCreateDraftProposal(
		tooling.GatheringExecutionContext{},
		tooling.GatheringToolDefinition{ToolName: "gathering.read_public"},
		tooling.GatheringCreateDraftProposalInput{},
		tooling.VerifiedGatheringHostAuthority{},
		tooling.GatheringApprovalIntentContext{},
		tooling.GatheringOptionalProviderState{},
		time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC),
	)
	if !errors.Is(err, tooling.ErrGatheringBindingInvalid) {
		t.Fatalf("binding rejection = %v, want ErrGatheringBindingInvalid", err)
	}
	if err.Error() != "ASSISTANT.USER.delegated_approval_invalid" {
		t.Fatalf(
			"sentinel must carry the canonical code, got %q",
			err.Error(),
		)
	}
}

func TestAgentLoopWithoutModelProviderEmitsModelProviderUnavailable(t *testing.T) {
	t.Parallel()
	_, failure, err := orchestration.NewAgentLoop(
		nil,
		orchestration.ReactRuntime{},
		func() time.Time { return time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC) },
	).RunTurn(t.Context(), assistantmodel.AssistantTurn{
		TurnID:          "turn-model-unavailable",
		SessionID:       "session-model-unavailable",
		ClientRequestID: "request-model-unavailable",
		Input:           assistantmodel.AssistantTurnInput{Text: "回答"},
	})
	if err != nil {
		t.Fatalf("run turn: %v", err)
	}
	if failure == nil ||
		failure.Code != "ASSISTANT.MIDDLEWARE.model_provider_unavailable" {
		t.Fatalf("failure=%+v", failure)
	}
}

func TestToolCoordinatorEmitsCanonicalProviderFailureCodes(t *testing.T) {
	t.Parallel()

	t.Run("uncategorized tool failure is tool_unavailable", func(t *testing.T) {
		t.Parallel()
		registry := toolpkg.NewRegistry()
		registry.Register(
			toolpkg.DefaultMetadata("custom_reader"),
			func(context.Context, toolpkg.Request) (toolpkg.Result, error) {
				return toolpkg.Result{}, errors.New("adapter crashed")
			},
		)
		execution, err := (orchestration.DefaultToolCoordinator{
			Registry: registry,
		}).Execute(t.Context(), orchestration.ToolRequest{
			Turn: assistantmodel.AssistantTurn{
				TurnID:          "turn-tool-unavailable",
				ClientRequestID: "request-tool-unavailable",
				Input:           assistantmodel.AssistantTurnInput{Text: "read"},
			},
			Skill:    orchestration.SkillSelection{SkillID: "knowledge_general"},
			ToolName: "custom_reader",
		})
		if err != nil {
			t.Fatalf("execute failing tool: %v", err)
		}
		if execution.Failure == nil ||
			execution.Failure.Code != "ASSISTANT.MIDDLEWARE.tool_unavailable" {
			t.Fatalf("failure=%+v", execution.Failure)
		}
	})

	t.Run("finance provider outage is finance_provider_unavailable", func(t *testing.T) {
		t.Parallel()
		registry := toolpkg.NewRegistry()
		registry.Register(
			toolpkg.FinanceQuoteMetadata(),
			func(context.Context, toolpkg.Request) (toolpkg.Result, error) {
				return toolpkg.Result{}, runports.ProviderFailure{
					Capability: "finance",
					Reason:     runports.ProviderFailureUnavailable,
				}
			},
		)
		execution, err := (orchestration.DefaultToolCoordinator{
			Registry: registry,
		}).Execute(t.Context(), orchestration.ToolRequest{
			Turn: assistantmodel.AssistantTurn{
				TurnID:          "turn-finance-unavailable",
				ClientRequestID: "request-finance-unavailable",
				Input:           assistantmodel.AssistantTurnInput{Text: "查询股价"},
			},
			Skill:    orchestration.SkillSelection{SkillID: "finance_insight"},
			ToolName: "finance_quote",
		})
		if err != nil {
			t.Fatalf("execute finance tool: %v", err)
		}
		if execution.Failure == nil ||
			execution.Failure.Code != "ASSISTANT.MIDDLEWARE.finance_provider_unavailable" {
			t.Fatalf("failure=%+v", execution.Failure)
		}
	})
}

func TestFrozenReasoningProfileDriftFailsRunWithCanonicalCode(t *testing.T) {
	repository := newMemoryRunRepository()
	queue := newMemoryWorkQueue()
	run, err := workerCommandService(repository).Start(
		context.Background(),
		runruntime.StartCommand{
			UserID:           "user-reasoning-drift",
			SessionID:        "session-reasoning-drift",
			ClientRequestID:  "request-reasoning-drift",
			InputText:        "核对推理档位",
			ReasoningProfile: generated.AssistantReasoningProfileBalanced,
		},
	)
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	repository.mu.Lock()
	drifted := repository.runs[run.RunID]
	drifted.ReasoningPolicy.Profile = generated.AssistantReasoningProfileFast
	repository.runs[run.RunID] = drifted
	repository.mu.Unlock()
	queue.enqueue(run.RunID)
	worker := runruntime.NewDurableWorker(
		repository,
		queue,
		&successfulRunExecutor{},
		"worker-reasoning-drift",
	)
	if _, err := worker.ProcessNext(context.Background()); err != nil {
		t.Fatalf("process drifted run: %v", err)
	}
	stored, err := repository.Load(context.Background(), run.RunID)
	if err != nil {
		t.Fatalf("load failed run: %v", err)
	}
	if stored.State != generated.AssistantRunStateFailed ||
		stored.TerminalSnapshot == nil ||
		stored.TerminalSnapshot.Failure == nil ||
		stored.TerminalSnapshot.Failure.Code !=
			"ASSISTANT.SYSTEM.run_reasoning_profile_unavailable" {
		t.Fatalf(
			"state=%s snapshot=%+v",
			stored.State,
			stored.TerminalSnapshot,
		)
	}
}
