package runruntime

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

type StartCommand struct {
	UserID              string
	PersonaID           string
	SessionID           string
	ClientRequestID     string
	TraceID             string
	RequestContext      RequestContext
	IntentKind          string
	InputText           string
	RequestedSkillID    string
	RequestedDomainID   string
	Trigger             map[string]any
	ContextSnapshot     map[string]any
	SurfaceCapabilities map[string]any
	SessionPreferences  []preferencemodel.AssistantPreferenceSnapshot
	LongTermPreferences []preferencemodel.AssistantPreferenceSnapshot
	ReasoningProfile    generated.AssistantReasoningProfile
	DefinitionOfDone    DefinitionOfDone
}

type ApproveToolUseCommand struct {
	UserID           string
	RunID            string
	ToolInvocationID string
	CommandID        string
	Decision         string
	ApprovalPermit   string
	InstallationID   string
	DeviceID         string
}

type SubmitDeviceActionReceiptCommand struct {
	UserID           string
	RunID            string
	ToolInvocationID string
	CommandID        string
	Receipt          DeviceActionExecutionReceipt
}

type SessionResolver interface {
	ResolveAuthorizedSession(
		context.Context,
		string,
		string,
	) (SessionContinuity, error)
}

type SessionResolverFunc func(
	context.Context,
	string,
	string,
) (SessionContinuity, error)

func (f SessionResolverFunc) ResolveAuthorizedSession(
	ctx context.Context,
	userID string,
	sessionID string,
) (SessionContinuity, error) {
	return f(ctx, userID, sessionID)
}

type SkillPackageIdentity struct {
	PackageID     string
	ReleaseDigest string
}

type SkillPackageIdentityResolver interface {
	ResolveActiveSkillPackage(context.Context) (string, string, error)
}

type StartAccessPolicy interface {
	AuthorizeStart(context.Context, StartAccessRequest) error
}

type StartAccessRequest struct {
	AccountID   string
	PersonaID   string
	SkillID     string
	SurfaceKind string
	SurfaceID   string
}

type PolicyResolver interface {
	ResolveFrozenPolicy(
		context.Context,
		string,
		string,
		string,
		string,
	) (FrozenPolicySelection, error)
}

type PolicyResolverFunc func(
	context.Context,
	string,
	string,
	string,
	string,
) (FrozenPolicySelection, error)

func (resolve PolicyResolverFunc) ResolveFrozenPolicy(
	ctx context.Context,
	policyID string,
	personaID string,
	skillID string,
	domainID string,
) (FrozenPolicySelection, error) {
	return resolve(ctx, policyID, personaID, skillID, domainID)
}

type FeedbackContextResolver interface {
	ResolveFeedbackContext(
		context.Context,
		string,
		string,
		string,
		string,
		string,
		string,
		assistantmodel.AssistantFrozenLearningContextPolicy,
		time.Time,
	) assistantmodel.AssistantFeedbackContextSnapshot
}

type CommandServiceOption func(*CommandService)

func WithPolicyResolver(resolver PolicyResolver) CommandServiceOption {
	return func(service *CommandService) { service.policies = resolver }
}

func WithFeedbackContextResolver(resolver FeedbackContextResolver) CommandServiceOption {
	return func(service *CommandService) { service.feedbackContext = resolver }
}

type StartAccessPolicyFunc func(context.Context, StartAccessRequest) error

func (policy StartAccessPolicyFunc) AuthorizeStart(
	ctx context.Context,
	request StartAccessRequest,
) error {
	return policy(ctx, request)
}

type AllowAllStartAccessPolicy struct{}

func (AllowAllStartAccessPolicy) AuthorizeStart(
	context.Context,
	StartAccessRequest,
) error {
	return nil
}

type StaticSkillPackageIdentityResolver struct {
	PackageID     string
	ReleaseDigest string
}

func (resolver StaticSkillPackageIdentityResolver) ResolveActiveSkillPackage(
	ctx context.Context,
) (string, string, error) {
	if err := ctx.Err(); err != nil {
		return "", "", err
	}
	packageID := strings.TrimSpace(resolver.PackageID)
	digest := strings.TrimSpace(resolver.ReleaseDigest)
	if packageID == "" || !validSkillPackageDigest(digest) {
		return "", "", ErrSkillPackageUnavailable
	}
	return packageID, digest, nil
}

