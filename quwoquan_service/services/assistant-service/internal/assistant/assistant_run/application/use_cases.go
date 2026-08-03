package application

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
)

type StartInput struct {
	ClientRequestID     string                `json:"clientRequestId"`
	Intent              rundomain.Intent      `json:"intent"`
	ContextSnapshot     map[string]any        `json:"contextSnapshot"`
	ReasoningProfile    string                `json:"reasoningProfile"`
	DefinitionOfDone    DefinitionOfDoneInput `json:"definitionOfDone"`
	SurfaceCapabilities map[string]any        `json:"surfaceCapabilities"`
	// TrustedPersonaID is injected from the verified transport principal after
	// JSON decoding. It is never accepted as a public command field.
	TrustedPersonaID      string                    `json:"-"`
	TrustedRequestContext runruntime.RequestContext `json:"-"`
}

type DefinitionOfDoneInput struct {
	Outcome                  string   `json:"outcome"`
	Constraints              []string `json:"constraints"`
	VerificationRequirements []string `json:"verificationRequirements"`
}

type ContinueToolUseInput struct {
	Decision          string                             `json:"decision"`
	ContinuationToken string                             `json:"continuationToken"`
	ExecutionReceipt  *DeviceActionExecutionReceiptInput `json:"executionReceipt"`
}

type DeviceActionExecutionReceiptInput struct {
	ActionKind     string    `json:"actionKind"`
	IdempotencyKey string    `json:"idempotencyKey"`
	Outcome        string    `json:"outcome"`
	ExecutedAt     time.Time `json:"executedAt"`
	DeviceObjectID string    `json:"deviceObjectId"`
	FailureCode    string    `json:"failureCode"`
}

type PauseInput struct {
	Reason string `json:"reason"`
}

type SteerInput struct {
	Instruction string `json:"instruction"`
}

type UseCases struct {
	runs                *runruntime.CommandService
	preferenceSnapshots PreferenceSnapshotReader
	contextResolver     *ContextResolver
}

type PreferenceSnapshotReader interface {
	ResolveActiveSnapshots(
		context.Context,
		string,
		string,
	) ([]preferencemodel.Snapshot, []preferencemodel.Snapshot, error)
}

type UseCaseOption func(*UseCases)

func WithPreferenceSnapshots(reader PreferenceSnapshotReader) UseCaseOption {
	return func(useCases *UseCases) { useCases.preferenceSnapshots = reader }
}

func WithContextResolver(resolver *ContextResolver) UseCaseOption {
	return func(useCases *UseCases) { useCases.contextResolver = resolver }
}

func NewUseCases(runs *runruntime.CommandService, options ...UseCaseOption) *UseCases {
	if runs == nil {
		panic("assistant run command service is required")
	}
	useCases := &UseCases{runs: runs}
	for _, option := range options {
		option(useCases)
	}
	return useCases
}

