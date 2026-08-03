package toolaccess

import (
	"context"
	"errors"
	"sort"
	"strings"

	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	consentports "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
	settingmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
	settingports "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/ports"
)

const (
	ConnectorNone     = "none"
	ConnectorOptional = "optional"
	ConnectorRequired = "required"

	SurfacePersonal     = "personal"
	SurfaceConversation = "conversation"
	SurfaceCircle       = "circle"
)

var (
	ErrInvalidPolicy      = errors.New("assistant tool capability policy is invalid")
	ErrSurfaceDenied      = errors.New("assistant tool capability is denied on this surface")
	ErrConsentRequired    = errors.New("assistant tool capability consent is required")
	ErrConnectorRequired  = errors.New("assistant tool connector capability is required")
	ErrGatewayUnavailable = errors.New("assistant connector gateway is unavailable")
)

type Requirement struct {
	CapabilityKey        string
	ConnectorRequirement string
	ConsentScopes        []string
	AllowedSurfaceKinds  []string
	RecheckAtExecution   bool
}

type Request struct {
	AccountID   string
	SkillID     string
	SurfaceKind string
	Requirement Requirement
}

type ConnectorGrantRequest struct {
	AccountID      string
	CapabilityKey  string
	SurfaceKind    string
	ConnectionRefs []string
}

type ConnectorGrantDecision struct {
	Allowed      bool
	ConnectionID string
	ConnectorID  string
	Reason       string
}

type Decision struct {
	Allowed       bool
	CapabilityKey string
	SurfaceKind   string
	ConnectionID  string
	ConnectorID   string
	Reason        string
}

type ConnectorGateway interface {
	ResolveCapability(context.Context, ConnectorGrantRequest) (ConnectorGrantDecision, error)
}

type Policy struct {
	settings   settingports.Reader
	consents   consentports.Reader
	connectors ConnectorGateway
}

func NewPolicy(
	settings settingports.Reader,
	consents consentports.Reader,
	connectors ConnectorGateway,
) *Policy {
	return &Policy{settings: settings, consents: consents, connectors: connectors}
}

func (policy *Policy) Authorize(
	ctx context.Context,
	request Request,
) (Decision, error) {
	accountID := strings.TrimSpace(request.AccountID)
	skillID := strings.TrimSpace(request.SkillID)
	requirement, err := normalizeRequirement(request.Requirement)
	if err != nil || accountID == "" || skillID == "" {
		return Decision{}, ErrInvalidPolicy
	}
	surfaceKind := strings.TrimSpace(request.SurfaceKind)
	if surfaceKind == "" {
		surfaceKind = SurfacePersonal
	}
	decision := Decision{
		CapabilityKey: requirement.CapabilityKey,
		SurfaceKind:   surfaceKind,
	}
	if !contains(requirement.AllowedSurfaceKinds, surfaceKind) {
		decision.Reason = "surface_denied"
		return decision, ErrSurfaceDenied
	}
	// SkillUserSetting connector refs are personal facts. Shared surfaces need a
	// future surface-owned grant source; they must never fall back to a member's
	// personal connection even if a package mistakenly declares the surface.
	if surfaceKind != SurfacePersonal &&
		requirement.ConnectorRequirement != ConnectorNone {
		decision.Reason = "personal_connector_forbidden_on_shared_surface"
		return decision, ErrSurfaceDenied
	}
	if len(requirement.ConsentScopes) > 0 {
		if policy == nil || policy.consents == nil {
			return decision, ErrGatewayUnavailable
		}
		consents, consentErr := policy.consents.ListActiveConsents(ctx, accountID)
		if consentErr != nil {
			return decision, ErrGatewayUnavailable
		}
		if !grantsAllScopes(consents, skillID, requirement.ConsentScopes) {
			decision.Reason = "consent_required"
			return decision, ErrConsentRequired
		}
	}
	if requirement.ConnectorRequirement == ConnectorNone {
		decision.Allowed = true
		decision.Reason = "allowed_without_connector"
		return decision, nil
	}
	if policy == nil || policy.settings == nil {
		return decision, ErrGatewayUnavailable
	}
	setting, settingErr := policy.settings.Get(ctx, accountID, skillID)
	connectionRefs := []string{}
	if settingErr == nil {
		if setting.Status != settingmodel.StatusEnabled {
			decision.Reason = "skill_disabled"
			return decision, ErrConnectorRequired
		}
		connectionRefs = normalizeStrings(setting.ConnectorConnectionRefs)
	} else if !errors.Is(settingErr, settingmodel.ErrNotFound) {
		return decision, ErrGatewayUnavailable
	}
	if len(connectionRefs) == 0 {
		if requirement.ConnectorRequirement == ConnectorOptional {
			decision.Allowed = true
			decision.Reason = "optional_connector_absent"
			return decision, nil
		}
		decision.Reason = "connector_required"
		return decision, ErrConnectorRequired
	}
	if policy.connectors == nil {
		return decision, ErrGatewayUnavailable
	}
	grant, grantErr := policy.connectors.ResolveCapability(ctx, ConnectorGrantRequest{
		AccountID:      accountID,
		CapabilityKey:  requirement.CapabilityKey,
		SurfaceKind:    surfaceKind,
		ConnectionRefs: connectionRefs,
	})
	if grantErr != nil {
		return decision, ErrGatewayUnavailable
	}
	decision.Allowed = grant.Allowed
	decision.ConnectionID = strings.TrimSpace(grant.ConnectionID)
	decision.ConnectorID = strings.TrimSpace(grant.ConnectorID)
	decision.Reason = strings.TrimSpace(grant.Reason)
	if !grant.Allowed {
		if decision.Reason == "" {
			decision.Reason = "connector_required"
		}
		return decision, ErrConnectorRequired
	}
	if decision.ConnectionID == "" || decision.ConnectorID == "" {
		return Decision{}, ErrGatewayUnavailable
	}
	return decision, nil
}

func normalizeRequirement(input Requirement) (Requirement, error) {
	input.CapabilityKey = strings.TrimSpace(input.CapabilityKey)
	input.ConnectorRequirement = strings.TrimSpace(input.ConnectorRequirement)
	input.ConsentScopes = normalizeStrings(input.ConsentScopes)
	input.AllowedSurfaceKinds = normalizeStrings(input.AllowedSurfaceKinds)
	if input.CapabilityKey == "" || !input.RecheckAtExecution ||
		!oneOf(input.ConnectorRequirement, ConnectorNone, ConnectorOptional, ConnectorRequired) ||
		len(input.AllowedSurfaceKinds) == 0 {
		return Requirement{}, ErrInvalidPolicy
	}
	return input, nil
}

func grantsAllScopes(
	consents []consentmodel.Consent,
	skillID string,
	required []string,
) bool {
	granted := map[string]struct{}{}
	for _, consent := range consents {
		if !consent.IsGranted() || strings.TrimSpace(consent.SkillID) != skillID {
			continue
		}
		for _, scope := range consent.GrantedScopes {
			granted[strings.TrimSpace(scope)] = struct{}{}
		}
	}
	for _, scope := range required {
		if _, exists := granted[scope]; !exists {
			return false
		}
	}
	return true
}

func normalizeStrings(values []string) []string {
	result := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" {
			continue
		}
		if _, duplicate := seen[value]; duplicate {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func contains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func oneOf(value string, allowed ...string) bool {
	for _, candidate := range allowed {
		if value == candidate {
			return true
		}
	}
	return false
}
