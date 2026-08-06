package tooling

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	runtimeauth "quwoquan_service/runtime/auth"
)

const (
	GatheringSearchPublicTool       = "gathering.search_public"
	GatheringReadPublicTool         = "gathering.read_public"
	GatheringReadPrivateTool        = "gathering.read_private"
	GatheringProposeCreateDraftTool = "gathering.propose_create_draft"
	GatheringProposeUpdateTool      = "gathering.propose_update"
	GatheringProposePlanTool        = "gathering.propose_plan"
	GatheringWatchAvailabilityTool  = "gathering.watch_availability"
	GatheringDelegateAudience       = "circle-service"
	GatheringDelegateService        = "assistant-service"
	GatheringConversationSurface    = "conversation"
	GatheringPrivateRedactionPolicy = "private_detail_without_roster_or_answers"
)

var (
	ErrGatheringBindingInvalid   = errors.New("ASSISTANT.USER.delegated_approval_invalid")
	ErrGatheringHostUnauthorized = errors.New("ASSISTANT.USER.run_unauthorized")
	ErrGatheringToolUnavailable  = errors.New("ASSISTANT.MIDDLEWARE.tool_unavailable")
	ErrGatheringAutomaticAction  = errors.New("ASSISTANT.USER.run_invalid_argument")
	ErrGatheringProviderDegraded = errors.New("ASSISTANT.MIDDLEWARE.tool_unavailable: optional provider degraded")
)

var gatheringToolClosedSet = []string{
	GatheringSearchPublicTool,
	GatheringReadPublicTool,
	GatheringReadPrivateTool,
	GatheringProposeCreateDraftTool,
	GatheringProposeUpdateTool,
	GatheringProposePlanTool,
	GatheringWatchAvailabilityTool,
}

func GatheringToolNames() []string {
	return append([]string(nil), gatheringToolClosedSet...)
}

type GatheringRequiredAuth struct {
	GrantKind        string   `json:"grantKind" yaml:"grantKind"`
	Scopes           []string `json:"scopes" yaml:"scopes"`
	ResourceType     string   `json:"resourceType" yaml:"resourceType"`
	ResourceIDSource string   `json:"resourceIdSource" yaml:"resourceIdSource"`
	ViewerAuthority  []string `json:"viewerAuthority" yaml:"viewerAuthority"`
}

type GatheringApprovalPolicy struct {
	Mode                                 string `json:"mode" yaml:"mode"`
	UserConfirmationRequiredBeforeEffect bool   `json:"userConfirmationRequiredBeforeEffect" yaml:"userConfirmationRequiredBeforeEffect"`
}

type GatheringRedactionPolicy struct {
	Policy        string   `json:"policy" yaml:"policy"`
	OmittedFields []string `json:"omittedFields" yaml:"omittedFields"`
}

type GatheringAuditPolicy struct {
	EventName            string   `json:"eventName" yaml:"eventName"`
	IncludeRequestDigest bool     `json:"includeRequestDigest" yaml:"includeRequestDigest"`
	IncludeGrantJTI      bool     `json:"includeGrantJti" yaml:"includeGrantJti"`
	NeverLog             []string `json:"neverLog" yaml:"neverLog"`
}

type GatheringExecutionPolicy struct {
	Mode                 string   `json:"mode" yaml:"mode"`
	ProhibitedOperations []string `json:"prohibitedOperations" yaml:"prohibitedOperations"`
}

// GatheringToolDefinition is the typed projection of the gathering-specific
// catalog policy. The canonical YAML remains the only metadata source; this
// projection exists so execution does not inspect untyped maps.
type GatheringToolDefinition struct {
	ToolName            string                   `json:"toolName" yaml:"toolName"`
	ReadOnly            bool                     `json:"readOnly" yaml:"readOnly"`
	RiskTier            string                   `json:"riskTier" yaml:"riskTier"`
	OwnerService        string                   `json:"ownerService" yaml:"ownerService"`
	OwnerOperationID    string                   `json:"ownerOperationId" yaml:"ownerOperationId"`
	OwnerRequestEntity  string                   `json:"ownerRequestEntity" yaml:"ownerRequestEntity"`
	OwnerResponseEntity string                   `json:"ownerResponseEntity" yaml:"ownerResponseEntity"`
	ContractDigest      string                   `json:"contractDigest" yaml:"contractDigest"`
	RequiredAuth        GatheringRequiredAuth    `json:"requiredAuth" yaml:"requiredAuth"`
	RequiredCapability  string                   `json:"requiredCapability" yaml:"requiredCapability"`
	ApprovalPolicy      GatheringApprovalPolicy  `json:"approvalPolicy" yaml:"approvalPolicy"`
	Idempotency         string                   `json:"idempotency" yaml:"idempotency"`
	Redaction           GatheringRedactionPolicy `json:"redaction" yaml:"redaction"`
	Audit               GatheringAuditPolicy     `json:"audit" yaml:"audit"`
	ExecutionPolicy     GatheringExecutionPolicy `json:"executionPolicy" yaml:"executionPolicy"`
}