func (s *UseCases) Start(
	ctx context.Context,
	userID string,
	sessionID string,
	traceID string,
	input StartInput,
) (runruntime.Run, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(sessionID) == "" {
		return runruntime.Run{}, invalidArgument("missing run owner or session")
	}
	if strings.TrimSpace(input.TrustedPersonaID) == "" {
		return runruntime.Run{}, invalidArgument("missing trusted run persona")
	}
	text, err := input.Intent.PrimaryText()
	if err != nil {
		return runruntime.Run{}, invalidArgument(err.Error())
	}
	profile := generated.AssistantReasoningProfileBalanced
	if raw := strings.TrimSpace(input.ReasoningProfile); raw != "" {
		profile, err = generated.ParseAssistantReasoningProfile(raw)
		if err != nil {
			return runruntime.Run{}, invalidArgument(err.Error())
		}
	}
	var sessionPreferences, longTermPreferences = []preferencemodel.Snapshot(nil), []preferencemodel.Snapshot(nil)
	if s.preferenceSnapshots != nil {
		sessionPreferences, longTermPreferences, err =
			s.preferenceSnapshots.ResolveActiveSnapshots(
				ctx,
				userID,
				sessionID,
			)
		if err != nil {
			return runruntime.Run{}, mapRunError(err)
		}
	}
	contextSnapshot := input.ContextSnapshot
	if s.contextResolver != nil {
		contextSnapshot, err = s.contextResolver.Resolve(
			ctx,
			userID,
			input.TrustedPersonaID,
			input.ContextSnapshot,
		)
		if err != nil {
			return runruntime.Run{}, mapRunError(err)
		}
	}
	run, err := s.runs.Start(ctx, runruntime.StartCommand{
		UserID:                  userID,
		PersonaID:               input.TrustedPersonaID,
		SessionID:               sessionID,
		ClientRequestID:         input.ClientRequestID,
		TraceID:                 traceID,
		RequestContext:          input.TrustedRequestContext,
		IntentKind:              strings.TrimSpace(input.Intent.Kind),
		InputText:               text,
		ContextSnapshot:         contextSnapshot,
		SurfaceCapabilities:     input.SurfaceCapabilities,
		SessionPreferenceFacts:  sessionPreferences,
		LongTermPreferenceFacts: longTermPreferences,
		ReasoningProfile:        profile,
		DefinitionOfDone: runruntime.DefinitionOfDone{
			Outcome:                  input.DefinitionOfDone.Outcome,
			Constraints:              input.DefinitionOfDone.Constraints,
			VerificationRequirements: input.DefinitionOfDone.VerificationRequirements,
		},
	})
	return run, mapRunError(err)
}

func (s *UseCases) Get(
	ctx context.Context,
	userID string,
	runID string,
) (runruntime.Run, error) {
	run, err := s.runs.Get(ctx, userID, strings.TrimSpace(runID))
	return run, mapRunError(err)
}

func (s *UseCases) Pause(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
	input PauseInput,
) (runruntime.Run, error) {
	run, err := s.runs.Pause(ctx, userID, runID, commandID, input.Reason)
	return run, mapRunError(err)
}

func (s *UseCases) Resume(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
) (runruntime.Run, error) {
	run, err := s.runs.Resume(ctx, userID, runID, commandID)
	return run, mapRunError(err)
}

func (s *UseCases) Steer(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
	input SteerInput,
) (runruntime.Run, error) {
	run, err := s.runs.Steer(
		ctx,
		userID,
		runID,
		commandID,
		input.Instruction,
	)
	return run, mapRunError(err)
}

func (s *UseCases) ContinueToolUse(
	ctx context.Context,
	userID string,
	runID string,
	toolUseID string,
	commandID string,
	input ContinueToolUseInput,
) (runruntime.Run, error) {
	var receipt *runruntime.DeviceActionExecutionReceipt
	if input.ExecutionReceipt != nil {
		receipt = &runruntime.DeviceActionExecutionReceipt{
			ActionKind:     input.ExecutionReceipt.ActionKind,
			IdempotencyKey: input.ExecutionReceipt.IdempotencyKey,
			Outcome:        input.ExecutionReceipt.Outcome,
			ExecutedAt:     input.ExecutionReceipt.ExecutedAt,
			DeviceObjectID: input.ExecutionReceipt.DeviceObjectID,
			FailureCode:    input.ExecutionReceipt.FailureCode,
		}
	}
	run, err := s.runs.ContinueToolUse(ctx, runruntime.ContinueToolUseCommand{
		UserID:            userID,
		RunID:             runID,
		ToolUseID:         toolUseID,
		CommandID:         commandID,
		Decision:          input.Decision,
		ContinuationToken: input.ContinuationToken,
		ExecutionReceipt:  receipt,
	})
	return run, mapRunError(err)
}

