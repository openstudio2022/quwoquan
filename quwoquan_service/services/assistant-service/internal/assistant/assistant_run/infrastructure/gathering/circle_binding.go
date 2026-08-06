package gathering

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/generated/serviceclients"
	gatheringclient "quwoquan_service/generated/serviceclients/circlegathering"
	gatheringplanclient "quwoquan_service/generated/serviceclients/circlegatheringplan"
	runtimeauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tooling"
)

var ErrCircleGatheringGeneratedClientUnavailable = errors.New(
	"ASSISTANT.MIDDLEWARE.tool_unavailable: circle gathering operation unavailable",
)

// CircleGatheringUnavailableError preserves the canonical commercial block
// evidence without treating ContractGraph metadata as a readiness decision.
type CircleGatheringUnavailableError struct {
	OperationID     string
	CommercialState string
	BlockReason     string
	GapID           string
}

func (err CircleGatheringUnavailableError) Error() string {
	return fmt.Sprintf(
		"%s: operation=%s commercial=%s gap=%s reason=%s",
		ErrCircleGatheringGeneratedClientUnavailable,
		err.OperationID,
		err.CommercialState,
		err.GapID,
		err.BlockReason,
	)
}

func (err CircleGatheringUnavailableError) Unwrap() error {
	return ErrCircleGatheringGeneratedClientUnavailable
}

// CircleGatheringDelegatedGrantRequest is the typed handoff from the Assistant
// binding to the service-client composition. Endpoint selection, HTTP headers
// and HTTP execution stay behind CircleGatheringDelegatedGrantTransport.
type CircleGatheringDelegatedGrantRequest struct {
	Packet          gatheringclient.RequestPacket
	SerializedGrant string
	Claims          runtimeauth.DelegatedGrantClaims
}

// CircleGatheringDelegatedGrantTransport is supplied by production service
// client composition. The binding never builds a base URL or raw HTTP request.
type CircleGatheringDelegatedGrantTransport interface {
	Execute(
		context.Context,
		CircleGatheringDelegatedGrantRequest,
	) (gatheringclient.ResponsePacket, error)
}

type CircleGatheringPlanDelegatedGrantRequest struct {
	Packet          gatheringplanclient.RequestPacket
	SerializedGrant string
	Claims          runtimeauth.DelegatedGrantClaims
}

type CircleGatheringPlanDelegatedGrantTransport interface {
	ExecuteGatheringPlan(
		context.Context,
		CircleGatheringPlanDelegatedGrantRequest,
	) (gatheringplanclient.ResponsePacket, error)
}

// CircleGatheringCommercialProfile is an authority decision supplied to the
// adapter. Tests may explicitly override it; generated clients only expose
// metadata and never infer business readiness.
type CircleGatheringCommercialProfile interface {
	Allows(serviceclients.CircleGatheringOperationMetadata) bool
}

type canonicalCircleGatheringCommercialProfile struct{}

func (canonicalCircleGatheringCommercialProfile) Allows(
	operation serviceclients.CircleGatheringOperationMetadata,
) bool {
	return operation.CommercialStatus == "ready"
}

type CircleGatheringPlanCommercialProfile interface {
	AllowsPlan(serviceclients.CircleGatheringPlanOperationMetadata) bool
}

func (canonicalCircleGatheringCommercialProfile) AllowsPlan(
	operation serviceclients.CircleGatheringPlanOperationMetadata,
) bool {
	return operation.CommercialStatus == "ready"
}

type CircleGatheringBindingOption func(*CircleGatheringDomainOperationBinding)

func WithCircleGatheringDelegatedGrantTransport(
	transport CircleGatheringDelegatedGrantTransport,
) CircleGatheringBindingOption {
	return func(binding *CircleGatheringDomainOperationBinding) {
		binding.transport = transport
	}
}

func WithCircleGatheringPlanDelegatedGrantTransport(
	transport CircleGatheringPlanDelegatedGrantTransport,
) CircleGatheringBindingOption {
	return func(binding *CircleGatheringDomainOperationBinding) {
		binding.planTransport = transport
	}
}

func WithCircleGatheringCommercialProfile(
	profile CircleGatheringCommercialProfile,
) CircleGatheringBindingOption {
	return func(binding *CircleGatheringDomainOperationBinding) {
		if profile != nil {
			binding.commercial = profile
		}
	}
}

func WithCircleGatheringPlanCommercialProfile(
	profile CircleGatheringPlanCommercialProfile,
) CircleGatheringBindingOption {
	return func(binding *CircleGatheringDomainOperationBinding) {
		if profile != nil {
			binding.planCommercial = profile
		}
	}
}

