package runruntime

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
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
			return Run{}, ErrRunIdempotencyConflict
		}
		return existing, nil
	}
	if !errors.Is(err, ErrRunNotFound) {
		return Run{}, err
	}
	skillPackageID, skillPackageReleaseDigest, err :=
		s.skillPackages.ResolveActiveSkillPackage(ctx)
	if err != nil || strings.TrimSpace(skillPackageID) == "" ||
		!validSkillPackageDigest(strings.TrimSpace(skillPackageReleaseDigest)) {
		return Run{}, ErrSkillPackageUnavailable
	}
	skillPackageID = strings.TrimSpace(skillPackageID)
	skillPackageReleaseDigest = strings.TrimSpace(skillPackageReleaseDigest)
	frozenPackageContext := skillpkg.WithPackageRelease(
		ctx,
		skillpkg.PackageReleaseIdentity{
			PackageID:     skillPackageID,
			ReleaseDigest: skillPackageReleaseDigest,
		},
	)
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
		found, membershipErr := s.skillPackages.ContainsSkillInFrozenPackage(
			frozenPackageContext,
			command.RequestedSkillID,
		)
		if membershipErr != nil || !found {
			return Run{}, ErrSkillPackageUnavailable
		}
		if err := s.startAccess.AuthorizeStart(
			frozenPackageContext,
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
	if s.policies == nil {
		return Run{}, ErrPolicyUnavailable
	}
	policySelection, err := s.policies.ResolveFrozenPolicy(
		frozenPackageContext,
		"assistant-default",
		command.PersonaID,
		command.RequestedSkillID,
		command.RequestedDomainID,
	)
	if err != nil || !validPolicySelection(policySelection) {
		return Run{}, ErrPolicyUnavailable
	}
	policySkillID := strings.TrimSpace(policySelection.Template.SkillID)
	if policySkillID != "" && policySkillID != strings.TrimSpace(command.RequestedSkillID) {
		found, membershipErr := s.skillPackages.ContainsSkillInFrozenPackage(
			frozenPackageContext,
			policySkillID,
		)
		if membershipErr != nil || !found {
			return Run{}, ErrPolicyUnavailable
		}
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
			frozenPackageContext,
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
			if replayErr == nil {
				if replayed.ExecutionInputDigest != inputDigest {
					return Run{}, ErrRunIdempotencyConflict
				}
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
		strings.TrimSpace(selection.Template.SkillID) != "" &&
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
