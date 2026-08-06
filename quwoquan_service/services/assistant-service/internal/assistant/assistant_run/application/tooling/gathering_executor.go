package tooling

import (
	"context"
	"fmt"
	"strings"

	gatheringplanclient "quwoquan_service/generated/serviceclients/circlegatheringplan"
	runtimeauth "quwoquan_service/runtime/auth"
)

type GatheringConversationKind string

const (
	GatheringConversationDirect GatheringConversationKind = "direct"
	GatheringConversationGroup  GatheringConversationKind = "group"
)

type GatheringConversationContext struct {
	Kind           GatheringConversationKind `json:"kind"`
	ConversationID string                    `json:"conversationId"`
}

type GatheringExecutionContext struct {
	AccountID        string                       `json:"accountId"`
	PersonaID        string                       `json:"personaId"`
	RunID            string                       `json:"runId"`
	ToolInvocationID string                       `json:"toolInvocationId"`
	Surface          string                       `json:"surface"`
	IdempotencyKey   string                       `json:"idempotencyKey"`
	ApprovalRef      string                       `json:"approvalRef"`
	Conversation     GatheringConversationContext `json:"conversation"`
}

func (c GatheringExecutionContext) validate() error {
	if strings.TrimSpace(c.AccountID) == "" ||
		strings.TrimSpace(c.PersonaID) == "" ||
		strings.TrimSpace(c.RunID) == "" ||
		strings.TrimSpace(c.ToolInvocationID) == "" ||
		strings.TrimSpace(c.IdempotencyKey) == "" ||
		c.Surface != GatheringConversationSurface ||
		strings.TrimSpace(c.Conversation.ConversationID) == "" {
		return ErrGatheringBindingInvalid
	}
	switch c.Conversation.Kind {
	case GatheringConversationDirect, GatheringConversationGroup:
		return nil
	default:
		return ErrGatheringBindingInvalid
	}
}

type GatheringSearchPublicRequest struct {
	SourceObjectTypeRef string `json:"sourceObjectTypeRef"`
	SourceObjectID      string `json:"sourceObjectId"`
	Cursor              string `json:"cursor,omitempty"`
	Limit               int    `json:"limit"`
}

type GatheringIDQuery struct {
	GatheringID string `json:"gatheringId"`
}

type PublicGatheringCard struct {
	GatheringID       string `json:"gatheringId"`
	Title             string `json:"title"`
	Summary           string `json:"summary"`
	StartAt           string `json:"startAt"`
	EndAt             string `json:"endAt"`
	MeetingPointLabel string `json:"meetingPointLabel"`
	RemainingCapacity int    `json:"remainingCapacity"`
	AdmissionMode     string `json:"admissionMode"`
}

type PublicGatheringPage struct {
	Gatherings []PublicGatheringCard `json:"gatherings"`
	NextCursor string                `json:"nextCursor,omitempty"`
}

type PublicGatheringDetail struct {
	GatheringID       string `json:"gatheringId"`
	Title             string `json:"title"`
	Summary           string `json:"summary"`
	StartAt           string `json:"startAt"`
	EndAt             string `json:"endAt"`
	MeetingPointLabel string `json:"meetingPointLabel"`
	RemainingCapacity int    `json:"remainingCapacity"`
	AdmissionMode     string `json:"admissionMode"`
	Status            string `json:"status"`
}

type GatheringViewerAuthority string

const (
	GatheringViewerParticipation GatheringViewerAuthority = "participation"
	GatheringViewerHost          GatheringViewerAuthority = "host"
)

type PrivateGatheringDetail struct {
	GatheringID         string                   `json:"gatheringId"`
	Title               string                   `json:"title"`
	Purpose             string                   `json:"purpose"`
	StartAt             string                   `json:"startAt"`
	EndAt               string                   `json:"endAt"`
	ExactMeetingPoint   string                   `json:"exactMeetingPoint"`
	Capacity            int                      `json:"capacity"`
	CurrentParticipants int                      `json:"currentParticipants"`
	AdmissionMode       string                   `json:"admissionMode"`
	Version             int64                    `json:"version"`
	ViewerAuthority     GatheringViewerAuthority `json:"viewerAuthority"`
}