// CircleGatheringDomainOperationBinding consumes only generated Circle
// operation metadata, typed DTO encoders and an injected delegated transport.
// Canonical blocked metadata is enforced before any transport call.
type CircleGatheringDomainOperationBinding struct {
	transport      CircleGatheringDelegatedGrantTransport
	planTransport  CircleGatheringPlanDelegatedGrantTransport
	commercial     CircleGatheringCommercialProfile
	planCommercial CircleGatheringPlanCommercialProfile
}

var _ tooling.GeneratedGatheringClient = (*CircleGatheringDomainOperationBinding)(nil)

func NewCircleGatheringDomainOperationBinding(
	options ...CircleGatheringBindingOption,
) *CircleGatheringDomainOperationBinding {
	binding := &CircleGatheringDomainOperationBinding{
		commercial:     canonicalCircleGatheringCommercialProfile{},
		planCommercial: canonicalCircleGatheringCommercialProfile{},
	}
	for _, option := range options {
		if option != nil {
			option(binding)
		}
	}
	return binding
}

func (*CircleGatheringDomainOperationBinding) OperationContractDigest(
	operationID string,
) string {
	operation, found := serviceclients.LookupCircleGatheringOperation(operationID)
	if !found {
		planOperation, planFound :=
			serviceclients.LookupCircleGatheringPlanOperation(operationID)
		if !planFound {
			return ""
		}
		return planOperation.ContractDigest
	}
	return operation.ContractDigest
}

func (binding *CircleGatheringDomainOperationBinding) SearchPublic(
	ctx context.Context,
	call tooling.VerifiedGatheringQueryCall,
	request tooling.GatheringSearchPublicRequest,
) (tooling.PublicGatheringPage, error) {
	packet, err := gatheringclient.EncodeListGatheringsBySource(
		gatheringclient.GatheringListBySourceQuery{
			SourceObjectTypeRef: request.SourceObjectTypeRef,
			SourceObjectID:      request.SourceObjectID,
			Cursor:              request.Cursor,
			Limit:               int64(request.Limit),
		},
	)
	if err != nil {
		return tooling.PublicGatheringPage{}, err
	}
	if err := binding.ensureAvailable(packet.Operation); err != nil {
		return tooling.PublicGatheringPage{}, err
	}
	target := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering.source",
		ID:   request.SourceObjectTypeRef + ":" + request.SourceObjectID,
	}
	if err := validateQueryCall(call, packet, target); err != nil {
		return tooling.PublicGatheringPage{}, err
	}
	responsePacket, err := binding.executeQuery(ctx, call, packet)
	if err != nil {
		return tooling.PublicGatheringPage{}, err
	}
	response, err := gatheringclient.DecodeListGatheringsBySourceResponse(
		responsePacket,
	)
	if err != nil {
		return tooling.PublicGatheringPage{}, err
	}
	result := tooling.PublicGatheringPage{
		Gatherings: make([]tooling.PublicGatheringCard, 0, len(response.Items)),
		NextCursor: response.NextCursor,
	}
	for _, card := range response.Items {
		result.Gatherings = append(result.Gatherings, publicCard(card))
	}
	return result, nil
}

func (binding *CircleGatheringDomainOperationBinding) ReadPublic(
	ctx context.Context,
	call tooling.VerifiedGatheringQueryCall,
	request tooling.GatheringIDQuery,
) (tooling.PublicGatheringDetail, error) {
	packet, err := gatheringclient.EncodeGetPublicGathering(
		gatheringclient.GatheringIDQuery{
			GatheringID: request.GatheringID,
		},
	)
	if err != nil {
		return tooling.PublicGatheringDetail{}, err
	}
	if err := binding.ensureAvailable(packet.Operation); err != nil {
		return tooling.PublicGatheringDetail{}, err
	}
	target := gatheringTarget(request.GatheringID)
	if err := validateQueryCall(call, packet, target); err != nil {
		return tooling.PublicGatheringDetail{}, err
	}
	responsePacket, err := binding.executeQuery(ctx, call, packet)
	if err != nil {
		return tooling.PublicGatheringDetail{}, err
	}
	response, err := gatheringclient.DecodeGetPublicGatheringResponse(
		responsePacket,
	)
	if err != nil {
		return tooling.PublicGatheringDetail{}, err
	}
	card := publicCard(response.Card)
	return tooling.PublicGatheringDetail{
		GatheringID:       card.GatheringID,
		Title:             card.Title,
		Summary:           card.Summary,
		StartAt:           card.StartAt,
		EndAt:             card.EndAt,
		MeetingPointLabel: card.MeetingPointLabel,
		RemainingCapacity: card.RemainingCapacity,
		AdmissionMode:     card.AdmissionMode,
		Status:            string(response.Card.LifecycleStatus),
	}, nil
}