type GatheringBindingCatalog struct {
	definitions map[string]GatheringToolDefinition
}

// ParseGatheringBindingCatalog consumes generated catalog JSON. It deliberately
// requires the exact seven-tool closed set and rejects any gathering tool whose
// authority, owner binding, digest, approval, redaction or audit policy is
// incomplete.
func ParseGatheringBindingCatalog(raw []byte) (GatheringBindingCatalog, error) {
	var all []GatheringToolDefinition
	if err := json.Unmarshal(raw, &all); err != nil {
		return GatheringBindingCatalog{}, fmt.Errorf("%w: decode catalog: %v", ErrGatheringBindingInvalid, err)
	}
	definitions := make(map[string]GatheringToolDefinition, len(gatheringToolClosedSet))
	for _, definition := range all {
		if !strings.HasPrefix(definition.ToolName, "gathering.") {
			continue
		}
		if _, duplicate := definitions[definition.ToolName]; duplicate {
			return GatheringBindingCatalog{}, fmt.Errorf(
				"%w: duplicate tool %s",
				ErrGatheringBindingInvalid,
				definition.ToolName,
			)
		}
		if err := validateGatheringToolDefinition(definition); err != nil {
			return GatheringBindingCatalog{}, err
		}
		definitions[definition.ToolName] = definition
	}
	if len(definitions) != len(gatheringToolClosedSet) {
		return GatheringBindingCatalog{}, fmt.Errorf(
			"%w: gathering tool set has %d definitions, want %d",
			ErrGatheringBindingInvalid,
			len(definitions),
			len(gatheringToolClosedSet),
		)
	}
	for _, toolName := range gatheringToolClosedSet {
		if _, found := definitions[toolName]; !found {
			return GatheringBindingCatalog{}, fmt.Errorf(
				"%w: missing tool %s",
				ErrGatheringBindingInvalid,
				toolName,
			)
		}
	}
	return GatheringBindingCatalog{definitions: definitions}, nil
}

func (c GatheringBindingCatalog) Definition(toolName string) (GatheringToolDefinition, bool) {
	definition, found := c.definitions[toolName]
	if !found {
		return GatheringToolDefinition{}, false
	}
	definition.RequiredAuth.Scopes = append([]string(nil), definition.RequiredAuth.Scopes...)
	definition.RequiredAuth.ViewerAuthority = append(
		[]string(nil),
		definition.RequiredAuth.ViewerAuthority...,
	)
	definition.Redaction.OmittedFields = append(
		[]string(nil),
		definition.Redaction.OmittedFields...,
	)
	definition.Audit.NeverLog = append([]string(nil), definition.Audit.NeverLog...)
	definition.ExecutionPolicy.ProhibitedOperations = append(
		[]string(nil),
		definition.ExecutionPolicy.ProhibitedOperations...,
	)
	return definition, true
}

func validateGatheringToolDefinition(definition GatheringToolDefinition) error {
	if !containsGatheringTool(definition.ToolName) ||
		strings.TrimSpace(definition.RiskTier) == "" ||
		strings.TrimSpace(definition.OwnerService) == "" ||
		strings.TrimSpace(definition.OwnerOperationID) == "" ||
		strings.TrimSpace(definition.OwnerRequestEntity) == "" ||
		strings.TrimSpace(definition.OwnerResponseEntity) == "" ||
		strings.TrimSpace(definition.RequiredAuth.GrantKind) == "" ||
		len(definition.RequiredAuth.Scopes) == 0 ||
		strings.TrimSpace(definition.RequiredAuth.ResourceType) == "" ||
		strings.TrimSpace(definition.RequiredAuth.ResourceIDSource) == "" ||
		strings.TrimSpace(definition.RequiredCapability) == "" ||
		strings.TrimSpace(definition.ApprovalPolicy.Mode) == "" ||
		strings.TrimSpace(definition.Idempotency) == "" ||
		strings.TrimSpace(definition.Redaction.Policy) == "" ||
		strings.TrimSpace(definition.Audit.EventName) == "" ||
		!definition.Audit.IncludeRequestDigest {
		return fmt.Errorf(
			"%w: incomplete policy for %s",
			ErrGatheringBindingInvalid,
			definition.ToolName,
		)
	}
	if err := validateSHA256Digest(definition.ContractDigest); err != nil {
		return fmt.Errorf(
			"%w: tool %s contract digest: %v",
			ErrGatheringBindingInvalid,
			definition.ToolName,
			err,
		)
	}
	if definition.ContractDigest != gatheringOperationContractDigest(definition) {
		return fmt.Errorf(
			"%w: tool %s contract digest does not bind owner operation entities",
			ErrGatheringBindingInvalid,
			definition.ToolName,
		)
	}
	isProposal := strings.HasPrefix(definition.ToolName, "gathering.propose_") ||
		definition.ToolName == GatheringWatchAvailabilityTool
	if isProposal && !definition.ApprovalPolicy.UserConfirmationRequiredBeforeEffect {
		return fmt.Errorf(
			"%w: tool %s permits effect without confirmation",
			ErrGatheringBindingInvalid,
			definition.ToolName,
		)
	}
	if isProposal &&
		definition.RequiredAuth.GrantKind !=
			"delegated_command_after_approval" {
		return fmt.Errorf(
			"%w: tool %s must mint a command grant only after approval",
			ErrGatheringBindingInvalid,
			definition.ToolName,
		)
	}
	if isGatheringQueryTool(definition.ToolName) &&
		definition.RequiredAuth.GrantKind != "delegated_query" {
		return fmt.Errorf(
			"%w: tool %s must use DelegatedQueryGrant",
			ErrGatheringBindingInvalid,
			definition.ToolName,
		)
	}
	if definition.OwnerService != "circle-service" ||
		!isCanonicalGatheringOperation(definition) {
		return fmt.Errorf(
			"%w: tool %s is not bound to Circle canonical operation",
			ErrGatheringBindingInvalid,
			definition.ToolName,
		)
	}
	return nil
}

