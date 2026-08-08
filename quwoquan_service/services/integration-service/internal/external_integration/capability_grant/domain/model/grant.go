package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"
)

type BindingKind string

const (
	BindingPublicProvider  BindingKind = "public_provider"
	BindingUserConnector   BindingKind = "user_connector"
	BindingDevice          BindingKind = "device_capability"
	BindingDomainOperation BindingKind = "domain_operation"
)

const GrantTTL = 5 * time.Minute

type ProviderBindingState string

const (
	ProviderBindingReady       ProviderBindingState = "ready"
	ProviderBindingDisabled    ProviderBindingState = "disabled"
	ProviderBindingUnavailable ProviderBindingState = "unavailable"
)

type ProviderProbeState string

const (
	ProviderProbePassed ProviderProbeState = "passed"
	ProviderProbeFailed ProviderProbeState = "failed"
	ProviderProbeNotRun ProviderProbeState = "not_run"
)

type ConnectorGrantState string

const (
	ConnectorGrantActive  ConnectorGrantState = "active"
	ConnectorGrantRevoked ConnectorGrantState = "revoked"
	ConnectorGrantExpired ConnectorGrantState = "expired"
)

type DeviceAvailability string

const (
	DeviceAvailable   DeviceAvailability = "available"
	DeviceUnavailable DeviceAvailability = "unavailable"
)

type DevicePermission string

const (
	DevicePermissionGranted DevicePermission = "granted"
	DevicePermissionDenied  DevicePermission = "denied"
)

var (
	ErrInvalidRequirement      = errors.New("capability grant requirement is invalid")
	ErrConfirmationRequired    = errors.New("capability write confirmation is required")
	ErrPermitRequired          = errors.New("capability write permit is required")
	ErrIdempotencyRequired     = errors.New("capability write idempotency key is required")
	ErrProviderUnavailable     = errors.New("public capability provider is unavailable")
	ErrConnectorRevoked        = errors.New("user connector authorization is revoked")
	ErrConnectorExpired        = errors.New("user connector authorization is expired")
	ErrConnectorCapability     = errors.New("user connector capability is not granted")
	ErrConnectorSurfaceDenied  = errors.New("user connector surface is not allowed")
	ErrDeviceUnavailable       = errors.New("device capability is unavailable")
	ErrDevicePermissionDenied  = errors.New("device capability permission is denied")
	ErrDomainOperationInvalid  = errors.New("domain operation binding is invalid")
	ErrCapabilityGrantRequired = errors.New("no capability binding can grant the requirement")
	ErrAmbiguousBinding        = errors.New("capability binding candidates are ambiguous")
	ErrInvalidResolvedGrant    = errors.New("resolved capability grant is invalid")
)

// Requirement is assembled by the capability owner. BindingPriority is ordered
// and fail-closed: once a kind has an authoritative candidate, a denied,
// revoked or unavailable candidate must not fall through to a lower-priority
// kind.
type Requirement struct {
	ResolutionID       string
	AccountID          string
	ServiceActorDigest string
	CapabilityKey      string
	RegionCode         string
	SurfaceKind        string
	ConnectionRefs     []string
	BindingPriority    []BindingKind
	Write              bool
	ConfirmationRef    string
	PermitRef          string
	IdempotencyKey     string
	InputDigest        string
}

// PublicProviderBinding is environment-owned runtime material. It intentionally
// has no account, authorization, connection or credential lifecycle.
type PublicProviderBinding struct {
	CapabilityKey        string
	SupportedRegionCodes []string
	AdapterID            string
	ContractDigest       string
	ConfigRef            string
	TimeoutMs            int
	RatePolicyRef        string
	State                ProviderBindingState
	ProbeState           ProviderProbeState
}

