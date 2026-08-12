package main

import (
	"encoding/json"
	"regexp"
)

const (
	appClientGenerator  = "codegen_graphql_app_client"
	appClientOutputPath = "lib/runtime/transport/graphql_read/generated/persisted_graphql_queries.g.dart"
	gatewayOperationID  = "gateway.persisted_query_execution.ExecutePersistedGraphQLQuery"
	detailBundleID      = "content.post.ContentPostDetail"
	detailOperationName = "ContentPostDetail"
	detailOperationID   = "content.post.GetPost"
	detailProjectionID  = "content.post.ContentPostDetailSlice"
)

var (
	canonicalDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	queryHashPattern       = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

type Options struct {
	MetadataDir       string
	RegistryPath      string
	MetadataPath      string
	SchemaPath        string
	ContractGraphPath string
	AppLockPath       string
}

type registryDocument struct {
	CandidateDigest string          `json:"candidateDigest"`
	SchemaDigest    string          `json:"schemaDigest"`
	Entries         []registryEntry `json:"entries"`
}

type registryEntry struct {
	SHA256Hash           string                  `json:"sha256Hash"`
	OperationName        string                  `json:"operationName"`
	OperationType        string                  `json:"operationType"`
	CanonicalOperationID string                  `json:"canonicalOperationId"`
	ObjectIDs            []string                `json:"objectIds"`
	CostModelVersion     string                  `json:"costModelVersion"`
	CostPlanDigest       string                  `json:"costPlanDigest"`
	Cost                 registryCost            `json:"cost"`
	CostPlan             registryCostPlan        `json:"costPlan"`
	PaginationVariables  []string                `json:"paginationVariables"`
	ExecutorKey          string                  `json:"executorKey"`
	AppClientBundle      *appClientBundleBinding `json:"appClientBundle,omitempty"`
	Authorization        registryAuthorization   `json:"authorization"`
}

type registryAuthorization struct {
	Principal       string   `json:"principal"`
	Scopes          []string `json:"scopes"`
	OwnershipPolicy string   `json:"ownershipPolicy"`
}

type registryCost struct {
	Depth             int    `json:"depth"`
	TopLevelFields    int    `json:"topLevelFields"`
	Complexity        int    `json:"complexity"`
	VariablesMaxBytes int    `json:"variablesMaxBytes"`
	PageSizeMax       int    `json:"pageSizeMax"`
	MaxOwnerCalls     int    `json:"maxOwnerCalls"`
	MaxBatchKeys      int    `json:"maxBatchKeys"`
	MaxResponseBytes  int    `json:"maxResponseBytes"`
	SLORef            string `json:"sloRef"`
}

type registryCostPlan struct {
	BaseComplexity   int                      `json:"baseComplexity"`
	ListMultipliers  []registryListMultiplier `json:"listMultipliers"`
	MaxOwnerCalls    int                      `json:"maxOwnerCalls"`
	MaxBatchKeys     int                      `json:"maxBatchKeys"`
	MaxResponseBytes int                      `json:"maxResponseBytes"`
}

type registryListMultiplier struct {
	VariablePath string `json:"variablePath"`
	Coefficient  int    `json:"coefficient"`
	DefaultValue int    `json:"defaultValue"`
	MaximumValue int    `json:"maximumValue"`
}

type queryMetadataDocument struct {
	Schema  string               `json:"schema"`
	Entries []queryMetadataEntry `json:"entries"`
}

type queryMetadataEntry struct {
	Document             string `json:"document"`
	CanonicalOperationID string `json:"canonicalOperationId"`
	QueryClass           string `json:"queryClass"`
	VariablesMaxBytes    int    `json:"variablesMaxBytes"`
	MaxOwnerCalls        int    `json:"maxOwnerCalls"`
	MaxBatchKeys         int    `json:"maxBatchKeys"`
	MaxResponseBytes     int    `json:"maxResponseBytes"`
	SLORef               string `json:"sloRef"`
	ExecutorKey          string `json:"executorKey"`
}

type contractGraphDocument struct {
	Operations  []graphOperation  `json:"operations"`
	Projections []graphProjection `json:"projections"`
	Documents   []graphDocument   `json:"documents"`
}

type graphDocument struct {
	Path    string          `json:"path"`
	SHA256  string          `json:"sha256"`
	Content json.RawMessage `json:"content"`
}

type graphOperation struct {
	ID                string                 `json:"id"`
	LocalOperationID  string                 `json:"localId"`
	Domain            string                 `json:"domain"`
	ObjectID          string                 `json:"objectId"`
	Kind              string                 `json:"kind"`
	Facet             string                 `json:"facet"`
	FacadeMethod      string                 `json:"facadeMethod"`
	Method            string                 `json:"method"`
	PathTemplate      string                 `json:"pathTemplate"`
	ActorRequirement  string                 `json:"actorRequirement"`
	AuthMode          string                 `json:"authMode"`
	Principal         string                 `json:"principal"`
	OwnershipPolicy   string                 `json:"ownershipPolicy"`
	Commercial        graphCommercial        `json:"commercial"`
	Reliability       graphReliability       `json:"reliability"`
	ErrorCodes        []string               `json:"errorCodes"`
	Privacy           graphPrivacy           `json:"privacy"`
	Telemetry         graphTelemetry         `json:"telemetry"`
	SLO               graphSLO               `json:"slo"`
	RequestEntity     string                 `json:"requestEntity"`
	RequestBodyKind   string                 `json:"requestBodyKind"`
	Transport         string                 `json:"transport"`
	ResponseEntity    string                 `json:"responseEntity"`
	ResponseBody      string                 `json:"responseBody"`
	ResponseBodyKind  string                 `json:"responseBodyKind"`
	ResponseAdmission graphResponseAdmission `json:"responseAdmission"`
	SourcePath        string                 `json:"sourcePath"`
}

type graphCommercial struct {
	Status      string `json:"status"`
	BlockReason string `json:"blockReason"`
}

type graphReliability struct {
	TimeoutMilliseconds int    `json:"timeoutMilliseconds"`
	Cancellation        string `json:"cancellation"`
	RetryMode           string `json:"retryMode"`
	MaxAttempts         int    `json:"maxAttempts"`
	Idempotency         string `json:"idempotency"`
}

type graphPrivacy struct {
	RequestClassification  string `json:"requestClassification"`
	ResponseClassification string `json:"responseClassification"`
	LogPolicy              string `json:"logPolicy"`
}

type graphTelemetry struct {
	Metric     string   `json:"metric"`
	Trace      bool     `json:"trace"`
	Attributes []string `json:"attributes"`
}

type graphSLO struct {
	LatencyP95Milliseconds int     `json:"latencyP95Milliseconds"`
	AvailabilityPercent    float64 `json:"availabilityPercent"`
}

type graphResponseAdmission struct {
	MaximumBodyBytes int `json:"maximumBodyBytes"`
}

type graphProjection struct {
	ID         string   `json:"id"`
	FieldNames []string `json:"fieldNames"`
}

type appLockDocument struct {
	Generator            string              `json:"generator"`
	ContractGraph        appLockGraphBinding `json:"contractGraph"`
	AppExposedOperations []appLockOperation  `json:"appExposedOperations"`
}

type appLockGraphBinding struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type appLockOperation struct {
	CanonicalOperationID string            `json:"canonicalOperationId"`
	RequestEntity        string            `json:"requestEntity"`
	SurfaceIDs           []string          `json:"surfaceIds"`
	ClientContract       appClientContract `json:"clientContract"`
}

type appClientContract struct {
	ResponseType    string `json:"responseType"`
	ResponseDecoder string `json:"responseDecoder"`
}

type generatedOutput struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
	Bytes  int    `json:"bytes"`
}

type generatedManifest struct {
	Generator           string            `json:"generator"`
	RegistrySHA256      string            `json:"registrySha256"`
	ContractGraphSHA256 string            `json:"contractGraphSha256"`
	AppLockSHA256       string            `json:"appLockSha256"`
	Outputs             []generatedOutput `json:"outputs"`
}

type bundleQueryInput struct {
	entry          registryEntry
	metadata       queryMetadataEntry
	responseKey    string
	rootTypeName   string
	selectedFields []string
}

type bundleGenerationInput struct {
	registry       registryDocument
	queries        []bundleQueryInput
	plan           detailBundlePlan
	gateway        graphOperation
	ownerOperation appLockOperation
	projection     graphProjection
	registryDigest string
	graphDigest    string
	appLockDigest  string
	schemaDigest   string
}