type PrivateGatheringResult struct {
	Gathering       PrivateGatheringDetail `json:"gathering"`
	RedactionPolicy string                 `json:"redactionPolicy"`
}

type GatheringAvailabilityWatchCommand struct {
	GatheringID              string `json:"gatheringId"`
	ExpectedGatheringVersion int64  `json:"expectedGatheringVersion"`
	ExpectedWatchVersion     int64  `json:"expectedWatchVersion"`
}

type GatheringCommandResult struct {
	GatheringID                string `json:"gatheringId"`
	AggregateVersion           int64  `json:"aggregateVersion"`
	LifecycleStatus            string `json:"lifecycleStatus"`
	ParticipationState         string `json:"participationState,omitempty"`
	ParticipationVersion       int64  `json:"participationVersion,omitempty"`
	CurrentGatheringRevisionID string `json:"currentGatheringRevisionId,omitempty"`
	CurrentGatheringRevisionNo int    `json:"currentGatheringRevisionNumber"`
	OutcomeStatus              string `json:"outcomeStatus,omitempty"`
	ConversationID             string `json:"conversationId,omitempty"`
	RoomBindingStatus          string `json:"roomBindingStatus"`
	IdempotentReplay           bool   `json:"idempotentReplay"`
}

type VerifiedGatheringQueryCall struct {
	Binding         DomainOperationBinding
	Grant           runtimeauth.DelegatedQueryGrant
	SerializedGrant string `json:"-"`
}

type VerifiedGatheringCommandCall struct {
	Binding         DomainOperationBinding
	Grant           runtimeauth.DelegatedCommandGrant
	SerializedGrant string `json:"-"`
}

// GeneratedGatheringClient is the only Circle execution boundary. Production
// composition must provide an adapter over the generated Circle client. This
// package intentionally contains no HTTP transport, fallback data or success
// synthesis; nil means fail-closed unavailable. Tests may provide typed fakes.
type GeneratedGatheringClient interface {
	OperationContractDigest(operationID string) string
	SearchPublic(
		ctx context.Context,
		call VerifiedGatheringQueryCall,
		request GatheringSearchPublicRequest,
	) (PublicGatheringPage, error)
	ReadPublic(
		ctx context.Context,
		call VerifiedGatheringQueryCall,
		request GatheringIDQuery,
	) (PublicGatheringDetail, error)
	ReadPrivate(
		ctx context.Context,
		call VerifiedGatheringQueryCall,
		request GatheringIDQuery,
	) (PrivateGatheringDetail, error)
	WatchAvailability(
		ctx context.Context,
		call VerifiedGatheringCommandCall,
		request GatheringAvailabilityWatchCommand,
		idempotencyKey string,
	) (GatheringCommandResult, error)
	ProposeGatheringPlan(
		ctx context.Context,
		call VerifiedGatheringCommandCall,
		request gatheringplanclient.ProposeGatheringPlanCommand,
		idempotencyKey string,
	) (gatheringplanclient.GatheringPlanCommandResult, error)
}

type GatheringExecutor struct {
	catalog         GatheringBindingCatalog
	queryVerifier   *runtimeauth.DelegatedGrantVerifier
	commandConsumer *runtimeauth.DelegatedCommandGrantConsumer
	client          GeneratedGatheringClient
}

func NewGatheringExecutor(
	catalog GatheringBindingCatalog,
	queryVerifier *runtimeauth.DelegatedGrantVerifier,
	commandConsumer *runtimeauth.DelegatedCommandGrantConsumer,
	client GeneratedGatheringClient,
) *GatheringExecutor {
	return &GatheringExecutor{
		catalog:         catalog,
		queryVerifier:   queryVerifier,
		commandConsumer: commandConsumer,
		client:          client,
	}
}