// UserConnectorConnection is a redacted authorization view read from
// Integration-owned Connection state. Credential references never enter the
// capability resolver.
type UserConnectorConnection struct {
	CapabilityKey                string
	AccountID                    string
	ConnectionID                 string
	ConnectorID                  string
	ContractDigest               string
	GrantedCapabilities          []string
	GrantState                   ConnectorGrantState
	ProviderAccountSubjectDigest string
	FreshnessAt                  time.Time
	ExpiresAt                    *time.Time
	Revision                     int64
}

// DeviceCapabilityBinding is attested for the current installation and bridge
// capability only. It never implies cloud OAuth availability on another
// device.
type DeviceCapabilityBinding struct {
	CapabilityKey     string
	BridgeCapability  string
	Availability      DeviceAvailability
	Permission        DevicePermission
	AttestationDigest string
}

// DomainOperationBinding contains only the owner operation and its current
// contract digest. Provider, connector and device material is forbidden here.
type DomainOperationBinding struct {
	OwnerOperationID string
	ContractDigest   string
}

type Candidates struct {
	PublicProviders  []PublicProviderBinding
	UserConnectors   []UserConnectorConnection
	DeviceBindings   []DeviceCapabilityBinding
	DomainOperations []DomainOperationBinding
}

// ResolvedCapabilityGrant is a short-lived tagged result, not a shared
// Connector aggregate. Exactly one typed binding pointer is non-nil.
type ResolvedCapabilityGrant struct {
	ResolutionID         string
	AccountID            string
	ServiceActorDigest   string
	CapabilityKey        string
	SurfaceKind          string
	BindingKind          BindingKind
	PublicProvider       *PublicProviderBinding
	UserConnector        *UserConnectorConnection
	DeviceBinding        *DeviceCapabilityBinding
	DomainOperation      *DomainOperationBinding
	RequiresConfirmation bool
	RequiresPermit       bool
	RequiresIdempotency  bool
	InputDigest          string
	ConfirmationDigest   string
	PermitDigest         string
	IdempotencyDigest    string
	ResolvedAt           time.Time
	ExpiresAt            *time.Time
}

func ResolveCapabilityGrant(
	requirement Requirement,
	candidates Candidates,
	now time.Time,
) (ResolvedCapabilityGrant, error) {
	normalized, err := NormalizeRequirement(requirement, now)
	if err != nil {
		return ResolvedCapabilityGrant{}, err
	}
	if normalized.Write {
		switch {
		case strings.TrimSpace(normalized.ConfirmationRef) == "":
			return ResolvedCapabilityGrant{}, ErrConfirmationRequired
		case strings.TrimSpace(normalized.PermitRef) == "":
			return ResolvedCapabilityGrant{}, ErrPermitRequired
		case strings.TrimSpace(normalized.IdempotencyKey) == "":
			return ResolvedCapabilityGrant{}, ErrIdempotencyRequired
		}
	}
	for _, kind := range normalized.BindingPriority {
		switch kind {
		case BindingPublicProvider:
			binding, found, resolveErr := resolvePublicProvider(normalized, candidates.PublicProviders)
			if !found {
				continue
			}
			if resolveErr != nil {
				return ResolvedCapabilityGrant{}, resolveErr
			}
			return newGrant(normalized, kind, now, &binding, nil, nil, nil), nil
		case BindingUserConnector:
			binding, found, resolveErr := resolveUserConnector(normalized, candidates.UserConnectors, now)
			if !found {
				continue
			}
			if resolveErr != nil {
				return ResolvedCapabilityGrant{}, resolveErr
			}
			return newGrant(normalized, kind, now, nil, &binding, nil, nil), nil
		case BindingDevice:
			binding, found, resolveErr := resolveDevice(normalized, candidates.DeviceBindings)
			if !found {
				continue
			}
			if resolveErr != nil {
				return ResolvedCapabilityGrant{}, resolveErr
			}
			return newGrant(normalized, kind, now, nil, nil, &binding, nil), nil
		case BindingDomainOperation:
			binding, found, resolveErr := resolveDomainOperation(candidates.DomainOperations)
			if !found {
				continue
			}
			if resolveErr != nil {
				return ResolvedCapabilityGrant{}, resolveErr
			}
			return newGrant(normalized, kind, now, nil, nil, nil, &binding), nil
		default:
			return ResolvedCapabilityGrant{}, ErrInvalidRequirement
		}
	}
	return ResolvedCapabilityGrant{}, ErrCapabilityGrantRequired
}