func validSkillPackageDigest(value string) bool {
	if len(value) != len("sha256:")+sha256.Size*2 ||
		!strings.HasPrefix(value, "sha256:") {
		return false
	}
	raw := strings.TrimPrefix(value, "sha256:")
	if raw != strings.ToLower(raw) {
		return false
	}
	_, err := hex.DecodeString(raw)
	return err == nil
}

// CommandService is the only writable AssistantRun command surface. Every
// mutation loads one aggregate revision and commits its journal event with CAS.
type CommandService struct {
	repository      Repository
	sessions        SessionResolver
	skillPackages   SkillPackageIdentityResolver
	startAccess     StartAccessPolicy
	policies        PolicyResolver
	feedbackContext FeedbackContextResolver
	now             func() time.Time
	newRunID        func() (string, error)
	cancel          *CancellationCoordinator
}

func NewCommandService(
	repository Repository,
	sessions SessionResolver,
	skillPackages SkillPackageIdentityResolver,
	startAccess StartAccessPolicy,
	now func() time.Time,
	cancel *CancellationCoordinator,
	options ...CommandServiceOption,
) *CommandService {
	if repository == nil || sessions == nil || skillPackages == nil || startAccess == nil {
		panic("assistant run command dependencies are required")
	}
	if now == nil {
		now = time.Now
	}
	service := &CommandService{
		repository:    repository,
		sessions:      sessions,
		skillPackages: skillPackages,
		startAccess:   startAccess,
		now:           now,
		newRunID:      newRunID,
		cancel:        cancel,
	}
	for _, option := range options {
		if option != nil {
			option(service)
		}
	}
	return service
}