func (e *GatheringExecutor) SearchPublic(
	ctx context.Context,
	execution GatheringExecutionContext,
	delegatedQueryGrant string,
	request GatheringSearchPublicRequest,
) (PublicGatheringPage, error) {
	definition, err := e.definition(GatheringSearchPublicTool)
	if err != nil {
		return PublicGatheringPage{}, err
	}
	if strings.TrimSpace(request.SourceObjectTypeRef) == "" ||
		strings.TrimSpace(request.SourceObjectID) == "" ||
		request.Limit < 1 ||
		request.Limit > 50 {
		return PublicGatheringPage{}, ErrGatheringBindingInvalid
	}
	target := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering.source",
		ID:   request.SourceObjectTypeRef + ":" + request.SourceObjectID,
	}
	call, err := e.verifyQuery(
		ctx,
		execution,
		delegatedQueryGrant,
		definition,
		target,
		request,
	)
	if err != nil {
		return PublicGatheringPage{}, err
	}
	if err := e.ensureClientBinding(definition); err != nil {
		return PublicGatheringPage{}, err
	}
	return e.client.SearchPublic(ctx, call, request)
}

func (e *GatheringExecutor) ReadPublic(
	ctx context.Context,
	execution GatheringExecutionContext,
	delegatedQueryGrant string,
	request GatheringIDQuery,
) (PublicGatheringDetail, error) {
	definition, err := e.definition(GatheringReadPublicTool)
	if err != nil {
		return PublicGatheringDetail{}, err
	}
	target := gatheringTarget(request.GatheringID)
	if strings.TrimSpace(target.ID) == "" {
		return PublicGatheringDetail{}, ErrGatheringBindingInvalid
	}
	call, err := e.verifyQuery(
		ctx,
		execution,
		delegatedQueryGrant,
		definition,
		target,
		request,
	)
	if err != nil {
		return PublicGatheringDetail{}, err
	}
	if err := e.ensureClientBinding(definition); err != nil {
		return PublicGatheringDetail{}, err
	}
	return e.client.ReadPublic(ctx, call, request)
}

func (e *GatheringExecutor) ReadPrivate(
	ctx context.Context,
	execution GatheringExecutionContext,
	delegatedQueryGrant string,
	request GatheringIDQuery,
) (PrivateGatheringResult, error) {
	definition, err := e.definition(GatheringReadPrivateTool)
	if err != nil {
		return PrivateGatheringResult{}, err
	}
	target := gatheringTarget(request.GatheringID)
	if strings.TrimSpace(target.ID) == "" {
		return PrivateGatheringResult{}, ErrGatheringBindingInvalid
	}
	call, err := e.verifyQuery(
		ctx,
		execution,
		delegatedQueryGrant,
		definition,
		target,
		request,
	)
	if err != nil {
		return PrivateGatheringResult{}, err
	}
	if err := e.ensureClientBinding(definition); err != nil {
		return PrivateGatheringResult{}, err
	}
	detail, err := e.client.ReadPrivate(ctx, call, request)
	if err != nil {
		return PrivateGatheringResult{}, err
	}
	if detail.GatheringID != request.GatheringID {
		return PrivateGatheringResult{}, ErrGatheringBindingInvalid
	}
	switch detail.ViewerAuthority {
	case GatheringViewerParticipation, GatheringViewerHost:
	default:
		return PrivateGatheringResult{}, ErrGatheringHostUnauthorized
	}
	return PrivateGatheringResult{
		Gathering:       detail,
		RedactionPolicy: GatheringPrivateRedactionPolicy,
	}, nil
}