// NormalizeRequirement validates trusted resolver input before any candidate
// source is consulted. Infrastructure adapters reuse this boundary so malformed
// requests cannot trigger provider, connector, device or owner lookups.
func NormalizeRequirement(requirement Requirement, now time.Time) (Requirement, error) {
	requirement.ResolutionID = strings.TrimSpace(requirement.ResolutionID)
	requirement.AccountID = strings.TrimSpace(requirement.AccountID)
	requirement.ServiceActorDigest = strings.TrimSpace(requirement.ServiceActorDigest)
	requirement.CapabilityKey = strings.TrimSpace(requirement.CapabilityKey)
	requirement.RegionCode = strings.ToUpper(strings.TrimSpace(requirement.RegionCode))
	requirement.SurfaceKind = strings.TrimSpace(requirement.SurfaceKind)
	requirement.ConnectionRefs = normalizeStrings(requirement.ConnectionRefs)
	requirement.InputDigest = strings.TrimSpace(requirement.InputDigest)
	now = now.UTC()
	if requirement.ResolutionID == "" || requirement.CapabilityKey == "" ||
		len(requirement.BindingPriority) == 0 || now.IsZero() {
		return Requirement{}, ErrInvalidRequirement
	}
	if requirement.RegionCode != "" && !validRegionCode(requirement.RegionCode) {
		return Requirement{}, ErrInvalidRequirement
	}
	seen := make(map[BindingKind]struct{}, len(requirement.BindingPriority))
	for _, kind := range requirement.BindingPriority {
		if !validBindingKind(kind) {
			return Requirement{}, ErrInvalidRequirement
		}
		if _, found := seen[kind]; found {
			return Requirement{}, ErrInvalidRequirement
		}
		seen[kind] = struct{}{}
	}
	if containsBindingKind(requirement.BindingPriority, BindingUserConnector) {
		if requirement.AccountID == "" {
			return Requirement{}, ErrInvalidRequirement
		}
		if requirement.SurfaceKind != "" || len(requirement.ConnectionRefs) != 0 {
			if !oneOf(requirement.SurfaceKind, "personal", "conversation", "circle") ||
				len(requirement.ConnectionRefs) == 0 || len(requirement.ConnectionRefs) > 32 {
				return Requirement{}, ErrInvalidRequirement
			}
		}
	}
	if requirement.Write && !validDigest(requirement.InputDigest) {
		return Requirement{}, ErrInvalidRequirement
	}
	return requirement, nil
}

func resolvePublicProvider(
	requirement Requirement,
	candidates []PublicProviderBinding,
) (PublicProviderBinding, bool, error) {
	matching := make([]PublicProviderBinding, 0, 1)
	for _, binding := range candidates {
		if strings.TrimSpace(binding.CapabilityKey) == requirement.CapabilityKey {
			matching = append(matching, binding)
		}
	}
	if len(matching) == 0 {
		return PublicProviderBinding{}, false, nil
	}
	if len(matching) != 1 {
		return PublicProviderBinding{}, true, ErrAmbiguousBinding
	}
	binding := matching[0]
	binding.AdapterID = strings.TrimSpace(binding.AdapterID)
	binding.ContractDigest = strings.TrimSpace(binding.ContractDigest)
	binding.ConfigRef = strings.TrimSpace(binding.ConfigRef)
	binding.RatePolicyRef = strings.TrimSpace(binding.RatePolicyRef)
	binding.SupportedRegionCodes = normalizeRegionCodes(
		binding.SupportedRegionCodes,
	)
	if binding.State != ProviderBindingReady ||
		binding.ProbeState != ProviderProbePassed {
		return PublicProviderBinding{}, true, ErrProviderUnavailable
	}
	if requirement.RegionCode != "" &&
		!supportsRegion(binding.SupportedRegionCodes, requirement.RegionCode) {
		return PublicProviderBinding{}, true, ErrProviderUnavailable
	}
	if binding.AdapterID == "" || !validDigest(binding.ContractDigest) ||
		binding.ConfigRef == "" || binding.TimeoutMs <= 0 ||
		binding.RatePolicyRef == "" {
		return PublicProviderBinding{}, true, ErrProviderUnavailable
	}
	return binding, true, nil
}