func (s *CommandService) Start(
	ctx context.Context,
	command StartCommand,
) (Run, error) {
	command = normalizeStartCommand(command, s.now())
	if command.UserID == "" ||
		command.SessionID == "" ||
		command.ClientRequestID == "" ||
		command.InputText == "" {
		return Run{}, ErrInvalidRun
	}
	inputDigest, err := commandDigest("run_start", struct {
		PersonaID           string         `json:"personaId"`
		RequestContext      RequestContext `json:"requestContext"`
		IntentKind          string         `json:"intentKind"`
		InputText           string         `json:"inputText"`
		RequestedSkillID    string         `json:"requestedSkillId,omitempty"`
		RequestedDomainID   string         `json:"requestedDomainId,omitempty"`
		Trigger             map[string]any `json:"trigger,omitempty"`
		ContextSnapshot     map[string]any `json:"contextSnapshot,omitempty"`
		SurfaceCapabilities map[string]any `json:"surfaceCapabilities,omitempty"`
	}{
		PersonaID:           command.PersonaID,
		RequestContext:      command.RequestContext,
		IntentKind:          command.IntentKind,
		InputText:           command.InputText,
		RequestedSkillID:    command.RequestedSkillID,
		RequestedDomainID:   command.RequestedDomainID,
		Trigger:             command.Trigger,
		ContextSnapshot:     command.ContextSnapshot,
		SurfaceCapabilities: command.SurfaceCapabilities,
	})
	if err != nil {
		return Run{}, err
	}
	existing, err := s.repository.LoadByRequest(
		ctx,
		command.UserID,
		command.SessionID,
		command.ClientRequestID,
	)
	if err == nil {
		if existing.ExecutionInputDigest != inputDigest {
			return Run{}, ErrRevisionConflict
		}
		return existing, nil
	}
	if !errors.Is(err, ErrRunNotFound) {
		return Run{}, err
	}
	continuity, err := s.sessions.ResolveAuthorizedSession(
		ctx,
		command.UserID,
		command.SessionID,
	)
	if err != nil {
		return Run{}, err
	}
	if !personalSessionContinuityAllowed(command.RequestContext.SurfaceKind) {
		continuity = SessionContinuity{}
	}
	if command.RequestedSkillID != "" {
		if err := s.startAccess.AuthorizeStart(
			ctx,
			StartAccessRequest{
				AccountID:   command.UserID,
				PersonaID:   command.PersonaID,
				SkillID:     command.RequestedSkillID,
				SurfaceKind: command.RequestContext.SurfaceKind,
				SurfaceID:   command.RequestContext.SurfaceID,
			},
		); err != nil {
			return Run{}, err
		}
	}
	skillPackageID, skillPackageReleaseDigest, err :=
		s.skillPackages.ResolveActiveSkillPackage(ctx)
	if err != nil || strings.TrimSpace(skillPackageID) == "" ||
		!validSkillPackageDigest(strings.TrimSpace(skillPackageReleaseDigest)) {
		return Run{}, ErrSkillPackageUnavailable
	}
	if s.policies == nil {
		return Run{}, ErrPolicyUnavailable
	}
	policySelection, err := s.policies.ResolveFrozenPolicy(
		ctx,
		"assistant-default",
		command.PersonaID,
		command.RequestedSkillID,
		command.RequestedDomainID,
	)
	if err != nil || !validPolicySelection(policySelection) {
		return Run{}, ErrPolicyUnavailable
	}
	feedbackSkillID := strings.TrimSpace(command.RequestedSkillID)
	if feedbackSkillID == "" {
		feedbackSkillID = strings.TrimSpace(policySelection.Template.SkillID)
	}
	runID, err := s.newRunID()
	if err != nil {
		return Run{}, err
	}
	graph, err := NewTaskGraph([]TaskNode{{
		TaskID: "task_root",
		Goal:   command.DefinitionOfDone.Outcome,
	}})
	if err != nil {
		return Run{}, err
	}
	now := s.now().UTC().Truncate(time.Millisecond)
	feedbackPolicy := projectFeedbackContextPolicy(
		policySelection.LearningContextPolicy,
	)
	feedbackContext := assistantmodel.AssistantFeedbackContextSnapshot{
		Decision:                 "resolver_unavailable",
		WindowDays:               feedbackPolicy.WindowDays,
		SnapshotTrainingEligible: false,
	}
	if !feedbackPolicy.Enabled {
		feedbackContext.Decision = "policy_disabled"
	} else if !personalSessionContinuityAllowed(command.RequestContext.SurfaceKind) {
		feedbackContext.Decision = "shared_surface_excluded"
	} else if s.feedbackContext != nil {
		feedbackContext = s.feedbackContext.ResolveFeedbackContext(
			ctx,
			command.UserID,
			command.PersonaID,
			feedbackSkillID,
			command.RequestContext.SurfaceKind,
			skillPackageID,
			skillPackageReleaseDigest,
			feedbackPolicy,
			now,
		)
	}
	if feedbackContext.Decision == "injected" && feedbackContext.ConsentGrantedAt.After(now) {
		return Run{}, ErrInvalidRun
	}
	run, err := NewRun(
		runID,
		command.ReasoningProfile,
		command.DefinitionOfDone,
		graph,
		now,
	)
	if err != nil {
		return Run{}, err
	}
	if err := run.BindIdentity(
		command.UserID,
		command.PersonaID,
		command.SessionID,
		command.ClientRequestID,
		command.TraceID,
		command.InputText,
	); err != nil {
		return Run{}, err
	}
	run.RequestContext = normalizeRequestContext(command.RequestContext)
	if err := run.BindExecutionInput(
		command.IntentKind,
		inputDigest,
		command.RequestedSkillID,
		command.RequestedDomainID,
		command.Trigger,
		command.ContextSnapshot,
		command.SurfaceCapabilities,
	); err != nil {
		return Run{}, err
	}
	if err := run.BindSessionContinuity(continuity); err != nil {
		return Run{}, err
	}
	if err := run.BindSkillPackage(
		skillPackageID,
		skillPackageReleaseDigest,
	); err != nil {
		return Run{}, err
	}
	run.FrozenPolicySelection = clonePolicySelection(policySelection)
	if err := run.BindFeedbackContext(feedbackContext); err != nil {
		return Run{}, err
	}
	run.SessionPreferences = append(
		[]preferencemodel.AssistantPreferenceSnapshot(nil),
		command.SessionPreferences...,
	)
	run.LongTermPreferences = append(
		[]preferencemodel.AssistantPreferenceSnapshot(nil),
		command.LongTermPreferences...,
	)
	event := JournalEvent{
		EventID:   run.RunID + ":1",
		RunID:     run.RunID,
		Sequence:  1,
		Revision:  run.Revision,
		Kind:      "run_accepted",
		Payload:   map[string]any{"status": run.State.WireName()},
		CreatedAt: now,
	}
	run.JournalSequence = event.Sequence
	if err := s.repository.Commit(
		ctx,
		0,
		run,
		[]JournalEvent{event},
		nil,
	); err != nil {
		if errors.Is(err, ErrRevisionConflict) {
			replayed, replayErr := s.repository.LoadByRequest(
				ctx,
				command.UserID,
				command.SessionID,
				command.ClientRequestID,
			)
			if replayErr == nil && replayed.ExecutionInputDigest == inputDigest {
				return replayed, nil
			}
		}
		return Run{}, err
	}
	return run, nil
}