func (s *UseCases) Cancel(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
) (runruntime.Run, error) {
	run, err := s.runs.Cancel(
		ctx,
		userID,
		strings.TrimSpace(runID),
		commandID,
	)
	return run, mapRunError(err)
}

func (s *UseCases) EventsAfter(
	ctx context.Context,
	userID string,
	runID string,
	afterSequence int64,
	limit int,
) ([]runruntime.JournalEvent, error) {
	events, err := s.runs.EventsAfter(
		ctx,
		userID,
		runID,
		afterSequence,
		limit,
	)
	return events, mapRunError(err)
}

func mapRunError(err error) error {
	if err == nil {
		return nil
	}
	var appErr *rterr.AppError
	if errors.As(err, &appErr) {
		return appErr
	}
	switch {
	case errors.Is(err, runruntime.ErrInvalidRun),
		errors.Is(err, runruntime.ErrInvalidTransition),
		errors.Is(err, runruntime.ErrInvalidTaskGraph):
		return invalidArgument(err.Error())
	case errors.Is(err, runruntime.ErrRunNotFound):
		appErr := rterr.NewAppError(
			rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "run_not_found"),
			"本次执行不存在或已失效",
			err.Error(),
		)
		appErr.HTTPStatus = http.StatusNotFound
		return appErr
	case errors.Is(err, runruntime.ErrSkillPackageUnavailable):
		appErr := rterr.NewAppError(
			rterr.NewCode(rterr.ModuleAssistant, rterr.KindSystem, "run_skill_package_unavailable"),
			"助手技能包暂不可用，请稍后重试",
			err.Error(),
		)
		appErr.HTTPStatus = http.StatusServiceUnavailable
		return appErr
	case errors.Is(err, runruntime.ErrSkillDisabled):
		appErr := rterr.NewAppError(
			rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "run_skill_disabled"),
			"该技能在当前场景未启用，请检查个人或群聊技能设置",
			err.Error(),
		)
		appErr.HTTPStatus = http.StatusConflict
		return appErr
	case errors.Is(err, runruntime.ErrSkillSettingUnavailable):
		appErr := rterr.NewAppError(
			rterr.NewCode(rterr.ModuleAssistant, rterr.KindSystem, "skill_setting_storage_unavailable"),
			"技能设置服务暂不可用，个人技能按失败关闭处理",
			err.Error(),
		)
		appErr.HTTPStatus = http.StatusServiceUnavailable
		return appErr
	case errors.Is(err, runruntime.ErrPolicyUnavailable):
		return runerrors.AppErrorFromRunPolicyUnavailable(err.Error())
	case errors.Is(err, ErrIntersectionEvidenceNotFound):
		return runerrors.AppErrorFromIntersectionEvidenceNotFound(err.Error())
	case errors.Is(err, ErrIntersectionEvidenceUnavailable):
		return runerrors.AppErrorFromIntersectionEvidenceUnavailable(err.Error())
	case errors.Is(err, runruntime.ErrRevisionConflict),
		errors.Is(err, runruntime.ErrLeaseConflict),
		errors.Is(err, runruntime.ErrJournalGap),
		errors.Is(err, runruntime.ErrJournalCorrupt):
		appErr := rterr.NewAppError(
			rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "run_revision_conflict"),
			"执行状态已更新，请刷新后重试",
			err.Error(),
		)
		appErr.HTTPStatus = http.StatusConflict
		return appErr
	default:
		appErr := rterr.NewAppError(
			rterr.NewCode(rterr.ModuleAssistant, rterr.KindSystem, "run_storage_unavailable"),
			"助手执行服务暂不可用，请稍后重试",
			err.Error(),
		)
		appErr.HTTPStatus = http.StatusServiceUnavailable
		return appErr
	}
}

func invalidArgument(debug string) *rterr.AppError {
	appErr := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "run_invalid_argument"),
		"执行请求参数有误",
		debug,
	)
	appErr.HTTPStatus = http.StatusBadRequest
	return appErr
}