func (binding *CircleGatheringDomainOperationBinding) ReadPrivate(
	ctx context.Context,
	call tooling.VerifiedGatheringQueryCall,
	request tooling.GatheringIDQuery,
) (tooling.PrivateGatheringDetail, error) {
	packet, err := gatheringclient.EncodeGetGathering(
		gatheringclient.GatheringIDQuery{
			GatheringID: request.GatheringID,
		},
	)
	if err != nil {
		return tooling.PrivateGatheringDetail{}, err
	}
	if err := binding.ensureAvailable(packet.Operation); err != nil {
		return tooling.PrivateGatheringDetail{}, err
	}
	target := gatheringTarget(request.GatheringID)
	if err := validateQueryCall(call, packet, target); err != nil {
		return tooling.PrivateGatheringDetail{}, err
	}
	responsePacket, err := binding.executeQuery(ctx, call, packet)
	if err != nil {
		return tooling.PrivateGatheringDetail{}, err
	}
	response, err := gatheringclient.DecodeGetGatheringResponse(responsePacket)
	if err != nil {
		return tooling.PrivateGatheringDetail{}, err
	}
	authority := tooling.GatheringViewerParticipation
	if response.CreatedByPersonaID == call.Grant.Claims.PersonaID ||
		(string(response.HostBinding.HostSubjectKind) == "persona" &&
			response.HostBinding.HostSubjectID == call.Grant.Claims.PersonaID) {
		authority = tooling.GatheringViewerHost
	}
	for _, organizer := range response.OrganizerAssignments {
		if organizer.PersonaID == call.Grant.Claims.PersonaID &&
			organizer.RevokedAt.IsZero() {
			authority = tooling.GatheringViewerHost
			break
		}
	}
	return tooling.PrivateGatheringDetail{
		GatheringID:         response.GatheringID,
		Title:               response.Purpose.Title,
		Purpose:             response.Purpose.Summary,
		StartAt:             wireTime(response.Schedule.StartAt),
		EndAt:               wireTime(response.Schedule.EndAt),
		ExactMeetingPoint:   response.Place.ExactMeetingPoint,
		Capacity:            int(response.Capacity.MaxParticipants),
		CurrentParticipants: int(response.Capacity.ActiveSeatCount),
		AdmissionMode:       string(response.PolicySet.AdmissionPolicy),
		Version:             response.AggregateVersion,
		ViewerAuthority:     authority,
	}, nil
}

func (binding *CircleGatheringDomainOperationBinding) WatchAvailability(
	ctx context.Context,
	call tooling.VerifiedGatheringCommandCall,
	request tooling.GatheringAvailabilityWatchCommand,
	idempotencyKey string,
) (tooling.GatheringCommandResult, error) {
	packet, err := gatheringclient.EncodeWatchGatheringAvailability(
		gatheringclient.GatheringAvailabilityWatchCommand{
			GatheringID:              request.GatheringID,
			ExpectedGatheringVersion: request.ExpectedGatheringVersion,
			ExpectedWatchVersion:     request.ExpectedWatchVersion,
		},
	)
	if err != nil {
		return tooling.GatheringCommandResult{}, err
	}
	if err := binding.ensureAvailable(packet.Operation); err != nil {
		return tooling.GatheringCommandResult{}, err
	}
	target := gatheringTarget(request.GatheringID)
	if err := validateCommandCall(
		call,
		packet,
		target,
		idempotencyKey,
	); err != nil {
		return tooling.GatheringCommandResult{}, err
	}
	if binding.transport == nil {
		return tooling.GatheringCommandResult{}, unavailable(packet.Operation)
	}
	responsePacket, err := binding.transport.Execute(
		ctx,
		CircleGatheringDelegatedGrantRequest{
			Packet:          packet,
			SerializedGrant: call.SerializedGrant,
			Claims:          call.Grant.Claims,
		},
	)
	if err != nil {
		return tooling.GatheringCommandResult{}, err
	}
	response, err := gatheringclient.DecodeWatchGatheringAvailabilityResponse(
		responsePacket,
	)
	if err != nil {
		return tooling.GatheringCommandResult{}, err
	}
	return tooling.GatheringCommandResult{
		GatheringID:                response.GatheringID,
		AggregateVersion:           response.AggregateVersion,
		LifecycleStatus:            string(response.LifecycleStatus),
		ParticipationState:         string(response.ParticipationState),
		ParticipationVersion:       response.ParticipationVersion,
		CurrentGatheringRevisionID: response.CurrentGatheringRevisionID,
		CurrentGatheringRevisionNo: int(response.CurrentGatheringRevisionNumber),
		OutcomeStatus:              string(response.OutcomeStatus),
		ConversationID:             response.ConversationID,
		RoomBindingStatus:          string(response.RoomBindingStatus),
		IdempotentReplay:           response.IdempotentReplay,
	}, nil
}