func projectFeedbackContextPolicy(
	policy FrozenLearningContextPolicy,
) assistantmodel.AssistantFrozenLearningContextPolicy {
	return assistantmodel.AssistantFrozenLearningContextPolicy{
		Enabled:                  policy.Enabled,
		AllowedSignals:           append([]string(nil), policy.AllowedSignals...),
		AllowedMetricIDs:         append([]string(nil), policy.AllowedMetricIDs...),
		AllowedReasonCodes:       append([]string(nil), policy.AllowedReasonCodes...),
		MinimumFeedbackSamples:   policy.MinimumFeedbackSamples,
		WindowDays:               policy.WindowDays,
		SnapshotTrainingEligible: policy.SnapshotTrainingEligible,
	}
}

func validPolicySelection(selection FrozenPolicySelection) bool {
	digest := strings.TrimPrefix(strings.TrimSpace(selection.ReleaseDigest), "sha256:")
	if strings.TrimSpace(selection.PolicyID) == "" || len(digest) != sha256.Size*2 ||
		digest != strings.ToLower(digest) {
		return false
	}
	if _, err := hex.DecodeString(digest); err != nil {
		return false
	}
	return strings.TrimSpace(selection.Template.TemplateID) != "" &&
		selection.RolloutRevision > 0
}

func clonePolicySelection(selection FrozenPolicySelection) FrozenPolicySelection {
	selection.Template.AllowedTools = append(
		[]string(nil),
		selection.Template.AllowedTools...,
	)
	selection.LearningContextPolicy.AllowedSignals = append(
		[]string(nil),
		selection.LearningContextPolicy.AllowedSignals...,
	)
	selection.LearningContextPolicy.AllowedMetricIDs = append(
		[]string(nil),
		selection.LearningContextPolicy.AllowedMetricIDs...,
	)
	selection.LearningContextPolicy.AllowedReasonCodes = append(
		[]string(nil),
		selection.LearningContextPolicy.AllowedReasonCodes...,
	)
	return selection
}

func normalizeRequestContext(value RequestContext) RequestContext {
	return RequestContext{
		ClientSessionID: strings.TrimSpace(value.ClientSessionID),
		PageID:          strings.TrimSpace(value.PageID),
		SurfaceKind:     strings.TrimSpace(value.SurfaceKind),
		SurfaceID:       strings.TrimSpace(value.SurfaceID),
		RouteID:         strings.TrimSpace(value.RouteID),
		OperationID:     strings.TrimSpace(value.OperationID),
		TraceID:         strings.TrimSpace(value.TraceID),
		PersonaID:       strings.TrimSpace(value.PersonaID),
	}
}

func (s *CommandService) Get(
	ctx context.Context,
	userID string,
	runID string,
) (Run, error) {
	run, err := s.repository.Load(ctx, strings.TrimSpace(runID))
	if err != nil {
		return Run{}, err
	}
	if run.UserID != strings.TrimSpace(userID) {
		return Run{}, ErrRunNotFound
	}
	return run, nil
}

func (s *CommandService) Pause(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
	reason string,
) (Run, error) {
	return s.mutate(ctx, userID, runID, commandID, "run_pause_requested", reason, func(run *Run, now time.Time) error {
		if run.State == generated.AssistantRunStatePaused {
			return nil
		}
		return run.RequestPause(reason, now)
	})
}

func (s *CommandService) Resume(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
) (Run, error) {
	return s.mutate(ctx, userID, runID, commandID, "run_resumed", nil, func(run *Run, now time.Time) error {
		return run.Resume(now)
	})
}

