package tooling

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	gatheringplanclient "quwoquan_service/generated/serviceclients/circlegatheringplan"
	runtimeauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
)

var (
	ErrGatheringToolDisabled = errors.New("gathering tool disabled")
	ErrGatheringToolBlocked  = errors.New("gathering tool blocked")
)

type GatheringToolAvailability struct {
	Enabled bool
	Blocked bool
	Reason  string
}

type GatheringDelegatedQueryGrantProvider interface {
	IssueGatheringQueryGrant(
		context.Context,
		GatheringExecutionContext,
		GatheringToolDefinition,
		runtimeauth.DelegatedResourceConstraint,
		string,
	) (string, error)
}

type GatheringHostAuthorityRequest struct {
	GatheringID     string
	HostSubjectKind string
	HostSubjectID   string
}

type GatheringHostAuthorityResolver interface {
	ResolveGatheringHostAuthority(
		context.Context,
		GatheringExecutionContext,
		GatheringHostAuthorityRequest,
	) (VerifiedGatheringHostAuthority, error)
}

type GatheringApprovalIntentIssuer interface {
	IssueGatheringApprovalIntent(
		context.Context,
		GatheringExecutionContext,
		GatheringToolDefinition,
	) (GatheringApprovalIntentContext, error)
}

type GatheringDispatcherDependencies struct {
	Executor        *GatheringExecutor
	QueryGrants     GatheringDelegatedQueryGrantProvider
	HostAuthorities GatheringHostAuthorityResolver
	ApprovalIntents GatheringApprovalIntentIssuer
	ProviderState   GatheringOptionalProviderState
	Availability    map[string]GatheringToolAvailability
	Now             func() time.Time
}

type GatheringDispatcher struct {
	catalog GatheringBindingCatalog
	deps    GatheringDispatcherDependencies
}

func NewGatheringDispatcher(
	catalog GatheringBindingCatalog,
	deps GatheringDispatcherDependencies,
) (*GatheringDispatcher, error) {
	for _, name := range GatheringToolNames() {
		if _, found := catalog.Definition(name); !found {
			return nil, fmt.Errorf("%s: %w", name, ErrGatheringToolUnavailable)
		}
	}
	if deps.Now == nil {
		deps.Now = time.Now
	}
	return &GatheringDispatcher{catalog: catalog, deps: deps}, nil
}

func (d *GatheringDispatcher) Handlers() map[string]tool.Handler {
	handlers := make(map[string]tool.Handler, len(GatheringToolNames()))
	for _, name := range GatheringToolNames() {
		toolName := name
		handlers[toolName] = func(ctx context.Context, request tool.Request) (tool.Result, error) {
			return d.execute(ctx, toolName, request)
		}
	}
	return handlers
}

func (d *GatheringDispatcher) ExecutableToolCount() int {
	count := 0
	for _, name := range GatheringToolNames() {
		availability, declared := d.deps.Availability[name]
		if !declared || (availability.Enabled && !availability.Blocked) {
			count++
		}
	}
	return count
}

func (d *GatheringDispatcher) execute(
	ctx context.Context,
	toolName string,
	request tool.Request,
) (tool.Result, error) {
	definition, found := d.catalog.Definition(toolName)
	if !found {
		return tool.Result{}, ErrGatheringToolUnavailable
	}
	if err := d.requireAvailable(toolName); err != nil {
		return tool.Result{}, err
	}
	execution, err := gatheringExecutionFromToolRequest(request)
	if err != nil {
		return tool.Result{}, err
	}
	switch toolName {
	case GatheringSearchPublicTool:
		return d.searchPublic(ctx, execution, definition, request)
	case GatheringReadPublicTool:
		return d.readPublic(ctx, execution, definition, request)
	case GatheringReadPrivateTool:
		return d.readPrivate(ctx, execution, definition, request)
	case GatheringProposeCreateDraftTool:
		return d.proposeCreateDraft(ctx, execution, definition, request)
	case GatheringProposeUpdateTool:
		return d.proposeUpdate(ctx, execution, definition, request)
	case GatheringWatchAvailabilityTool:
		return d.proposeWatchAvailability(ctx, execution, definition, request)
	case GatheringProposePlanTool:
		return d.proposePlan(ctx, execution, definition, request)
	default:
		return tool.Result{}, ErrGatheringToolUnavailable
	}
}

func (d *GatheringDispatcher) searchPublic(
	ctx context.Context,
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	request tool.Request,
) (tool.Result, error) {
	var input GatheringSearchPublicRequest
	if err := decodeGatheringInput(request.Input, &input); err != nil {
		return tool.Result{}, err
	}
	target := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering.source",
		ID:   strings.TrimSpace(input.SourceObjectTypeRef) + ":" + strings.TrimSpace(input.SourceObjectID),
	}
	grant, err := d.queryGrant(ctx, execution, definition, target, input, request.DelegatedGrant)
	if err != nil {
		return tool.Result{}, err
	}
	if d.deps.Executor == nil {
		return tool.Result{}, ErrGatheringToolUnavailable
	}
	output, err := d.deps.Executor.SearchPublic(ctx, execution, grant, input)
	if err != nil {
		return tool.Result{}, err
	}
	return gatheringToolResult(output)
}

