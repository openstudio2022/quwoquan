package ast

import "encoding/json"

// ObjectKind 是 ContractGraph 中业务对象分类的闭集。
type ObjectKind string

const (
	ObjectKindAggregateRoot     ObjectKind = "aggregate_root"
	ObjectKindOwnedEntity       ObjectKind = "owned_entity"
	ObjectKindValueObject       ObjectKind = "value_object"
	ObjectKindProjection        ObjectKind = "projection"
	ObjectKindExternalReference ObjectKind = "external_reference"
	ObjectKindAppendOnlyFact    ObjectKind = "append_only_fact"
	ObjectKindRuntimeSession    ObjectKind = "runtime_session"
)

// OperationKind 区分修改状态的 command 与只读 query。
type OperationKind string

const (
	OperationKindCommand OperationKind = "command"
	OperationKindQuery   OperationKind = "query"
	OperationKindSession OperationKind = "session"
)

// Catalog 是 loader 产生、尚未做跨文件图校验的规范化 AST。
type Catalog struct {
	Objects            []Object                  `json:"objects"`
	Operations         []Operation               `json:"operations"`
	RuntimeEntrypoints []RuntimeEntrypoint       `json:"runtimeEntrypoints"`
	Projections        []Projection              `json:"projections"`
	BusinessObjectMaps []BusinessObjectMap       `json:"businessObjectMaps"`
	ReadinessEvidence  []ObjectReadinessEvidence `json:"readinessEvidence"`
	Sources            []SourceDigest            `json:"sources"`
	Documents          []SourceDocument          `json:"documents"`
	Governance         MetadataGovernance        `json:"-"`
}

// EvidenceArtifact binds a readiness claim to the exact bytes consumed by the
// compiler. Paths are repository-relative; hashes are derived, never written
// by metadata authors.
type EvidenceArtifact struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

// ObjectReadinessEvidence is an object-packet evidence declaration. It has no
// writable status field: graph.Build derives the lifecycle stage from these
// typed evidence sets and the canonical operation contract.
type ObjectReadinessEvidence struct {
	ObjectID       string                `json:"objectId"`
	OperationIDs   []string              `json:"operationIds"`
	DomainBehavior []EvidenceArtifact    `json:"domainBehavior"`
	Store          []EvidenceArtifact    `json:"store"`
	Outbox         []EvidenceArtifact    `json:"outbox"`
	Reader         []EvidenceArtifact    `json:"reader"`
	Transport      []EvidenceArtifact    `json:"transport"`
	AppClient      []EvidenceArtifact    `json:"appClient"`
	Page           []EvidenceArtifact    `json:"page"`
	LocalContract  []EvidenceArtifact    `json:"localContract"`
	APIIntegration []EvidenceArtifact    `json:"apiIntegration"`
	UserAcceptance []EvidenceArtifact    `json:"userAcceptance"`
	Environments   []EnvironmentEvidence `json:"environments"`
	SourcePath     string                `json:"sourcePath"`
}

type EnvironmentEvidence struct {
	Name     string           `json:"name"`
	Artifact EvidenceArtifact `json:"artifact"`
}

type Object struct {
	ID             string     `json:"id"`
	Domain         string     `json:"domain"`
	Name           string     `json:"name"`
	Kind           ObjectKind `json:"kind"`
	KindExplicit   bool       `json:"kindExplicit"`
	AggregateOwner string     `json:"aggregateOwner,omitempty"`
	StorageBackend string     `json:"storageBackend,omitempty"`
	SourcePath     string     `json:"sourcePath"`
	Members        []Member   `json:"members,omitempty"`
}

type Member struct {
	Name           string     `json:"name"`
	Kind           ObjectKind `json:"kind,omitempty"`
	Cardinality    string     `json:"cardinality,omitempty"`
	MaxCardinality int        `json:"maxCardinality,omitempty"`
	AggregateOwner string     `json:"aggregateOwner,omitempty"`
}

// RuntimeEntrypoint models an object-owned typed invocation seam that is not an
// HTTP API operation.  Middleware, event projectors/subscriptions, atomic
// internal append ports and external ports all use this one non-HTTP track;
// none of them is exposed to App/OpenAPI generators.
type RuntimeEntrypoint struct {
	ID              string        `json:"id"`
	LocalID         string        `json:"localId"`
	Domain          string        `json:"domain"`
	ObjectID        string        `json:"objectId"`
	RuntimeKind     string        `json:"runtimeKind"`
	Phase           string        `json:"phase"`
	ApplicationKind OperationKind `json:"applicationKind"`
	Facet           string        `json:"facet"`
	FacadeMethod    string        `json:"facadeMethod"`
	ObjectOwner     string        `json:"objectOwner"`
	SourceEvents    []string      `json:"sourceEvents,omitempty"`
	SourceObjects   []string      `json:"sourceObjects,omitempty"`
	Checkpoint      string        `json:"checkpoint,omitempty"`
	Rebuild         string        `json:"rebuild,omitempty"`
	Tombstone       string        `json:"tombstone,omitempty"`
	Idempotency     string        `json:"idempotency,omitempty"`
	SourcePath      string        `json:"sourcePath"`
}