func normalizeRegionCodes(values []string) []string {
	normalized := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, raw := range values {
		value := strings.ToUpper(strings.TrimSpace(raw))
		if value == "" {
			continue
		}
		if _, found := seen[value]; found {
			continue
		}
		seen[value] = struct{}{}
		normalized = append(normalized, value)
	}
	return normalized
}

func supportsRegion(supported []string, requested string) bool {
	for _, value := range supported {
		if value == "*" || value == requested {
			return true
		}
	}
	return false
}

func validRegionCode(value string) bool {
	if len(value) < 2 || len(value) > 16 ||
		value[0] == '-' || value[len(value)-1] == '-' {
		return false
	}
	for _, character := range value {
		if (character >= 'A' && character <= 'Z') ||
			(character >= '0' && character <= '9') ||
			character == '-' {
			continue
		}
		return false
	}
	return true
}

func resolveUserConnector(
	requirement Requirement,
	candidates []UserConnectorConnection,
	now time.Time,
) (UserConnectorConnection, bool, error) {
	matching := make([]UserConnectorConnection, 0, 1)
	for _, binding := range candidates {
		if strings.TrimSpace(binding.CapabilityKey) == requirement.CapabilityKey {
			matching = append(matching, binding)
		}
	}
	if len(matching) == 0 {
		return UserConnectorConnection{}, false, nil
	}
	if len(matching) != 1 {
		return UserConnectorConnection{}, true, ErrAmbiguousBinding
	}
	binding := matching[0]
	binding.AccountID = strings.TrimSpace(binding.AccountID)
	binding.ConnectionID = strings.TrimSpace(binding.ConnectionID)
	binding.ConnectorID = strings.TrimSpace(binding.ConnectorID)
	binding.ContractDigest = strings.TrimSpace(binding.ContractDigest)
	binding.ProviderAccountSubjectDigest = strings.TrimSpace(binding.ProviderAccountSubjectDigest)
	if binding.AccountID == "" || binding.AccountID != requirement.AccountID ||
		binding.ConnectionID == "" || binding.ConnectorID == "" ||
		binding.Revision <= 0 {
		return UserConnectorConnection{}, true, ErrConnectorCapability
	}
	switch binding.GrantState {
	case ConnectorGrantRevoked:
		return UserConnectorConnection{}, true, ErrConnectorRevoked
	case ConnectorGrantExpired:
		return UserConnectorConnection{}, true, ErrConnectorExpired
	case ConnectorGrantActive:
	default:
		return UserConnectorConnection{}, true, ErrConnectorCapability
	}
	if !validDigest(binding.ContractDigest) {
		return UserConnectorConnection{}, true, ErrConnectorCapability
	}
	if binding.ProviderAccountSubjectDigest != "" &&
		!validDigest(binding.ProviderAccountSubjectDigest) {
		return UserConnectorConnection{}, true, ErrConnectorCapability
	}
	if binding.ExpiresAt != nil && !binding.ExpiresAt.After(now.UTC()) {
		return UserConnectorConnection{}, true, ErrConnectorExpired
	}
	if !contains(binding.GrantedCapabilities, requirement.CapabilityKey) {
		return UserConnectorConnection{}, true, ErrConnectorCapability
	}
	binding.FreshnessAt = binding.FreshnessAt.UTC()
	binding.ExpiresAt = normalizeTimePointer(binding.ExpiresAt)
	return binding, true, nil
}

