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
)

type StartCommand struct {
	UserID                  string
	PersonaID               string
	SessionID               string
	ClientRequestID         string
	TraceID                 string
	RequestContext          RequestContext
	IntentKind              string
	InputText               string
	RequestedSkillID        string
	RequestedDomainID       string
	Trigger                 map[string]any
	ContextSnapshot         map[string]any
	SurfaceCapabilities     map[string]any
	SessionPreferenceFacts  []preferencemodel.Snapshot
	LongTermPreferenceFacts []preferencemodel.Snapshot
	ReasoningProfile        generated.AssistantReasoningProfile
	DefinitionOfDone        DefinitionOfDone
}

type ContinueToolUseCommand struct {
	UserID            string
	RunID             string
	ToolUseID         string
	CommandID         string
	Decision          string
	ContinuationToken string
	ExecutionReceipt  *DeviceActionExecutionReceipt
}

type SessionAuthorizer interface {
	AuthorizeSession(context.Context, string, string) error
}

type SessionAuthorizerFunc func(context.Context, string, string) error

func (f SessionAuthorizerFunc) AuthorizeSession(
	ctx context.Context,
	userID string,
	sessionID string,
) error {
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
	repository    Repository
	sessions      SessionAuthorizer
	skillPackages SkillPackageIdentityResolver
	startAccess   StartAccessPolicy
	policies      PolicyResolver
	now           func() time.Time
	newRunID      func() (string, error)
	cancel        *CancellationCoordinator
}