func (s *CommandService) Steer(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
	instruction string,
) (Run, error) {
	return s.mutate(ctx, userID, runID, commandID, "run_steer_requested", instruction, func(run *Run, now time.Time) error {
		return run.RequestSteer(instruction, now)
	})
}

func (s *CommandService) Cancel(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
) (Run, error) {
	startedAt := s.now()
	run, err := s.mutate(ctx, userID, runID, commandID, "run_cancelled", nil, func(run *Run, now time.Time) error {
		if run.State == generated.AssistantRunStateCancelled {
			return nil
		}
		if s.cancel != nil {
			if err := s.cancel.Cancel(ctx, run, "user_cancelled", now); err != nil {
				return err
			}
		} else if err := run.Transition(
			generated.AssistantRunStateCancelled,
			"user_cancelled",
			now,
		); err != nil {
			return err
		}
		snapshot := assistantmodel.AssistantRunTerminalSnapshot{
			AnswerText:        "",
			Processes:         []assistantmodel.AssistantRunVisibleProcess{},
			SelectedPolicyRef: terminalSelectedPolicyRef(run.FrozenPolicySelection),
		}
		return run.SetTerminalSnapshot(snapshot, now)
	})
	observeCancelDuration(startedAt, err)
	return run, err
}

func (s *CommandService) ApproveToolUse(
	ctx context.Context,
	command ApproveToolUseCommand,
) (Run, *DeviceActionPermit, error) {
	decision := strings.TrimSpace(command.Decision)
	if decision != "approved" && decision != "rejected" {
		return Run{}, nil, ErrInvalidRun
	}
	if decision == "approved" &&
		(strings.TrimSpace(command.InstallationID) == "" ||
			strings.TrimSpace(command.DeviceID) == "") {
		return Run{}, nil, ErrInvalidRun
	}
	permitValue, jti, err := newDeviceActionPermitIdentity()
	if err != nil {
		return Run{}, nil, err
	}
	run, err := s.mutate(
		ctx,
		command.UserID,
		command.RunID,
		command.CommandID,
		"tool_use_approved",
		map[string]string{
			"toolInvocationId": command.ToolInvocationID,
			"decision":         decision,
		},
		func(run *Run, now time.Time) error {
			if run.State != generated.AssistantRunStateWaitingApproval ||
				run.Checkpoint == nil ||
				run.Checkpoint.PendingApprovalRef !=
					strings.TrimSpace(command.ToolInvocationID) ||
				strings.TrimSpace(command.ApprovalPermit) !=
					assistantRunContinuationToken(
						run.RunID,
						command.ToolInvocationID,
					) {
				return ErrInvalidTransition
			}
			binding, valid := pendingDeviceActionBinding(
				run.PresentationDocument,
				run.RunID,
				strings.TrimSpace(command.ToolInvocationID),
				strings.TrimSpace(command.ApprovalPermit),
				decision,
				now,
			)
			if !valid {
				return ErrInvalidRun
			}
			if decision == "approved" {
				permit := DeviceActionPermit{
					RunID:            run.RunID,
					ToolInvocationID: strings.TrimSpace(command.ToolInvocationID),
					InstallationID:   strings.TrimSpace(command.InstallationID),
					DeviceID:         strings.TrimSpace(command.DeviceID),
					Capability:       binding.Capability,
					InputDigest:      binding.InputDigest,
					IdempotencyKey:   strings.TrimSpace(command.ToolInvocationID),
					ApprovalRef:      strings.TrimSpace(command.ApprovalPermit),
					JTI:              jti,
					ExpiresAt:        now.UTC().Add(time.Minute),
					Permit:           permitValue,
				}
				run.Checkpoint.PendingApprovalRef = ""
				run.Checkpoint.PendingDeviceAction = &permit
				run.Checkpoint.DecisionSummary = append(
					run.Checkpoint.DecisionSummary,
					"device_action_approved:"+
						strings.TrimSpace(command.ToolInvocationID),
				)
				return run.Transition(
					generated.AssistantRunStateWaitingExternal,
					"device_action_receipt_pending",
					now,
				)
			}
			run.Checkpoint.PendingApprovalRef = ""
			run.Checkpoint.PendingDeviceAction = nil
			for index := range run.Items {
				if run.Items[index].ItemID ==
					strings.TrimSpace(command.ToolInvocationID) &&
					run.Items[index].Status == generated.AssistantRunItemStatusStarted {
					if err := run.CompleteItem(
						run.Items[index].ItemID,
						generated.AssistantRunItemStatusCancelled,
						nil,
						"user_rejected",
						now,
					); err != nil {
						return err
					}
					break
				}
			}
			run.CancelActiveWork("user_rejected", now)
			return run.Transition(generated.AssistantRunStateCancelled, "user_rejected", now)
		},
	)
	if err != nil {
		return Run{}, nil, err
	}
	if run.Checkpoint == nil || run.Checkpoint.PendingDeviceAction == nil {
		return run, nil, nil
	}
	permit := *run.Checkpoint.PendingDeviceAction
	return run, &permit, nil
}