// ExecuteConfirmedAvailabilityWatch accepts the owner command exactly,
// requires a consumed single-use command grant, and cannot join, approve,
// invite or reserve a seat.
func (e *GatheringExecutor) ExecuteConfirmedAvailabilityWatch(
	ctx context.Context,
	execution GatheringExecutionContext,
	delegatedCommandGrant string,
	binding DomainOperationBinding,
	request GatheringAvailabilityWatchCommand,
) (GatheringCommandResult, error) {
	definition, err := e.definition(GatheringWatchAvailabilityTool)
	if err != nil {
		return GatheringCommandResult{}, err
	}
	if request.ExpectedGatheringVersion < 1 || request.ExpectedWatchVersion < 0 {
		return GatheringCommandResult{}, ErrGatheringBindingInvalid
	}
	if e.commandConsumer == nil {
		return GatheringCommandResult{}, ErrGatheringToolUnavailable
	}
	if err := e.ensureClientBinding(definition); err != nil {
		return GatheringCommandResult{}, err
	}
	if err := execution.validate(); err != nil ||
		strings.TrimSpace(execution.ApprovalRef) == "" {
		return GatheringCommandResult{}, ErrGatheringBindingInvalid
	}
	requestDigest, err := CanonicalGatheringRequestDigest(request)
	if err != nil {
		return GatheringCommandResult{}, err
	}
	target := gatheringTarget(request.GatheringID)
	if err := binding.ValidateAgainst(definition, requestDigest, target); err != nil {
		return GatheringCommandResult{}, err
	}
	grant, err := e.commandConsumer.Consume(
		ctx,
		delegatedCommandGrant,
		delegatedExpectation(execution, definition, target, requestDigest),
	)
	if err != nil {
		return GatheringCommandResult{}, err
	}
	return e.client.WatchAvailability(
		ctx,
		VerifiedGatheringCommandCall{
			Binding:         binding,
			Grant:           grant,
			SerializedGrant: delegatedCommandGrant,
		},
		request,
		execution.IdempotencyKey,
	)
}

// ExecuteConfirmedGatheringPlanProposal submits only the canonical
// ProposeGatheringPlan command after approval. It deliberately cannot create a
// plan or commit/accept a proposal; those are separate Circle operations.
func (e *GatheringExecutor) ExecuteConfirmedGatheringPlanProposal(
	ctx context.Context,
	execution GatheringExecutionContext,
	delegatedCommandGrant string,
	binding DomainOperationBinding,
	request gatheringplanclient.ProposeGatheringPlanCommand,
) (gatheringplanclient.GatheringPlanCommandResult, error) {
	definition, err := e.definition(GatheringProposePlanTool)
	if err != nil {
		return gatheringplanclient.GatheringPlanCommandResult{}, err
	}
	if strings.TrimSpace(request.PlanID) == "" ||
		request.ExpectedPlanVersion < 1 ||
		strings.TrimSpace(request.BaseRevisionID) == "" ||
		request.BaseRevisionNumber < 1 ||
		strings.TrimSpace(request.BaseRevisionDigest) == "" {
		return gatheringplanclient.GatheringPlanCommandResult{},
			ErrGatheringBindingInvalid
	}
	if e.commandConsumer == nil {
		return gatheringplanclient.GatheringPlanCommandResult{},
			ErrGatheringToolUnavailable
	}
	if err := e.ensureClientBinding(definition); err != nil {
		return gatheringplanclient.GatheringPlanCommandResult{}, err
	}
	if err := execution.validate(); err != nil ||
		strings.TrimSpace(execution.ApprovalRef) == "" {
		return gatheringplanclient.GatheringPlanCommandResult{},
			ErrGatheringBindingInvalid
	}
	packet, err := gatheringplanclient.EncodeProposeGatheringPlan(request)
	if err != nil {
		return gatheringplanclient.GatheringPlanCommandResult{}, err
	}
	requestDigest := gatheringplanclient.CanonicalRequestDigest(
		packet.CanonicalRequest,
	)
	target := gatheringPlanTarget(request.PlanID)
	if err := binding.ValidateAgainst(definition, requestDigest, target); err != nil {
		return gatheringplanclient.GatheringPlanCommandResult{}, err
	}
	grant, err := e.commandConsumer.Consume(
		ctx,
		delegatedCommandGrant,
		delegatedExpectation(execution, definition, target, requestDigest),
	)
	if err != nil {
		return gatheringplanclient.GatheringPlanCommandResult{}, err
	}
	return e.client.ProposeGatheringPlan(
		ctx,
		VerifiedGatheringCommandCall{
			Binding:         binding,
			Grant:           grant,
			SerializedGrant: delegatedCommandGrant,
		},
		request,
		execution.IdempotencyKey,
	)
}