func resolveDevice(
	requirement Requirement,
	candidates []DeviceCapabilityBinding,
) (DeviceCapabilityBinding, bool, error) {
	matching := make([]DeviceCapabilityBinding, 0, 1)
	for _, binding := range candidates {
		if strings.TrimSpace(binding.CapabilityKey) == requirement.CapabilityKey {
			matching = append(matching, binding)
		}
	}
	if len(matching) == 0 {
		return DeviceCapabilityBinding{}, false, nil
	}
	if len(matching) != 1 {
		return DeviceCapabilityBinding{}, true, ErrAmbiguousBinding
	}
	binding := matching[0]
	binding.BridgeCapability = strings.TrimSpace(binding.BridgeCapability)
	binding.AttestationDigest = strings.TrimSpace(binding.AttestationDigest)
	if binding.Availability != DeviceAvailable {
		return DeviceCapabilityBinding{}, true, ErrDeviceUnavailable
	}
	if binding.Permission != DevicePermissionGranted {
		return DeviceCapabilityBinding{}, true, ErrDevicePermissionDenied
	}
	if binding.BridgeCapability == "" || !validDigest(binding.AttestationDigest) {
		return DeviceCapabilityBinding{}, true, ErrDeviceUnavailable
	}
	return binding, true, nil
}

func resolveDomainOperation(
	candidates []DomainOperationBinding,
) (DomainOperationBinding, bool, error) {
	if len(candidates) == 0 {
		return DomainOperationBinding{}, false, nil
	}
	if len(candidates) != 1 {
		return DomainOperationBinding{}, true, ErrAmbiguousBinding
	}
	binding := candidates[0]
	binding.OwnerOperationID = strings.TrimSpace(binding.OwnerOperationID)
	binding.ContractDigest = strings.TrimSpace(binding.ContractDigest)
	if binding.OwnerOperationID == "" || !validDigest(binding.ContractDigest) {
		return DomainOperationBinding{}, true, ErrDomainOperationInvalid
	}
	return binding, true, nil
}

func newGrant(
	requirement Requirement,
	kind BindingKind,
	now time.Time,
	publicProvider *PublicProviderBinding,
	userConnector *UserConnectorConnection,
	deviceBinding *DeviceCapabilityBinding,
	domainOperation *DomainOperationBinding,
) ResolvedCapabilityGrant {
	expiresAt := now.UTC().Add(GrantTTL)
	return ResolvedCapabilityGrant{
		ResolutionID:         requirement.ResolutionID,
		AccountID:            requirement.AccountID,
		ServiceActorDigest:   requirement.ServiceActorDigest,
		CapabilityKey:        requirement.CapabilityKey,
		SurfaceKind:          requirement.SurfaceKind,
		BindingKind:          kind,
		PublicProvider:       publicProvider,
		UserConnector:        userConnector,
		DeviceBinding:        deviceBinding,
		DomainOperation:      domainOperation,
		RequiresConfirmation: requirement.Write,
		RequiresPermit:       requirement.Write,
		RequiresIdempotency:  requirement.Write,
		InputDigest:          requirement.InputDigest,
		ConfirmationDigest:   digestOpaque(requirement.ConfirmationRef),
		PermitDigest:         digestOpaque(requirement.PermitRef),
		IdempotencyDigest:    digestOpaque(requirement.IdempotencyKey),
		ResolvedAt:           now.UTC(),
		ExpiresAt:            &expiresAt,
	}
}

// OpaqueDigest commits to a protected reference without persisting its value.
// Empty input intentionally stays empty for read-only grants.
func OpaqueDigest(value string) string {
	return digestOpaque(value)
}