func (s *CommandService) SubmitDeviceActionReceipt(
	ctx context.Context,
	command SubmitDeviceActionReceiptCommand,
) (Run, error) {
	return s.mutate(
		ctx,
		command.UserID,
		command.RunID,
		command.CommandID,
		"device_action_receipt_submitted",
		map[string]string{
			"toolInvocationId": command.ToolInvocationID,
			"outcome":          command.Receipt.Outcome,
		},
		func(run *Run, now time.Time) error {
			if run.State != generated.AssistantRunStateWaitingExternal ||
				run.Checkpoint == nil ||
				run.Checkpoint.PendingDeviceAction == nil {
				return ErrInvalidTransition
			}
			permit := *run.Checkpoint.PendingDeviceAction
			receipt := command.Receipt
			if now.UTC().After(permit.ExpiresAt) ||
				permit.RunID != strings.TrimSpace(command.RunID) ||
				permit.ToolInvocationID != strings.TrimSpace(command.ToolInvocationID) ||
				permit.InstallationID != strings.TrimSpace(receipt.InstallationID) ||
				permit.DeviceID != strings.TrimSpace(receipt.DeviceID) ||
				permit.Capability != strings.TrimSpace(receipt.Capability) ||
				permit.InputDigest != strings.TrimSpace(receipt.InputDigest) ||
				permit.IdempotencyKey != strings.TrimSpace(receipt.IdempotencyKey) ||
				permit.IdempotencyKey != strings.TrimSpace(command.CommandID) ||
				permit.Permit != strings.TrimSpace(receipt.Permit) ||
				receipt.ExecutedAt.IsZero() {
				return ErrInvalidRun
			}
			outcome := strings.TrimSpace(receipt.Outcome)
			switch outcome {
			case "completed":
				if strings.TrimSpace(receipt.FailureCode) != "" {
					return ErrInvalidRun
				}
			case "unavailable", "denied", "failed":
				if strings.TrimSpace(receipt.FailureCode) == "" {
					return ErrInvalidRun
				}
			default:
				return ErrInvalidRun
			}
			receipt.InstallationID = strings.TrimSpace(receipt.InstallationID)
			receipt.DeviceID = strings.TrimSpace(receipt.DeviceID)
			receipt.Capability = strings.TrimSpace(receipt.Capability)
			receipt.InputDigest = strings.TrimSpace(receipt.InputDigest)
			receipt.Permit = strings.TrimSpace(receipt.Permit)
			receipt.IdempotencyKey = strings.TrimSpace(receipt.IdempotencyKey)
			receipt.Outcome = outcome
			receipt.ExecutedAt = receipt.ExecutedAt.UTC()
			receipt.DeviceObjectID = strings.TrimSpace(receipt.DeviceObjectID)
			receipt.FailureCode = strings.TrimSpace(receipt.FailureCode)
			run.Checkpoint.DeviceActionReceipts = append(
				run.Checkpoint.DeviceActionReceipts,
				receipt,
			)
			run.Checkpoint.PendingDeviceAction = nil
			if outcome == "completed" {
				run.Checkpoint.DecisionSummary = append(
					run.Checkpoint.DecisionSummary,
					"device_action_completed:"+permit.ToolInvocationID,
				)
				return run.Transition(generated.AssistantRunStateExecuting, "", now)
			}
			run.Checkpoint.DecisionSummary = append(
				run.Checkpoint.DecisionSummary,
				"device_action_failed:"+permit.ToolInvocationID+":"+outcome,
			)
			for index := range run.Items {
				if run.Items[index].ItemID == permit.ToolInvocationID &&
					run.Items[index].Status == generated.AssistantRunItemStatusStarted {
					if err := run.CompleteItem(
						run.Items[index].ItemID,
						generated.AssistantRunItemStatusCancelled,
						nil,
						"device_action_"+outcome,
						now,
					); err != nil {
						return err
					}
					break
				}
			}
			run.CancelActiveWork("device_action_"+outcome, now)
			return run.Transition(
				generated.AssistantRunStateCancelled,
				"device_action_"+outcome,
				now,
			)
		},
	)
}