func (e *GatheringExecutor) verifyQuery(
	ctx context.Context,
	execution GatheringExecutionContext,
	token string,
	definition GatheringToolDefinition,
	target runtimeauth.DelegatedResourceConstraint,
	request any,
) (VerifiedGatheringQueryCall, error) {
	if e.queryVerifier == nil {
		return VerifiedGatheringQueryCall{}, ErrGatheringToolUnavailable
	}
	if err := execution.validate(); err != nil {
		return VerifiedGatheringQueryCall{}, err
	}
	requestDigest, err := CanonicalGatheringRequestDigest(request)
	if err != nil {
		return VerifiedGatheringQueryCall{}, err
	}
	binding, err := NewDomainOperationBinding(definition, requestDigest, target)
	if err != nil {
		return VerifiedGatheringQueryCall{}, err
	}
	if err := binding.ValidateAgainst(definition, requestDigest, target); err != nil {
		return VerifiedGatheringQueryCall{}, err
	}
	grant, err := e.queryVerifier.VerifyQuery(
		ctx,
		token,
		delegatedExpectation(execution, definition, target, requestDigest),
	)
	if err != nil {
		return VerifiedGatheringQueryCall{}, err
	}
	return VerifiedGatheringQueryCall{
		Binding:         binding,
		Grant:           grant,
		SerializedGrant: token,
	}, nil
}

func (e *GatheringExecutor) definition(toolName string) (GatheringToolDefinition, error) {
	definition, found := e.catalog.Definition(toolName)
	if !found {
		return GatheringToolDefinition{}, fmt.Errorf(
			"%w: definition %s absent",
			ErrGatheringToolUnavailable,
			toolName,
		)
	}
	return definition, nil
}

func (e *GatheringExecutor) ensureClientBinding(
	definition GatheringToolDefinition,
) error {
	if e.client == nil {
		return ErrGatheringToolUnavailable
	}
	if e.client.OperationContractDigest(
		definition.OwnerOperationID,
	) != definition.ContractDigest {
		return ErrGatheringBindingInvalid
	}
	return nil
}

func delegatedExpectation(
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	target runtimeauth.DelegatedResourceConstraint,
	requestDigest string,
) runtimeauth.DelegatedGrantExpectation {
	return runtimeauth.DelegatedGrantExpectation{
		Audience:         GatheringDelegateAudience,
		DelegateService:  GatheringDelegateService,
		AccountID:        execution.AccountID,
		PersonaID:        execution.PersonaID,
		RunID:            execution.RunID,
		ToolInvocationID: execution.ToolInvocationID,
		OperationID:      definition.OwnerOperationID,
		Resource:         target,
		RequestDigest:    requestDigest,
		Surface:          execution.Surface,
		Scopes:           append([]string(nil), definition.RequiredAuth.Scopes...),
		IdempotencyKey:   execution.IdempotencyKey,
		ApprovalRef:      execution.ApprovalRef,
	}
}

func gatheringTarget(gatheringID string) runtimeauth.DelegatedResourceConstraint {
	return runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering",
		ID:   strings.TrimSpace(gatheringID),
	}
}

func gatheringPlanTarget(planID string) runtimeauth.DelegatedResourceConstraint {
	return runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering_plan",
		ID:   strings.TrimSpace(planID),
	}
}

// RejectAutomaticGatheringHostOperation is used by proposal dispatchers before
// they accept any future Gathering operation. The M5 executor itself exposes no
// methods for these owner-only actions.
func RejectAutomaticGatheringHostOperation(operationID string) error {
	operationID = strings.TrimSpace(operationID)
	if operationID == "circle.gathering.WatchGatheringAvailability" {
		return nil
	}
	if operationID == "circle.gathering_plan.ProposeGatheringPlan" {
		return nil
	}
	if strings.HasPrefix(operationID, "circle.gathering_plan.") {
		return ErrGatheringAutomaticAction
	}
	if strings.HasPrefix(operationID, "circle.gathering.") {
		return ErrGatheringAutomaticAction
	}
	return ErrGatheringBindingInvalid
}
