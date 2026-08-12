package domain

import (
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"
)

const (
	DefaultMaxDepth          = 3
	MaxDepth                 = 5
	DefaultMaxTopLevelFields = 3
	MaxTopLevelFields        = 5
	DefaultMaxComplexity     = 500
	MaxComplexity            = 1000
	MaxVariablesBytes        = 64 * 1024
	MaxPageSize              = 100
	MaxOwnerCalls            = 64
	MaxBatchKeys             = 10_000
	MaxResponseBytes         = 4 * 1024 * 1024
	MaxRegistryEntries       = 10_000
	OperationTypeQuery       = "query"
	RegistrySourceLocal      = "local_contract"
	RegistrySourceSigned     = "signed_release"
)

var (
	hashPattern      = regexp.MustCompile(`^[0-9a-f]{64}$`)
	digestPattern    = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	graphQLName      = regexp.MustCompile(`^[_A-Za-z][_0-9A-Za-z]*$`)
	operationPattern = regexp.MustCompile(`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[A-Z][A-Za-z0-9]*$`)
	objectIDPattern  = regexp.MustCompile(`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`)
	executorPattern  = regexp.MustCompile(`^[a-z][A-Za-z0-9]*(\.[a-zA-Z][A-Za-z0-9]*)+$`)
	variablePath     = regexp.MustCompile(`^[_A-Za-z][_0-9A-Za-z]*(\.[_A-Za-z][_0-9A-Za-z]*)*$`)
)

type AuthorizationBinding struct {
	Principal       string   `json:"principal"`
	Scopes          []string `json:"scopes"`
	OwnershipPolicy string   `json:"ownershipPolicy"`
}

type CostBudget struct {
	Depth                  int    `json:"depth"`
	TopLevelFields         int    `json:"topLevelFields"`
	Complexity             int    `json:"complexity"`
	VariablesMaxBytes      int    `json:"variablesMaxBytes"`
	PageSizeMax            int    `json:"pageSizeMax"`
	MaxOwnerCalls          int    `json:"maxOwnerCalls"`
	MaxBatchKeys           int    `json:"maxBatchKeys"`
	MaxResponseBytes       int    `json:"maxResponseBytes"`
	SLORef                 string `json:"sloRef"`
	DepthExceptionRef      string `json:"depthExceptionRef,omitempty"`
	TopLevelExceptionRef   string `json:"topLevelExceptionRef,omitempty"`
	ComplexityExceptionRef string `json:"complexityExceptionRef,omitempty"`
}

type Entry struct {
	SHA256Hash           string               `json:"sha256Hash"`
	OperationName        string               `json:"operationName"`
	OperationType        string               `json:"operationType"`
	CanonicalOperationID string               `json:"canonicalOperationId"`
	ObjectIDs            []string             `json:"objectIds"`
	Authorization        AuthorizationBinding `json:"authorization"`
	CostModelVersion     string               `json:"costModelVersion"`
	CostPlanDigest       string               `json:"costPlanDigest"`
	Cost                 CostBudget           `json:"cost"`
	CostPlan             CostPlan             `json:"costPlan"`
	PaginationVariables  []string             `json:"paginationVariables,omitempty"`
	ExecutorKey          string               `json:"executorKey"`
	AppClientBundle      *AppClientBundle     `json:"appClientBundle,omitempty"`
}

type RegistrySource struct {
	Kind            string
	CandidateDigest string
	SchemaDigest    string
	SignatureKeyID  string
	PayloadDigest   string
}

type Registry struct {
	entries map[string]Entry
	source  RegistrySource
}

func NewRegistry(entries []Entry) (*Registry, error) {
	return newRegistry(entries, RegistrySource{Kind: RegistrySourceLocal})
}

func newRegistry(entries []Entry, source RegistrySource) (*Registry, error) {
	if len(entries) == 0 {
		return nil, errors.New("persisted query registry must contain at least one entry")
	}
	if len(entries) > MaxRegistryEntries {
		return nil, fmt.Errorf("persisted query registry entries=%d exceeds %d", len(entries), MaxRegistryEntries)
	}
	registry := &Registry{
		entries: make(map[string]Entry, len(entries)),
		source:  source,
	}
	seenOperationNames := make(map[string]bool, len(entries))
	seenCanonicalOperations := make(map[string]bool, len(entries))
	for index, candidate := range entries {
		entry := cloneEntry(candidate)
		if err := entry.Validate(); err != nil {
			return nil, fmt.Errorf("persisted query registry entry %d: %w", index, err)
		}
		if _, duplicate := registry.entries[entry.SHA256Hash]; duplicate {
			return nil, fmt.Errorf("duplicate persisted query hash %s", entry.SHA256Hash)
		}
		if seenOperationNames[entry.OperationName] {
			return nil, fmt.Errorf("duplicate persisted query operationName %s", entry.OperationName)
		}
		if seenCanonicalOperations[entry.CanonicalOperationID] {
			return nil, fmt.Errorf("duplicate persisted query canonicalOperationId %s", entry.CanonicalOperationID)
		}
		seenOperationNames[entry.OperationName] = true
		seenCanonicalOperations[entry.CanonicalOperationID] = true
		registry.entries[entry.SHA256Hash] = entry
	}
	if err := validateRegistryBundles(registry.Entries()); err != nil {
		return nil, fmt.Errorf("persisted query registry bundles: %w", err)
	}
	return registry, nil
}