func NewCommandService(
	repository Repository,
	sessions SessionAuthorizer,
	skillPackages SkillPackageIdentityResolver,
	startAccess StartAccessPolicy,
	now func() time.Time,
	cancel *CancellationCoordinator,
	policies ...PolicyResolver,
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
	if len(policies) > 0 {
		service.policies = policies[0]
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
	if err := s.sessions.AuthorizeSession(
		ctx,
		command.UserID,
		command.SessionID,
	); err != nil {
		return Run{}, err
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
	if err := run.BindSkillPackage(
		skillPackageID,
		skillPackageReleaseDigest,
	); err != nil {
		return Run{}, err
	}
	run.FrozenPolicySelection = clonePolicySelection(policySelection)
	run.SessionPreferenceFacts = append(
		[]preferencemodel.Snapshot(nil),
		command.SessionPreferenceFacts...,
	)
	run.LongTermPreferenceFacts = append(
		[]preferencemodel.Snapshot(nil),
		command.LongTermPreferenceFacts...,
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
		snapshot := map[string]any{
			"answerText": "",
			"processes":  []map[string]any{},
		}
		if run.FrozenPolicySelection.PolicyID != "" {
			snapshot["selectedPolicyRef"] = map[string]any{
				"policyId":      run.FrozenPolicySelection.PolicyID,
				"releaseDigest": run.FrozenPolicySelection.ReleaseDigest,
				"cohort":        run.FrozenPolicySelection.Cohort,
			}
		}
		return run.SetTerminalSnapshot(snapshot, now)
	})
	observeCancelDuration(startedAt, err)
	return run, err
}

func (s *CommandService) ContinueToolUse(
	ctx context.Context,
	command ContinueToolUseCommand,
) (Run, error) {
	decision := strings.TrimSpace(command.Decision)
	if decision != "approved" && decision != "rejected" {
		return Run{}, ErrInvalidRun
	}
	executionOutcome := ""
	if command.ExecutionReceipt != nil {
		executionOutcome = strings.TrimSpace(command.ExecutionReceipt.Outcome)
	}
	return s.mutate(
		ctx,
		command.UserID,
		command.RunID,
		command.CommandID,
		"tool_use_continued",
		map[string]string{
			"toolUseId":        command.ToolUseID,
			"decision":         decision,
			"executionOutcome": executionOutcome,
		},
		func(run *Run, now time.Time) error {
			if run.State != generated.AssistantRunStateWaitingApproval ||
				run.Checkpoint == nil ||
				run.Checkpoint.PendingApprovalRef != strings.TrimSpace(command.ToolUseID) ||
				strings.TrimSpace(command.ContinuationToken) !=
					assistantRunContinuationToken(run.RunID, command.ToolUseID) {
				return ErrInvalidTransition
			}
			expectedActionKind, valid := pendingDeviceActionKind(
				run.PresentationDocument,
				strings.TrimSpace(command.ToolUseID),
				strings.TrimSpace(command.ContinuationToken),
			)
			if !valid {
				return ErrInvalidRun
			}
			if err := validateDeviceActionExecutionReceipt(
				command,
				decision,
				expectedActionKind,
			); err != nil {
				return err
			}
			run.Checkpoint.PendingApprovalRef = ""
			if command.ExecutionReceipt != nil {
				receipt := *command.ExecutionReceipt
				receipt.ActionKind = strings.TrimSpace(receipt.ActionKind)
				receipt.IdempotencyKey = strings.TrimSpace(receipt.IdempotencyKey)
				receipt.Outcome = strings.TrimSpace(receipt.Outcome)
				receipt.ExecutedAt = receipt.ExecutedAt.UTC()
				receipt.DeviceObjectID = strings.TrimSpace(receipt.DeviceObjectID)
				receipt.FailureCode = strings.TrimSpace(receipt.FailureCode)
				run.Checkpoint.DeviceActionReceipts = append(
					run.Checkpoint.DeviceActionReceipts,
					receipt,
				)
			}
			if decision == "approved" {
				run.Checkpoint.DecisionSummary = append(
					run.Checkpoint.DecisionSummary,
					"device_action_completed:"+strings.TrimSpace(command.ToolUseID),
				)
				return run.Transition(generated.AssistantRunStateExecuting, "", now)
			}
			if command.ExecutionReceipt != nil {
				run.Checkpoint.DecisionSummary = append(
					run.Checkpoint.DecisionSummary,
					"device_action_failed:"+
						strings.TrimSpace(command.ToolUseID)+":"+
						strings.TrimSpace(command.ExecutionReceipt.Outcome),
				)
			}
			for index := range run.Items {
				if run.Items[index].ItemID == strings.TrimSpace(command.ToolUseID) &&
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
}

func validateDeviceActionExecutionReceipt(
	command ContinueToolUseCommand,
	decision string,
	expectedActionKind string,
) error {
	receipt := command.ExecutionReceipt
	expectedActionKind = strings.TrimSpace(expectedActionKind)
	if expectedActionKind == "" {
		return ErrInvalidRun
	}
	if decision == "rejected" {
		if receipt == nil {
			return nil
		}
		outcome := strings.TrimSpace(receipt.Outcome)
		if strings.TrimSpace(receipt.ActionKind) != expectedActionKind ||
			strings.TrimSpace(receipt.IdempotencyKey) != strings.TrimSpace(command.ToolUseID) ||
			(outcome != "unavailable" && outcome != "denied" && outcome != "failed") ||
			receipt.ExecutedAt.IsZero() ||
			strings.TrimSpace(receipt.FailureCode) == "" {
			return ErrInvalidRun
		}
		return nil
	}
	if receipt == nil ||
		strings.TrimSpace(receipt.ActionKind) != expectedActionKind ||
		strings.TrimSpace(receipt.IdempotencyKey) != strings.TrimSpace(command.ToolUseID) ||
		strings.TrimSpace(receipt.Outcome) != "completed" ||
		receipt.ExecutedAt.IsZero() ||
		strings.TrimSpace(receipt.FailureCode) != "" {
		return ErrInvalidRun
	}
	return nil
}

func pendingDeviceActionKind(
	presentation map[string]any,
	toolUseID string,
	continuationToken string,
) (string, bool) {
	for _, rawNode := range objectSlice(presentation["nodes"]) {
		action := objectValue(rawNode["action"])
		if strings.TrimSpace(stringValue(action["operation"])) != "ContinueAssistantToolUse" ||
			strings.TrimSpace(stringValue(action["objectTypeRef"])) != "assistant_tool_use" ||
			strings.TrimSpace(stringValue(action["objectId"])) != toolUseID {
			continue
		}
		payload := objectValue(action["payload"])
		if strings.TrimSpace(stringValue(payload["decision"])) != "approved" ||
			strings.TrimSpace(stringValue(payload["continuationToken"])) != continuationToken {
			continue
		}
		deviceAction := objectValue(payload["deviceAction"])
		kind := strings.TrimSpace(stringValue(deviceAction["kind"]))
		if kind == "" ||
			strings.TrimSpace(stringValue(deviceAction["idempotencyKey"])) != toolUseID {
			continue
		}
		return kind, true
	}
	return "", false
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