func (d *GatheringDispatcher) readPublic(
	ctx context.Context,
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	request tool.Request,
) (tool.Result, error) {
	var input GatheringIDQuery
	if err := decodeGatheringInput(request.Input, &input); err != nil {
		return tool.Result{}, err
	}
	grant, err := d.queryGrant(
		ctx,
		execution,
		definition,
		gatheringTarget(input.GatheringID),
		input,
		request.DelegatedGrant,
	)
	if err != nil {
		return tool.Result{}, err
	}
	if d.deps.Executor == nil {
		return tool.Result{}, ErrGatheringToolUnavailable
	}
	output, err := d.deps.Executor.ReadPublic(ctx, execution, grant, input)
	if err != nil {
		return tool.Result{}, err
	}
	return gatheringToolResult(map[string]any{"gathering": output})
}

func (d *GatheringDispatcher) readPrivate(
	ctx context.Context,
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	request tool.Request,
) (tool.Result, error) {
	var input GatheringIDQuery
	if err := decodeGatheringInput(request.Input, &input); err != nil {
		return tool.Result{}, err
	}
	grant, err := d.queryGrant(
		ctx,
		execution,
		definition,
		gatheringTarget(input.GatheringID),
		input,
		request.DelegatedGrant,
	)
	if err != nil {
		return tool.Result{}, err
	}
	if d.deps.Executor == nil {
		return tool.Result{}, ErrGatheringToolUnavailable
	}
	output, err := d.deps.Executor.ReadPrivate(ctx, execution, grant, input)
	if err != nil {
		return tool.Result{}, err
	}
	return gatheringToolResult(output)
}

func (d *GatheringDispatcher) proposeCreateDraft(
	ctx context.Context,
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	request tool.Request,
) (tool.Result, error) {
	var input GatheringCreateDraftProposalInput
	if err := decodeGatheringInput(request.Input, &input); err != nil {
		return tool.Result{}, err
	}
	authority, err := d.hostAuthority(ctx, execution, GatheringHostAuthorityRequest{
		HostSubjectKind: input.HostSubjectKind,
		HostSubjectID:   input.HostSubjectID,
	})
	if err != nil {
		return tool.Result{}, err
	}
	intent, err := d.approvalIntent(ctx, execution, definition)
	if err != nil {
		return tool.Result{}, err
	}
	proposal, err := MapGatheringCreateDraftProposal(
		execution,
		definition,
		input,
		authority,
		intent,
		d.deps.ProviderState,
		d.deps.Now().UTC(),
	)
	if err != nil {
		return tool.Result{}, err
	}
	return gatheringProposalResult(proposal, proposal.Envelope)
}

func (d *GatheringDispatcher) proposeUpdate(
	ctx context.Context,
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	request tool.Request,
) (tool.Result, error) {
	var input GatheringUpdateProposalInput
	if err := decodeGatheringInput(request.Input, &input); err != nil {
		return tool.Result{}, err
	}
	authority, err := d.hostAuthority(ctx, execution, GatheringHostAuthorityRequest{
		GatheringID:     input.GatheringID,
		HostSubjectKind: input.HostSubjectKind,
		HostSubjectID:   input.HostSubjectID,
	})
	if err != nil {
		return tool.Result{}, err
	}
	intent, err := d.approvalIntent(ctx, execution, definition)
	if err != nil {
		return tool.Result{}, err
	}
	proposal, err := MapGatheringUpdateProposal(
		execution,
		definition,
		input,
		authority,
		intent,
		d.deps.ProviderState,
		d.deps.Now().UTC(),
	)
	if err != nil {
		return tool.Result{}, err
	}
	return gatheringProposalResult(proposal, proposal.Envelope)
}

func (d *GatheringDispatcher) proposeWatchAvailability(
	ctx context.Context,
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	request tool.Request,
) (tool.Result, error) {
	var input GatheringAvailabilityWatchCommand
	if err := decodeGatheringInput(request.Input, &input); err != nil {
		return tool.Result{}, err
	}
	intent, err := d.approvalIntent(ctx, execution, definition)
	if err != nil {
		return tool.Result{}, err
	}
	proposal, err := MapGatheringAvailabilityWatchProposal(
		execution,
		definition,
		input,
		intent,
	)
	if err != nil {
		return tool.Result{}, err
	}
	return gatheringProposalResult(proposal, proposal.Envelope)
}