func (entry Entry) Validate() error {
	if !ValidHash(entry.SHA256Hash) {
		return errors.New("sha256Hash must be 64 lowercase hexadecimal characters")
	}
	if !graphQLName.MatchString(entry.OperationName) {
		return fmt.Errorf("invalid GraphQL operationName %q", entry.OperationName)
	}
	if entry.OperationType != OperationTypeQuery {
		return fmt.Errorf("operationType %q is forbidden; only query is supported", entry.OperationType)
	}
	if !operationPattern.MatchString(entry.CanonicalOperationID) {
		return fmt.Errorf("invalid canonicalOperationId %q", entry.CanonicalOperationID)
	}
	if len(entry.ObjectIDs) == 0 {
		return errors.New("objectIds must bind the exact non-empty object set")
	}
	if err := validateSortedUnique("objectIds", entry.ObjectIDs, objectIDPattern); err != nil {
		return err
	}
	if err := entry.Authorization.Validate(); err != nil {
		return fmt.Errorf("authorization: %w", err)
	}
	if entry.CostModelVersion != CostModelVersionV1 {
		return fmt.Errorf("costModelVersion=%q is unsupported", entry.CostModelVersion)
	}
	if !ValidDigest(entry.CostPlanDigest) {
		return errors.New("costPlanDigest must be canonical sha256")
	}
	if err := entry.Cost.Validate(); err != nil {
		return fmt.Errorf("cost: %w", err)
	}
	if err := entry.CostPlan.Validate(); err != nil {
		return fmt.Errorf("costPlan: %w", err)
	}
	planDigest, err := entry.CostPlan.Digest()
	if err != nil {
		return fmt.Errorf("costPlan: %w", err)
	}
	if entry.CostPlanDigest != planDigest {
		return errors.New("costPlanDigest does not match canonical costPlan JSON")
	}
	worstCase, err := entry.CostPlan.WorstCaseComplexity()
	if err != nil {
		return fmt.Errorf("costPlan: %w", err)
	}
	if entry.Cost.Complexity != worstCase {
		return fmt.Errorf("cost.complexity=%d does not equal costPlan worstCase=%d", entry.Cost.Complexity, worstCase)
	}
	if entry.Cost.MaxOwnerCalls != entry.CostPlan.MaxOwnerCalls ||
		entry.Cost.MaxBatchKeys != entry.CostPlan.MaxBatchKeys ||
		entry.Cost.MaxResponseBytes != entry.CostPlan.MaxResponseBytes {
		return errors.New("cost execution limits do not match costPlan")
	}
	if !executorPattern.MatchString(entry.ExecutorKey) {
		return fmt.Errorf("invalid executorKey %q", entry.ExecutorKey)
	}
	if entry.AppClientBundle != nil {
		if err := entry.AppClientBundle.Validate(); err != nil {
			return fmt.Errorf("appClientBundle: %w", err)
		}
	}
	if err := validateSortedUnique("paginationVariables", entry.PaginationVariables, variablePath); err != nil {
		return err
	}
	return nil
}

func (binding AuthorizationBinding) Validate() error {
	allowedPrincipals := map[string]struct{}{
		"public": {}, "account": {}, "persona": {}, "device": {},
		"service": {}, "operator": {}, "admin": {},
	}
	if _, ok := allowedPrincipals[binding.Principal]; !ok {
		return fmt.Errorf("unsupported principal %q", binding.Principal)
	}
	if strings.TrimSpace(binding.OwnershipPolicy) == "" {
		return errors.New("ownershipPolicy is required")
	}
	if err := validateSortedUnique("scopes", binding.Scopes, nil); err != nil {
		return err
	}
	for _, scope := range binding.Scopes {
		if strings.TrimSpace(scope) == "" {
			return errors.New("scopes must not contain blank values")
		}
	}
	return nil
}

