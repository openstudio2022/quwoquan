package application

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

type StartInput struct {
	ClientRequestID     string                `json:"clientRequestId"`
	Intent              StartIntent           `json:"intent"`
	ContextSnapshot     map[string]any        `json:"contextSnapshot"`
	ReasoningProfile    string                `json:"reasoningProfile"`
	DefinitionOfDone    DefinitionOfDoneInput `json:"definitionOfDone"`
	SurfaceCapabilities map[string]any        `json:"surfaceCapabilities"`
}

type StartIntent struct {
	Kind               string                    `json:"kind"`
	Answer             *AnswerIntent             `json:"answer"`
	Search             *SearchIntent             `json:"search"`
	CreationAssistance *CreationAssistanceIntent `json:"creationAssistance"`
}

type AnswerIntent struct {
	Text string `json:"text"`
}

type SearchIntent struct {
	Query string `json:"query"`
}

type CreationAssistanceIntent struct {
	DraftTitle   string `json:"draftTitle"`
	DraftSummary string `json:"draftSummary"`
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
	preferenceSnapshots sessionports.PreferenceSnapshotReader
}

func NewUseCases(
	runs *runruntime.CommandService,
	preferenceSnapshots ...sessionports.PreferenceSnapshotReader,
) *UseCases {
	if runs == nil {
		panic("assistant run command service is required")
	}
	useCases := &UseCases{runs: runs}
	if len(preferenceSnapshots) > 0 {
		useCases.preferenceSnapshots = preferenceSnapshots[0]
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
	text, err := input.Intent.primaryText()
	if err != nil {
		return runruntime.Run{}, err
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
	run, err := s.runs.Start(ctx, runruntime.StartCommand{
		UserID:                  userID,
		SessionID:               sessionID,
		ClientRequestID:         input.ClientRequestID,
		TraceID:                 traceID,
		IntentKind:              strings.TrimSpace(input.Intent.Kind),
		InputText:               text,
		ContextSnapshot:         input.ContextSnapshot,
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

func (intent StartIntent) primaryText() (string, error) {
	switch strings.TrimSpace(intent.Kind) {
	case "answer":
		if intent.Answer == nil ||
			intent.Search != nil ||
			intent.CreationAssistance != nil ||
			strings.TrimSpace(intent.Answer.Text) == "" {
			return "", invalidArgument("invalid answer intent")
		}
		return strings.TrimSpace(intent.Answer.Text), nil
	case "search":
		if intent.Search == nil ||
			intent.Answer != nil ||
			intent.CreationAssistance != nil ||
			strings.TrimSpace(intent.Search.Query) == "" {
			return "", invalidArgument("invalid search intent")
		}
		return strings.TrimSpace(intent.Search.Query), nil
	case "creation_assistance":
		if intent.CreationAssistance == nil ||
			intent.Answer != nil ||
			intent.Search != nil {
			return "", invalidArgument("invalid creation assistance intent")
		}
		text := strings.TrimSpace(
			intent.CreationAssistance.DraftTitle + "\n" +
				intent.CreationAssistance.DraftSummary,
		)
		if text == "" {
			return "", invalidArgument("empty creation assistance intent")
		}
		return text, nil
	default:
		return "", invalidArgument("unknown assistant run intent")
	}
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