type Operation struct {
	ID                     string                   `json:"id"`
	LocalID                string                   `json:"localId"`
	Domain                 string                   `json:"domain"`
	ObjectID               string                   `json:"objectId"`
	Method                 string                   `json:"method"`
	PathTemplate           string                   `json:"pathTemplate"`
	Kind                   OperationKind            `json:"kind"`
	KindExplicit           bool                     `json:"kindExplicit"`
	Facet                  string                   `json:"facet,omitempty"`
	FacadeMethod           string                   `json:"facadeMethod,omitempty"`
	AggregateOwner         string                   `json:"aggregateOwner,omitempty"`
	AppendSink             string                   `json:"appendSink,omitempty"`
	MutationTarget         string                   `json:"mutationTarget,omitempty"`
	InvariantTarget        string                   `json:"invariantTarget,omitempty"`
	SessionOwner           string                   `json:"sessionOwner,omitempty"`
	Reader                 string                   `json:"reader,omitempty"`
	Slice                  string                   `json:"slice,omitempty"`
	ActorRequirement       string                   `json:"actorRequirement,omitempty"`
	RequestEntity          string                   `json:"requestEntity,omitempty"`
	RequestBodyKind        string                   `json:"requestBodyKind,omitempty"`
	Transport              string                   `json:"transport"`
	Streaming              *StreamingPolicy         `json:"streaming,omitempty"`
	RequestBindings        *RequestBindings         `json:"requestBindings,omitempty"`
	RequestConstants       *RequestConstants        `json:"requestConstants,omitempty"`
	LegacyRequestKeys      []string                 `json:"-"`
	ClientBindingOverrides []string                 `json:"-"`
	ResponseEntity         string                   `json:"responseEntity,omitempty"`
	ResponseBody           string                   `json:"responseBody,omitempty"`
	ResponseBodyKind       string                   `json:"responseBodyKind,omitempty"`
	SourcePath             string                   `json:"sourcePath"`
	Security               map[string]string        `json:"security,omitempty"`
	AuthMode               string                   `json:"authMode"`
	Principal              string                   `json:"principal,omitempty"`
	Scopes                 []string                 `json:"scopes,omitempty"`
	Permissions            []string                 `json:"permissions,omitempty"`
	OwnershipPolicy        string                   `json:"ownershipPolicy,omitempty"`
	Commercial             CommercialBinding        `json:"commercial"`
	Reliability            ReliabilityPolicy        `json:"reliability"`
	Pagination             *PaginationPolicy        `json:"pagination,omitempty"`
	ResponseAdmission      *ResponseAdmissionPolicy `json:"responseAdmission,omitempty"`
	Concurrency            ConcurrencyPolicy        `json:"concurrency,omitempty"`
	ErrorCodes             []string                 `json:"errorCodes,omitempty"`
	Privacy                PrivacyPolicy            `json:"privacy"`
	Telemetry              TelemetryPolicy          `json:"telemetry"`
	SLO                    SLOPolicy                `json:"slo"`
	ClientContract         *ClientContract          `json:"clientContract,omitempty"`
}

type StreamingPolicy struct {
	ResumeRequestField  string   `json:"resumeRequestField"`
	ResumeResponseField string   `json:"resumeResponseField"`
	TerminalField       string   `json:"terminalField"`
	TerminalValues      []string `json:"terminalValues"`
}

// RequestBindings records the non-body wire positions of a request. The body
// remains owned solely by RequestEntity + RequestBodyKind. Name is the wire
// parameter (or authenticated context source for injected bindings); Field is
// the corresponding generated client command field.
type RequestBindings struct {
	Path     []RequestBinding `json:"path,omitempty"`
	Query    []RequestBinding `json:"query,omitempty"`
	Header   []RequestBinding `json:"header,omitempty"`
	Injected []RequestBinding `json:"injected,omitempty"`
}

type RequestBinding struct {
	Name     string `json:"name"`
	Field    string `json:"field"`
	Required *bool  `json:"required,omitempty"`
}

// RequestConstants contains operation-owned wire literals. Constants are not
// writable request fields: they are compiled into generated encoders and keep
// protocol discriminators out of the public App request model.
type RequestConstants struct {
	Body []RequestConstant `json:"body,omitempty"`
}

type RequestConstant struct {
	Name  string `json:"name"`
	Value any    `json:"value"`
}