func (budget CostBudget) Validate() error {
	if budget.Depth < 1 || budget.Depth > MaxDepth {
		return fmt.Errorf("depth=%d is outside 1..%d", budget.Depth, MaxDepth)
	}
	if budget.TopLevelFields < 1 || budget.TopLevelFields > MaxTopLevelFields {
		return fmt.Errorf("topLevelFields=%d is outside 1..%d", budget.TopLevelFields, MaxTopLevelFields)
	}
	if budget.Complexity < 1 || budget.Complexity > MaxComplexity {
		return fmt.Errorf("complexity=%d is outside 1..%d", budget.Complexity, MaxComplexity)
	}
	if budget.VariablesMaxBytes < 1 || budget.VariablesMaxBytes > MaxVariablesBytes {
		return fmt.Errorf("variablesMaxBytes=%d is outside 1..%d", budget.VariablesMaxBytes, MaxVariablesBytes)
	}
	if budget.PageSizeMax < 1 || budget.PageSizeMax > MaxPageSize {
		return fmt.Errorf("pageSizeMax=%d is outside 1..%d", budget.PageSizeMax, MaxPageSize)
	}
	if budget.MaxOwnerCalls < 1 || budget.MaxOwnerCalls > MaxOwnerCalls {
		return fmt.Errorf("maxOwnerCalls=%d is outside 1..%d", budget.MaxOwnerCalls, MaxOwnerCalls)
	}
	if budget.MaxBatchKeys < 1 || budget.MaxBatchKeys > MaxBatchKeys {
		return fmt.Errorf("maxBatchKeys=%d is outside 1..%d", budget.MaxBatchKeys, MaxBatchKeys)
	}
	if budget.MaxResponseBytes < 1 || budget.MaxResponseBytes > MaxResponseBytes {
		return fmt.Errorf("maxResponseBytes=%d is outside 1..%d", budget.MaxResponseBytes, MaxResponseBytes)
	}
	if err := validateReference("sloRef", budget.SLORef, true, false); err != nil {
		return err
	}
	if err := validateReference("depthExceptionRef", budget.DepthExceptionRef, budget.Depth > DefaultMaxDepth, true); err != nil {
		return err
	}
	if err := validateReference("topLevelExceptionRef", budget.TopLevelExceptionRef, budget.TopLevelFields > DefaultMaxTopLevelFields, true); err != nil {
		return err
	}
	if err := validateReference("complexityExceptionRef", budget.ComplexityExceptionRef, budget.Complexity > DefaultMaxComplexity, false); err != nil {
		return err
	}
	return nil
}

func validateReference(name, value string, required, forbidWhenOptional bool) error {
	if value != strings.TrimSpace(value) || strings.ContainsAny(value, "\r\n\t ") || len(value) > 512 {
		return fmt.Errorf("%s is invalid", name)
	}
	if required && value == "" {
		return fmt.Errorf("%s is required by the registered cost", name)
	}
	if !required && forbidWhenOptional && value != "" {
		return fmt.Errorf("%s is forbidden when no exception is required", name)
	}
	if value != "" && !strings.Contains(value, ":") {
		return fmt.Errorf("%s must be a typed reference", name)
	}
	return nil
}

func ValidHash(value string) bool {
	return hashPattern.MatchString(value)
}

func ValidDigest(value string) bool {
	return digestPattern.MatchString(value)
}

func (registry *Registry) Lookup(hash string) (Entry, bool) {
	if registry == nil {
		return Entry{}, false
	}
	entry, ok := registry.entries[hash]
	return cloneEntry(entry), ok
}

func (registry *Registry) Source() RegistrySource {
	if registry == nil {
		return RegistrySource{}
	}
	return registry.source
}

// Entries returns a deterministic defensive copy so the composition root can
// prove every signed binding has an executable ContractGraph owner before it
// accepts traffic.
func (registry *Registry) Entries() []Entry {
	if registry == nil {
		return nil
	}
	hashes := make([]string, 0, len(registry.entries))
	for hash := range registry.entries {
		hashes = append(hashes, hash)
	}
	sort.Strings(hashes)
	entries := make([]Entry, 0, len(hashes))
	for _, hash := range hashes {
		entries = append(entries, cloneEntry(registry.entries[hash]))
	}
	return entries
}

func (registry *Registry) IsSignedRelease() bool {
	return registry != nil && registry.source.Kind == RegistrySourceSigned
}

func cloneEntry(entry Entry) Entry {
	entry.ObjectIDs = append([]string(nil), entry.ObjectIDs...)
	entry.Authorization.Scopes = append([]string(nil), entry.Authorization.Scopes...)
	entry.PaginationVariables = append([]string(nil), entry.PaginationVariables...)
	entry.AppClientBundle = cloneAppClientBundle(entry.AppClientBundle)
	if entry.CostPlan.ListMultipliers != nil {
		entry.CostPlan.ListMultipliers = append(
			make([]ListMultiplier, 0, len(entry.CostPlan.ListMultipliers)),
			entry.CostPlan.ListMultipliers...,
		)
	}
	return entry
}

func validateSortedUnique(name string, values []string, pattern *regexp.Regexp) error {
	if len(values) == 0 {
		return nil
	}
	if !sort.StringsAreSorted(values) {
		return fmt.Errorf("%s must be sorted for deterministic release digests", name)
	}
	for index, value := range values {
		if index > 0 && value == values[index-1] {
			return fmt.Errorf("%s contains duplicate %q", name, value)
		}
		if pattern != nil && !pattern.MatchString(value) {
			return fmt.Errorf("%s contains invalid value %q", name, value)
		}
	}
	return nil
}