func isCanonicalGatheringOperation(definition GatheringToolDefinition) bool {
	if definition.ToolName == GatheringProposePlanTool {
		return definition.OwnerOperationID ==
			"circle.gathering_plan.ProposeGatheringPlan"
	}
	return strings.HasPrefix(definition.OwnerOperationID, "circle.gathering.")
}

func isGatheringQueryTool(toolName string) bool {
	switch toolName {
	case GatheringSearchPublicTool,
		GatheringReadPublicTool,
		GatheringReadPrivateTool:
		return true
	default:
		return false
	}
}

// gatheringOperationContractDigest is the stable M5 binding identity carried by
// DomainOperationBinding. The dynamic command/query body has a separate
// CanonicalGatheringRequestDigest and both are checked before execution.
func gatheringOperationContractDigest(
	definition GatheringToolDefinition,
) string {
	identity := strings.Join([]string{
		strings.TrimSpace(definition.OwnerService),
		strings.TrimSpace(definition.OwnerOperationID),
		strings.TrimSpace(definition.OwnerRequestEntity),
		strings.TrimSpace(definition.OwnerResponseEntity),
	}, "|")
	digest := sha256.Sum256([]byte(identity))
	return "sha256:" + hex.EncodeToString(digest[:])
}

func containsGatheringTool(toolName string) bool {
	for _, candidate := range gatheringToolClosedSet {
		if candidate == toolName {
			return true
		}
	}
	return false
}

type DomainOperationBinding struct {
	OwnerService   string                                  `json:"ownerService"`
	OperationID    string                                  `json:"operationId"`
	ContractDigest string                                  `json:"contractDigest"`
	RequestDigest  string                                  `json:"requestDigest"`
	Target         runtimeauth.DelegatedResourceConstraint `json:"target"`
}

func NewDomainOperationBinding(
	definition GatheringToolDefinition,
	requestDigest string,
	target runtimeauth.DelegatedResourceConstraint,
) (DomainOperationBinding, error) {
	binding := DomainOperationBinding{
		OwnerService:   definition.OwnerService,
		OperationID:    definition.OwnerOperationID,
		ContractDigest: definition.ContractDigest,
		RequestDigest:  requestDigest,
		Target:         target,
	}
	if err := binding.ValidateAgainst(definition, requestDigest, target); err != nil {
		return DomainOperationBinding{}, err
	}
	return binding, nil
}

func (b DomainOperationBinding) ValidateAgainst(
	definition GatheringToolDefinition,
	requestDigest string,
	target runtimeauth.DelegatedResourceConstraint,
) error {
	if b.OwnerService != definition.OwnerService ||
		b.OperationID != definition.OwnerOperationID ||
		b.ContractDigest != definition.ContractDigest ||
		b.RequestDigest != requestDigest ||
		b.Target != target {
		return ErrGatheringBindingInvalid
	}
	if definition.OwnerService != "circle-service" ||
		!isCanonicalGatheringOperation(definition) {
		return ErrGatheringBindingInvalid
	}
	if err := validateSHA256Digest(b.ContractDigest); err != nil {
		return fmt.Errorf("%w: %v", ErrGatheringBindingInvalid, err)
	}
	if err := validateSHA256Digest(b.RequestDigest); err != nil {
		return fmt.Errorf("%w: %v", ErrGatheringBindingInvalid, err)
	}
	if strings.TrimSpace(b.Target.Type) == "" || strings.TrimSpace(b.Target.ID) == "" {
		return ErrGatheringBindingInvalid
	}
	return nil
}

func CanonicalGatheringRequestDigest(request any) (string, error) {
	encoded, err := json.Marshal(request)
	if err != nil {
		return "", fmt.Errorf("%w: encode request: %v", ErrGatheringBindingInvalid, err)
	}
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func validateSHA256Digest(value string) error {
	const prefix = "sha256:"
	if !strings.HasPrefix(value, prefix) {
		return errors.New("digest must use sha256")
	}
	decoded, err := hex.DecodeString(strings.TrimPrefix(value, prefix))
	if err != nil || len(decoded) != sha256.Size {
		return errors.New("digest must contain 32 bytes")
	}
	return nil
}