func (binding *CircleGatheringDomainOperationBinding) ProposeGatheringPlan(
	ctx context.Context,
	call tooling.VerifiedGatheringCommandCall,
	request gatheringplanclient.ProposeGatheringPlanCommand,
	idempotencyKey string,
) (gatheringplanclient.GatheringPlanCommandResult, error) {
	packet, err := gatheringplanclient.EncodeProposeGatheringPlan(request)
	if err != nil {
		return gatheringplanclient.GatheringPlanCommandResult{}, err
	}
	if binding.planCommercial == nil ||
		!binding.planCommercial.AllowsPlan(packet.Operation) {
		return gatheringplanclient.GatheringPlanCommandResult{},
			unavailablePlan(packet.Operation)
	}
	target := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering_plan",
		ID:   strings.TrimSpace(request.PlanID),
	}
	if err := validatePlanCommandCall(
		call,
		packet,
		target,
		idempotencyKey,
	); err != nil {
		return gatheringplanclient.GatheringPlanCommandResult{}, err
	}
	if binding.planTransport == nil {
		return gatheringplanclient.GatheringPlanCommandResult{},
			unavailablePlan(packet.Operation)
	}
	responsePacket, err := binding.planTransport.ExecuteGatheringPlan(
		ctx,
		CircleGatheringPlanDelegatedGrantRequest{
			Packet:          packet,
			SerializedGrant: call.SerializedGrant,
			Claims:          call.Grant.Claims,
		},
	)
	if err != nil {
		return gatheringplanclient.GatheringPlanCommandResult{}, err
	}
	return gatheringplanclient.DecodeProposeGatheringPlanResponse(responsePacket)
}

func (binding *CircleGatheringDomainOperationBinding) ensureAvailable(
	operation serviceclients.CircleGatheringOperationMetadata,
) error {
	if binding.commercial == nil || !binding.commercial.Allows(operation) {
		return unavailable(operation)
	}
	return nil
}

func unavailable(
	operation serviceclients.CircleGatheringOperationMetadata,
) error {
	return CircleGatheringUnavailableError{
		OperationID:     operation.OperationID,
		CommercialState: operation.CommercialStatus,
		BlockReason:     operation.CommercialReason,
		GapID:           operation.CommercialGapID,
	}
}

func unavailablePlan(
	operation serviceclients.CircleGatheringPlanOperationMetadata,
) error {
	return CircleGatheringUnavailableError{
		OperationID:     operation.OperationID,
		CommercialState: operation.CommercialStatus,
		BlockReason:     operation.CommercialReason,
		GapID:           operation.CommercialGapID,
	}
}

func (binding *CircleGatheringDomainOperationBinding) executeQuery(
	ctx context.Context,
	call tooling.VerifiedGatheringQueryCall,
	packet gatheringclient.RequestPacket,
) (gatheringclient.ResponsePacket, error) {
	if binding.transport == nil {
		return gatheringclient.ResponsePacket{}, unavailable(packet.Operation)
	}
	return binding.transport.Execute(
		ctx,
		CircleGatheringDelegatedGrantRequest{
			Packet:          packet,
			SerializedGrant: call.SerializedGrant,
			Claims:          call.Grant.Claims,
		},
	)
}

func validateQueryCall(
	call tooling.VerifiedGatheringQueryCall,
	packet gatheringclient.RequestPacket,
	target runtimeauth.DelegatedResourceConstraint,
) error {
	if call.Grant.Claims.GrantType != runtimeauth.DelegatedGrantTypeQuery {
		return tooling.ErrGatheringBindingInvalid
	}
	return validateCall(
		call.Binding,
		call.Grant.Claims,
		call.SerializedGrant,
		packet,
		target,
	)
}

func validateCommandCall(
	call tooling.VerifiedGatheringCommandCall,
	packet gatheringclient.RequestPacket,
	target runtimeauth.DelegatedResourceConstraint,
	idempotencyKey string,
) error {
	if call.Grant.Claims.GrantType != runtimeauth.DelegatedGrantTypeCommand ||
		strings.TrimSpace(idempotencyKey) == "" ||
		call.Grant.Claims.IdempotencyKey != strings.TrimSpace(idempotencyKey) ||
		strings.TrimSpace(call.Grant.Claims.ApprovalRef) == "" {
		return tooling.ErrGatheringBindingInvalid
	}
	return validateCall(
		call.Binding,
		call.Grant.Claims,
		call.SerializedGrant,
		packet,
		target,
	)
}