func (d *GatheringDispatcher) proposePlan(
	ctx context.Context,
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	request tool.Request,
) (tool.Result, error) {
	var input gatheringplanclient.ProposeGatheringPlanCommand
	if err := decodeGatheringInput(request.Input, &input); err != nil {
		return tool.Result{}, err
	}
	intent, err := d.approvalIntent(ctx, execution, definition)
	if err != nil {
		return tool.Result{}, err
	}
	proposal, err := MapGatheringPlanProposal(
		execution,
		definition,
		input,
		intent,
	)
	if err != nil {
		return tool.Result{}, err
	}
	return gatheringProposalResult(proposal, proposal.Envelope)
}

func (d *GatheringDispatcher) queryGrant(
	ctx context.Context,
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	target runtimeauth.DelegatedResourceConstraint,
	request any,
	explicit string,
) (string, error) {
	if token := strings.TrimSpace(explicit); token != "" {
		return token, nil
	}
	if d.deps.QueryGrants == nil {
		return "", ErrGatheringToolUnavailable
	}
	digest, err := CanonicalGatheringRequestDigest(request)
	if err != nil {
		return "", err
	}
	return d.deps.QueryGrants.IssueGatheringQueryGrant(
		ctx,
		execution,
		definition,
		target,
		digest,
	)
}

func (d *GatheringDispatcher) hostAuthority(
	ctx context.Context,
	execution GatheringExecutionContext,
	request GatheringHostAuthorityRequest,
) (VerifiedGatheringHostAuthority, error) {
	if d.deps.HostAuthorities == nil {
		return VerifiedGatheringHostAuthority{}, ErrGatheringToolUnavailable
	}
	return d.deps.HostAuthorities.ResolveGatheringHostAuthority(ctx, execution, request)
}

func (d *GatheringDispatcher) approvalIntent(
	ctx context.Context,
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
) (GatheringApprovalIntentContext, error) {
	if d.deps.ApprovalIntents == nil {
		return GatheringApprovalIntentContext{}, ErrGatheringToolUnavailable
	}
	return d.deps.ApprovalIntents.IssueGatheringApprovalIntent(ctx, execution, definition)
}

func (d *GatheringDispatcher) requireAvailable(toolName string) error {
	availability, declared := d.deps.Availability[toolName]
	if !declared {
		return nil
	}
	reason := strings.TrimSpace(availability.Reason)
	if reason == "" {
		reason = toolName
	}
	if availability.Blocked {
		return fmt.Errorf("%w: %s", ErrGatheringToolBlocked, reason)
	}
	if !availability.Enabled {
		return fmt.Errorf("%w: %s", ErrGatheringToolDisabled, reason)
	}
	return nil
}

func gatheringExecutionFromToolRequest(request tool.Request) (GatheringExecutionContext, error) {
	conversationKind := GatheringConversationGroup
	if strings.TrimSpace(request.SurfaceKind) == "personal" {
		conversationKind = GatheringConversationDirect
	}
	execution := GatheringExecutionContext{
		AccountID:        strings.TrimSpace(request.AccountID),
		PersonaID:        strings.TrimSpace(request.PersonaID),
		RunID:            strings.TrimSpace(request.RunID),
		ToolInvocationID: strings.TrimSpace(request.ToolUseID),
		Surface:          GatheringConversationSurface,
		IdempotencyKey:   strings.TrimSpace(request.IdempotencyKey),
		Conversation: GatheringConversationContext{
			Kind:           conversationKind,
			ConversationID: strings.TrimSpace(request.SurfaceID),
		},
	}
	if err := execution.validate(); err != nil {
		return GatheringExecutionContext{}, err
	}
	return execution, nil
}

func gatheringProposalResult(
	proposal any,
	envelope GatheringProposalEnvelope,
) (tool.Result, error) {
	if envelope.Approval == nil {
		return tool.Result{}, ErrGatheringBindingInvalid
	}
	return tool.Result{
		Output: map[string]any{
			"proposalId":         envelope.ProposalID,
			"status":             envelope.Status,
			"summary":            envelope.Summary,
			"requestDigest":      envelope.RequestDigest,
			"domainOperationId":  envelope.Binding.OperationID,
			"approvalIntentKind": string(envelope.Approval.Kind),
		},
		TypedProposal:  proposal,
		ApprovalIntent: envelope.Approval,
	}, nil
}

func gatheringToolResult(value any) (tool.Result, error) {
	if output, ok := value.(map[string]any); ok {
		return tool.Result{Output: output}, nil
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return tool.Result{}, err
	}
	output := map[string]any{}
	if err := json.Unmarshal(encoded, &output); err != nil {
		return tool.Result{}, err
	}
	return tool.Result{Output: output}, nil
}

func decodeGatheringInput(input map[string]any, target any) error {
	encoded, err := json.Marshal(input)
	if err != nil {
		return ErrGatheringBindingInvalid
	}
	if err := json.Unmarshal(encoded, target); err != nil {
		return ErrGatheringBindingInvalid
	}
	return nil
}