type pendingDeviceActionIntentBinding struct {
	Capability  string
	InputDigest string
}

func pendingDeviceActionBinding(
	presentation map[string]any,
	runID string,
	toolInvocationID string,
	approvalPermit string,
	decision string,
	now time.Time,
) (pendingDeviceActionIntentBinding, bool) {
	for _, rawNode := range objectSlice(presentation["nodes"]) {
		action := objectValue(rawNode["action"])
		if strings.TrimSpace(stringValue(action["kind"])) != "ApproveTool" {
			continue
		}
		approveTool := objectValue(action["approveTool"])
		if strings.TrimSpace(stringValue(approveTool["runId"])) != runID ||
			strings.TrimSpace(stringValue(approveTool["toolInvocationId"])) !=
				toolInvocationID ||
			strings.TrimSpace(stringValue(approveTool["decision"])) != decision ||
			strings.TrimSpace(stringValue(approveTool["approvalPermit"])) !=
				approvalPermit {
			continue
		}
		expiresAt, err := time.Parse(
			time.RFC3339Nano,
			strings.TrimSpace(stringValue(action["expiresAt"])),
		)
		capability := strings.TrimSpace(stringValue(approveTool["capability"]))
		inputDigest := strings.TrimSpace(stringValue(approveTool["inputDigest"]))
		expectedDigest := actionIntentRequestDigest(approveTool)
		if err != nil || !now.UTC().Before(expiresAt.UTC()) ||
			capability == "" || inputDigest == "" ||
			expectedDigest == "" ||
			expectedDigest != strings.TrimSpace(stringValue(action["requestDigest"])) {
			continue
		}
		return pendingDeviceActionIntentBinding{
			Capability:  capability,
			InputDigest: inputDigest,
		}, true
	}
	return pendingDeviceActionIntentBinding{}, false
}

func objectSlice(value any) []map[string]any {
	switch values := value.(type) {
	case []map[string]any:
		return values
	case []any:
		result := make([]map[string]any, 0, len(values))
		for _, value := range values {
			if object := objectValue(value); object != nil {
				result = append(result, object)
			}
		}
		return result
	default:
		return nil
	}
}

func objectValue(value any) map[string]any {
	object, _ := value.(map[string]any)
	return object
}

func stringValue(value any) string {
	text, _ := value.(string)
	return text
}

func assistantRunContinuationToken(runID string, toolUseID string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(runID) + "\x00" + strings.TrimSpace(toolUseID)))
	return "ct_" + hex.EncodeToString(digest[:16])
}