func validatePlanCommandCall(
	call tooling.VerifiedGatheringCommandCall,
	packet gatheringplanclient.RequestPacket,
	target runtimeauth.DelegatedResourceConstraint,
	idempotencyKey string,
) error {
	if call.Grant.Claims.GrantType != runtimeauth.DelegatedGrantTypeCommand ||
		strings.TrimSpace(idempotencyKey) == "" ||
		call.Grant.Claims.IdempotencyKey != strings.TrimSpace(idempotencyKey) ||
		strings.TrimSpace(call.Grant.Claims.ApprovalRef) == "" {
		return tooling.ErrGatheringBindingInvalid
	}
	requestDigest := gatheringplanclient.CanonicalRequestDigest(
		packet.CanonicalRequest,
	)
	if strings.TrimSpace(call.SerializedGrant) == "" ||
		call.Binding.OwnerService != gatheringOwnerService ||
		call.Binding.OperationID != packet.Operation.OperationID ||
		call.Binding.ContractDigest != packet.Operation.ContractDigest ||
		call.Binding.RequestDigest != requestDigest ||
		call.Binding.Target != target ||
		call.Grant.Claims.Audience != tooling.GatheringDelegateAudience ||
		call.Grant.Claims.DelegateService != tooling.GatheringDelegateService ||
		call.Grant.Claims.OperationID != packet.Operation.OperationID ||
		call.Grant.Claims.RequestDigest != requestDigest ||
		call.Grant.Claims.Resource != target ||
		strings.TrimSpace(call.Grant.Claims.AccountID) == "" ||
		strings.TrimSpace(call.Grant.Claims.PersonaID) == "" ||
		strings.TrimSpace(call.Grant.Claims.RunID) == "" ||
		strings.TrimSpace(call.Grant.Claims.ToolInvocationID) == "" {
		return tooling.ErrGatheringBindingInvalid
	}
	return nil
}

func validateCall(
	operationBinding tooling.DomainOperationBinding,
	claims runtimeauth.DelegatedGrantClaims,
	serializedGrant string,
	packet gatheringclient.RequestPacket,
	target runtimeauth.DelegatedResourceConstraint,
) error {
	requestDigest := gatheringclient.CanonicalRequestDigest(
		packet.CanonicalRequest,
	)
	if strings.TrimSpace(serializedGrant) == "" ||
		operationBinding.OwnerService != gatheringOwnerService ||
		operationBinding.OperationID != packet.Operation.OperationID ||
		operationBinding.ContractDigest != packet.Operation.ContractDigest ||
		operationBinding.RequestDigest != requestDigest ||
		operationBinding.Target != target ||
		claims.Audience != tooling.GatheringDelegateAudience ||
		claims.DelegateService != tooling.GatheringDelegateService ||
		claims.OperationID != packet.Operation.OperationID ||
		claims.RequestDigest != requestDigest ||
		claims.Resource != target ||
		strings.TrimSpace(claims.AccountID) == "" ||
		strings.TrimSpace(claims.PersonaID) == "" ||
		strings.TrimSpace(claims.RunID) == "" ||
		strings.TrimSpace(claims.ToolInvocationID) == "" {
		return tooling.ErrGatheringBindingInvalid
	}
	return nil
}

func publicCard(
	card gatheringclient.GatheringPublicCardSlice,
) tooling.PublicGatheringCard {
	meetingPoint := strings.TrimSpace(card.Place.ExactMeetingPoint)
	if meetingPoint == "" {
		meetingPoint = card.Place.CoarsePlaceLabel
	}
	return tooling.PublicGatheringCard{
		GatheringID:       card.GatheringID,
		Title:             card.Purpose.Title,
		Summary:           card.Purpose.Summary,
		StartAt:           wireTime(card.Schedule.StartAt),
		EndAt:             wireTime(card.Schedule.EndAt),
		MeetingPointLabel: meetingPoint,
		RemainingCapacity: int(card.Capacity.RemainingSeats),
		AdmissionMode:     string(card.Admission.AdmissionState),
	}
}

func wireTime(value time.Time) string {
	if value.IsZero() {
		return ""
	}
	return value.UTC().Format(time.RFC3339Nano)
}

func gatheringTarget(
	gatheringID string,
) runtimeauth.DelegatedResourceConstraint {
	return runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering",
		ID:   strings.TrimSpace(gatheringID),
	}
}

const gatheringOwnerService = "circle-service"