type CommercialBinding struct {
	Status      string `json:"status"`
	Explicit    bool   `json:"explicit"`
	BlockReason string `json:"blockReason,omitempty"`
	GapID       string `json:"gapId,omitempty"`
	TargetStory string `json:"targetStory,omitempty"`
}

type ReliabilityPolicy struct {
	TimeoutMilliseconds int    `json:"timeoutMilliseconds,omitempty"`
	Cancellation        string `json:"cancellation,omitempty"`
	RetryMode           string `json:"retryMode,omitempty"`
	MaxAttempts         int    `json:"maxAttempts,omitempty"`
	Idempotency         string `json:"idempotency,omitempty"`
}

type PaginationPolicy struct {
	DefaultItems int `json:"defaultItems"`
	MaximumItems int `json:"maximumItems"`
}

type ResponseAdmissionPolicy struct {
	MaximumBodyBytes int `json:"maximumBodyBytes"`
}

// ConcurrencyPolicy only describes a caller-supplied resource precondition.
// AggregateStore expected versions remain internal service-side CAS details.
type ConcurrencyPolicy struct {
	VersionPrecondition VersionPrecondition `json:"versionPrecondition,omitempty"`
}

type VersionPrecondition string

const (
	VersionPreconditionNone    VersionPrecondition = ""
	VersionPreconditionIfMatch VersionPrecondition = "if_match"
)

type PrivacyPolicy struct {
	RequestClassification  string `json:"requestClassification,omitempty"`
	ResponseClassification string `json:"responseClassification,omitempty"`
	LogPolicy              string `json:"logPolicy,omitempty"`
}

type TelemetryPolicy struct {
	Metric     string   `json:"metric,omitempty"`
	Trace      bool     `json:"trace"`
	Attributes []string `json:"attributes,omitempty"`
}

type SLOPolicy struct {
	LatencyP95Milliseconds int     `json:"latencyP95Milliseconds,omitempty"`
	AvailabilityPercent    float64 `json:"availabilityPercent,omitempty"`
}

type ClientContract struct {
	DartImport      string `json:"dartImport"`
	ResponseType    string `json:"responseType"`
	ResponseDecoder string `json:"responseDecoder"`
}

type Projection struct {
	ID                string   `json:"id"`
	Domain            string   `json:"domain"`
	ObjectID          string   `json:"objectId"`
	ReadModel         string   `json:"readModel"`
	ReadModelExplicit bool     `json:"readModelExplicit"`
	DartClass         string   `json:"dartClass,omitempty"`
	OutputPath        string   `json:"outputPath,omitempty"`
	ExternalDartPath  string   `json:"-"`
	FieldNames        []string `json:"fieldNames,omitempty"`
	SourceEntities    []string `json:"sourceEntities,omitempty"`
	SourceEvents      []string `json:"sourceEvents,omitempty"`
	SourcePath        string   `json:"sourcePath"`
}

// MetadataGovernance is a compiler-only typed view used by cross-document
// validators. It is deliberately not serialized into ContractGraph: business
// fields, lifecycle, errors and events remain owned by their object packets.
type MetadataGovernance struct {
	Objects        []ObjectGovernance
	Enums          []EnumDefinition
	EnumReferences []EnumReference
	Types          []TypeDefinition
	Fields         []FieldDefinition
}

type TypeDefinition struct {
	Name       string
	OwnerLevel EnumOwnerLevel
	Domain     string
	ObjectID   string
	SourcePath string
}

type EnumReference struct {
	Name       string
	Domain     string
	ObjectID   string
	SourcePath string
}

type ObjectGovernance struct {
	ObjectID      string
	Domain        string
	SourcePath    string
	Lifecycle     *LifecycleDefinition
	DeclaredTypes []string
	Fields        []FieldDefinition
	Errors        []ErrorDefinition
	Events        []EventDefinition
	Privacy       *PrivacyDefinition
}

type LifecycleDefinition struct {
	States     []string
	StateField string
	Immutable  bool
	SourcePath string
}

type EnumOwnerLevel string

const (
	EnumOwnerGlobal  EnumOwnerLevel = "global"
	EnumOwnerService EnumOwnerLevel = "service"
	EnumOwnerObject  EnumOwnerLevel = "object"
)

type EnumDefinition struct {
	Name       string
	Values     []string
	OwnerLevel EnumOwnerLevel
	Domain     string
	ObjectID   string
	SourcePath string
}

type FieldDefinition struct {
	ObjectID     string
	Domain       string
	Entity       string
	Name         string
	Type         string
	EnumRef      string
	InlineValues []string
	SemanticType string
	SourcePath   string
}

type ErrorEmission struct {
	Surface    string
	Operations []string
}