// IsValidDigest validates the canonical digest shape used by persisted
// capability sessions. Callers must never accept a non-canonical digest as an
// authorization binding.
func IsValidDigest(value string) bool {
	return validDigest(strings.TrimSpace(value))
}

// IsValidBindingKind keeps the persisted session decoder on the same closed
// binding-kind set as the domain resolver.
func IsValidBindingKind(kind BindingKind) bool {
	return validBindingKind(kind)
}

func digestOpaque(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func containsBindingKind(values []BindingKind, expected BindingKind) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
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
	return result
}

func oneOf(value string, values ...string) bool {
	for _, candidate := range values {
		if value == candidate {
			return true
		}
	}
	return false
}

func validBindingKind(kind BindingKind) bool {
	switch kind {
	case BindingPublicProvider, BindingUserConnector, BindingDevice, BindingDomainOperation:
		return true
	default:
		return false
	}
}

func contains(values []string, expected string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == expected {
			return true
		}
	}
	return false
}

func validDigest(value string) bool {
	if !strings.HasPrefix(value, "sha256:") || len(value) != len("sha256:")+sha256.Size*2 {
		return false
	}
	_, err := hex.DecodeString(strings.TrimPrefix(value, "sha256:"))
	return err == nil
}

func normalizeTimePointer(value *time.Time) *time.Time {
	if value == nil || value.IsZero() {
		return nil
	}
	normalized := value.UTC()
	return &normalized
}

// BindingDigest is the only binding material persisted with the short-lived
// session. It commits to the selected typed identity without storing an
// endpoint, credential, proof, permit, confirmation or raw input.
func BindingDigest(grant ResolvedCapabilityGrant) (string, error) {
	var identity string
	switch grant.BindingKind {
	case BindingPublicProvider:
		if grant.PublicProvider == nil || grant.UserConnector != nil ||
			grant.DeviceBinding != nil || grant.DomainOperation != nil {
			return "", ErrInvalidResolvedGrant
		}
		identity = fmt.Sprintf(
			"public_provider\x00%s\x00%s\x00%s",
			grant.PublicProvider.AdapterID,
			grant.PublicProvider.ContractDigest,
			grant.PublicProvider.ConfigRef,
		)
	case BindingUserConnector:
		if grant.UserConnector == nil || grant.PublicProvider != nil ||
			grant.DeviceBinding != nil || grant.DomainOperation != nil {
			return "", ErrInvalidResolvedGrant
		}
		identity = fmt.Sprintf(
			"user_connector\x00%s\x00%s\x00%s\x00%d\x00%s",
			grant.UserConnector.ConnectionID,
			grant.UserConnector.ConnectorID,
			grant.UserConnector.ContractDigest,
			grant.UserConnector.Revision,
			grant.UserConnector.ProviderAccountSubjectDigest,
		)
	case BindingDevice:
		if grant.DeviceBinding == nil || grant.PublicProvider != nil ||
			grant.UserConnector != nil || grant.DomainOperation != nil {
			return "", ErrInvalidResolvedGrant
		}
		identity = fmt.Sprintf(
			"device_capability\x00%s\x00%s",
			grant.DeviceBinding.BridgeCapability,
			grant.DeviceBinding.AttestationDigest,
		)
	case BindingDomainOperation:
		if grant.DomainOperation == nil || grant.PublicProvider != nil ||
			grant.UserConnector != nil || grant.DeviceBinding != nil {
			return "", ErrInvalidResolvedGrant
		}
		identity = fmt.Sprintf(
			"domain_operation\x00%s\x00%s",
			grant.DomainOperation.OwnerOperationID,
			grant.DomainOperation.ContractDigest,
		)
	default:
		return "", ErrInvalidResolvedGrant
	}
	sum := sha256.Sum256([]byte(identity))
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}