func actionIntentRequestDigest(value map[string]any) string {
	encoded, err := json.Marshal(value)
	if err != nil {
		return ""
	}
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func newDeviceActionPermitIdentity() (string, string, error) {
	permitBytes := make([]byte, 32)
	if _, err := rand.Read(permitBytes); err != nil {
		return "", "", err
	}
	jtiBytes := make([]byte, 16)
	if _, err := rand.Read(jtiBytes); err != nil {
		return "", "", err
	}
	return "dap_" + hex.EncodeToString(permitBytes),
		"dapjti_" + hex.EncodeToString(jtiBytes),
		nil
}

func (s *CommandService) EventsAfter(
	ctx context.Context,
	userID string,
	runID string,
	afterSequence int64,
	limit int,
) ([]JournalEvent, error) {
	if _, err := s.Get(ctx, userID, runID); err != nil {
		return nil, err
	}
	return s.repository.EventsAfter(ctx, runID, afterSequence, limit)
}

func (s *CommandService) mutate(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
	eventKind string,
	commandPayload any,
	change func(*Run, time.Time) error,
) (Run, error) {
	commandID = strings.TrimSpace(commandID)
	if commandID == "" {
		return Run{}, ErrInvalidRun
	}
	payloadDigest, err := commandDigest(eventKind, commandPayload)
	if err != nil {
		return Run{}, err
	}
	receipt, err := s.repository.LoadCommandReceipt(ctx, runID, commandID)
	if err == nil {
		if receipt.CommandKind != eventKind ||
			receipt.PayloadDigest != payloadDigest {
			return Run{}, ErrRevisionConflict
		}
		return s.Get(ctx, userID, runID)
	}
	if !errors.Is(err, ErrRunNotFound) {
		return Run{}, err
	}
	run, err := s.Get(ctx, userID, runID)
	if err != nil {
		return Run{}, err
	}
	lastSequence := run.JournalSequence
	expectedRevision := run.Revision
	now := s.now().UTC().Truncate(time.Millisecond)
	if err := change(&run, now); err != nil {
		return Run{}, err
	}
	if run.Revision == expectedRevision {
		return run, nil
	}
	event := JournalEvent{
		EventID:   run.RunID + ":" + int64String(lastSequence+1),
		RunID:     run.RunID,
		Sequence:  lastSequence + 1,
		Revision:  run.Revision,
		Kind:      eventKind,
		Payload:   map[string]any{"status": run.State.WireName()},
		CreatedAt: now,
	}
	run.JournalSequence = event.Sequence
	if err := s.repository.Commit(
		ctx,
		expectedRevision,
		run,
		[]JournalEvent{event},
		&CommandReceipt{
			RunID:         run.RunID,
			CommandID:     commandID,
			CommandKind:   eventKind,
			PayloadDigest: payloadDigest,
			Revision:      run.Revision,
			CreatedAt:     now,
		},
	); err != nil {
		return Run{}, err
	}
	return run, nil
}

func commandDigest(kind string, payload any) (string, error) {
	encoded, err := json.Marshal(struct {
		Kind    string `json:"kind"`
		Payload any    `json:"payload"`
	}{
		Kind:    strings.TrimSpace(kind),
		Payload: payload,
	})
	if err != nil {
		return "", ErrInvalidRun
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

func normalizeStartCommand(command StartCommand, now time.Time) StartCommand {
	command.UserID = strings.TrimSpace(command.UserID)
	command.PersonaID = strings.TrimSpace(command.PersonaID)
	command.SessionID = strings.TrimSpace(command.SessionID)
	command.ClientRequestID = strings.TrimSpace(command.ClientRequestID)
	command.TraceID = strings.TrimSpace(command.TraceID)
	command.IntentKind = strings.TrimSpace(command.IntentKind)
	command.RequestedSkillID = strings.TrimSpace(command.RequestedSkillID)
	command.RequestedDomainID = strings.TrimSpace(command.RequestedDomainID)
	if command.IntentKind == "" {
		command.IntentKind = "answer"
	}
	command.InputText = strings.TrimSpace(command.InputText)
	if command.ReasoningProfile == "" {
		command.ReasoningProfile = generated.AssistantReasoningProfileBalanced
	}
	command.DefinitionOfDone.Outcome = strings.TrimSpace(command.DefinitionOfDone.Outcome)
	if command.DefinitionOfDone.Outcome == "" {
		command.DefinitionOfDone.Outcome = command.InputText
	}
	if len(command.DefinitionOfDone.VerificationRequirements) == 0 {
		command.DefinitionOfDone.VerificationRequirements = []string{"answer_present"}
	}
	if command.DefinitionOfDone.FrozenAt.IsZero() {
		command.DefinitionOfDone.FrozenAt = now.UTC()
	}
	return command
}

func personalSessionContinuityAllowed(surfaceKind string) bool {
	switch strings.ToLower(strings.TrimSpace(surfaceKind)) {
	case "conversation", "circle":
		return false
	default:
		return true
	}
}

func newRunID() (string, error) {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return "arn_" + hex.EncodeToString(buffer), nil
}

func int64String(value int64) string {
	if value == 0 {
		return "0"
	}
	var buffer [20]byte
	index := len(buffer)
	for value > 0 {
		index--
		buffer[index] = byte('0' + value%10)
		value /= 10
	}
	return string(buffer[index:])
}