type ErrorDefinition struct {
	ObjectID   string
	Code       string
	HTTPStatus *int
	EmittedBy  []ErrorEmission
	SourcePath string
}

type EventDefinition struct {
	ObjectID         string
	Name             string
	Channel          string
	PayloadEntity    string
	PayloadShape     string
	PayloadFields    []string
	Consumers        []string
	NoConsumerReason string
	SourcePath       string
}

// PrivacyDefinition 是对象 privacy.yaml 的 typed compiler view。字段与级联
// 引用在 loader 中归一，validator 不重新解释 YAML/JSON 文档。
type PrivacyDefinition struct {
	ObjectID            string
	Aggregate           string
	AppLogFields        []string
	VisibilityFields    []string
	AnonymizationFields []string
	DeletionTargets     []string
	SourcePath          string
}

// BusinessObjectMap 是字段角色与对象边界的 typed canonical 输入。
// validator 与 generator 禁止再从 SourceDocument.Content 二次解析该语义。
type BusinessObjectMap struct {
	Domain          string                       `json:"domain"`
	BoundedContexts []BoundedContextRegistration `json:"boundedContexts"`
	SourcePath      string                       `json:"sourcePath"`
	Objects         []BusinessObjectBoundary     `json:"objects"`
}

type BusinessObjectBoundary struct {
	CanonicalObject      string               `json:"canonicalObject"`
	BoundedContext       string               `json:"boundedContext"`
	ObjectKind           ObjectKind           `json:"objectKind"`
	AggregateOwner       string               `json:"aggregateOwner,omitempty"`
	Identity             ObjectIdentity       `json:"identity"`
	InvariantRefs        []string             `json:"invariantRefs"`
	MemberBounds         map[string]int       `json:"memberBounds"`
	StorageRole          string               `json:"storageRole"`
	StorageBackend       string               `json:"storageBackend,omitempty"`
	MutationEntrypoints  []string             `json:"mutationEntrypoints"`
	EventConsumers       []string             `json:"eventConsumers"`
	LifecycleRefs        []string             `json:"lifecycleRefs"`
	SourceDocument       string               `json:"sourceDocument,omitempty"`
	SourceEntity         string               `json:"sourceEntity,omitempty"`
	Access               ObjectAccessPolicy   `json:"access"`
	Relationships        []ObjectRelationship `json:"relationships"`
	CounterSources       map[string]string    `json:"counterSources,omitempty"`
	FieldRoles           map[string][]string  `json:"fieldRoles"`
	LocalIdentityReasons map[string]string    `json:"localIdentityReasons,omitempty"`
}

// ObjectIdentity 明确对象身份与并发版本的来源；version 不再由 DTO 或存储实现猜测。
type ObjectIdentity struct {
	Fields        []string `json:"fields"`
	VersionSource string   `json:"versionSource"`
	VersionField  string   `json:"versionField,omitempty"`
}

// BoundedContextRegistration 将业务语义边界与物理 service/workload 解耦。
// 一个 metadata domain 可以承载多个高内聚限界上下文，但上下文之间只能经公开合同交互。
type BoundedContextRegistration struct {
	ContextID    string              `json:"contextId"`
	Name         string              `json:"name"`
	Role         string              `json:"role"`
	AccessPolicy ContextAccessPolicy `json:"accessPolicy"`
}

type ContextAccessPolicy struct {
	Commands     string `json:"commands"`
	Queries      string `json:"queries"`
	ChildObjects string `json:"childObjects"`
	CrossContext string `json:"crossContext"`
}

// ObjectAccessPolicy 明确对象可被怎样访问，避免调用方绕过聚合根直达子对象或存储。
type ObjectAccessPolicy struct {
	Commands     string `json:"commands"`
	Queries      string `json:"queries"`
	CrossContext string `json:"crossContext"`
}

// ObjectRelationship 是跨对象依赖的唯一登记。TargetObject 使用 canonical object id。
type ObjectRelationship struct {
	Name            string   `json:"name"`
	TargetObject    string   `json:"targetObject,omitempty"`
	TargetObjects   []string `json:"targetObjects,omitempty"`
	ReferenceFields []string `json:"referenceFields"`
	Kind            string   `json:"kind"`
	Cardinality     string   `json:"cardinality"`
	Consistency     string   `json:"consistency"`
	Access          string   `json:"access"`
	OnDelete        string   `json:"onDelete"`
}

type SourceDigest struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

// SourceDocument 是所有 generator 读取 metadata 的规范化输入。
// Content 已转成确定性的 JSON，禁止 generator 再自行解析 YAML。
type SourceDocument struct {
	Path      string          `json:"path"`
	SHA256    string          `json:"sha256"`
	MediaType string          `json:"mediaType"`
	Content   json.RawMessage `json:"content"`
}
