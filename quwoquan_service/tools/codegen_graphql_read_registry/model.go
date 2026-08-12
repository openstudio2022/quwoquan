package main

const (
	metadataSchema   = "graphql-read-query-metadata"
	costModelVersion = "graphql-cost-v1"
)

type Options struct {
	SchemaPath      string
	MetadataPath    string
	MetadataDir     string
	CandidateDigest string
}

type metadataFile struct {
	Schema  string          `json:"schema"`
	Entries []metadataEntry `json:"entries"`
}

type metadataEntry struct {
	Document               string `json:"document"`
	CanonicalOperationID   string `json:"canonicalOperationId"`
	QueryClass             string `json:"queryClass"`
	VariablesMaxBytes      int    `json:"variablesMaxBytes"`
	MaxOwnerCalls          int    `json:"maxOwnerCalls"`
	MaxBatchKeys           int    `json:"maxBatchKeys"`
	MaxResponseBytes       int    `json:"maxResponseBytes"`
	SLORef                 string `json:"sloRef"`
	DepthExceptionRef      string `json:"depthExceptionRef,omitempty"`
	TopLevelExceptionRef   string `json:"topLevelExceptionRef,omitempty"`
	ComplexityExceptionRef string `json:"complexityExceptionRef,omitempty"`
	ExecutorKey            string `json:"executorKey"`
}

type operationBinding struct {
	operationName  string
	operationType  string
	objectIDs      []string
	authorization  authorizationMetadata
	ownerSourceDir string
}

type ownerPersistedQueryBinding struct {
	Schema               string                `json:"schema"`
	CanonicalOperationID string                `json:"canonicalOperationId"`
	ObjectID             string                `json:"objectId"`
	Document             string                `json:"document"`
	OperationName        string                `json:"operationName"`
	OperationType        string                `json:"operationType"`
	SHA256Hash           string                `json:"sha256Hash"`
	AssemblyProjectionID string                `json:"assemblyProjectionId,omitempty"`
	AssemblyMappings     []AssemblyMapping     `json:"assemblyMappings,omitempty"`
	AppClientBundle      *ownerAppClientBundle `json:"appClientBundle,omitempty"`
}

type ownerAppClientBundle struct {
	BundleID                string   `json:"bundleId"`
	Role                    string   `json:"role"`
	SupportedContentTypes   []string `json:"supportedContentTypes,omitempty"`
	RequiredForContentTypes []string `json:"requiredForContentTypes,omitempty"`
}

type authorizationMetadata struct {
	Principal       string   `json:"principal"`
	Scopes          []string `json:"scopes"`
	OwnershipPolicy string   `json:"ownershipPolicy"`
}

type RegistryDocument struct {
	CandidateDigest string          `json:"candidateDigest"`
	SchemaDigest    string          `json:"schemaDigest"`
	Entries         []RegistryEntry `json:"entries"`
}

type RegistryEntry struct {
	SHA256Hash           string                `json:"sha256Hash"`
	OperationName        string                `json:"operationName"`
	OperationType        string                `json:"operationType"`
	CanonicalOperationID string                `json:"canonicalOperationId"`
	ObjectIDs            []string              `json:"objectIds"`
	Authorization        authorizationMetadata `json:"authorization"`
	CostModelVersion     string                `json:"costModelVersion"`
	CostPlanDigest       string                `json:"costPlanDigest"`
	Cost                 CostBudget            `json:"cost"`
	CostPlan             CostPlan              `json:"costPlan"`
	PaginationVariables  []string              `json:"paginationVariables"`
	ExecutorKey          string                `json:"executorKey"`
	AppClientBundle      *AppClientBundle      `json:"appClientBundle,omitempty"`
}

type AppClientBundle struct {
	BundleID                string            `json:"bundleId"`
	Role                    string            `json:"role"`
	SupportedContentTypes   []string          `json:"supportedContentTypes,omitempty"`
	RequiredForContentTypes []string          `json:"requiredForContentTypes,omitempty"`
	SelectedFields          []string          `json:"selectedFields"`
	AssemblyMappings        []AssemblyMapping `json:"assemblyMappings"`
}

type AssemblyMapping struct {
	TargetField         string           `json:"targetField"`
	PresenceSourceField string           `json:"presenceSourceField,omitempty"`
	Sources             []AssemblySource `json:"sources"`
}

type AssemblySource struct {
	SourceField string `json:"sourceField"`
	Strategy    string `json:"strategy"`
	TargetKey   string `json:"targetKey,omitempty"`
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

type CostPlan struct {
	BaseComplexity   int              `json:"baseComplexity"`
	ListMultipliers  []ListMultiplier `json:"listMultipliers"`
	MaxOwnerCalls    int              `json:"maxOwnerCalls"`
	MaxBatchKeys     int              `json:"maxBatchKeys"`
	MaxResponseBytes int              `json:"maxResponseBytes"`
}

type ListMultiplier struct {
	VariablePath string `json:"variablePath"`
	Coefficient  int    `json:"coefficient"`
	DefaultValue int    `json:"defaultValue"`
	MaximumValue int    `json:"maximumValue"`
}
