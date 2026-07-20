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
	Projections        []Projection              `json:"projections"`
	BusinessObjectMaps []BusinessObjectMap       `json:"businessObjectMaps"`
	ReadinessEvidence  []ObjectReadinessEvidence `json:"readinessEvidence"`
	Sources            []SourceDigest            `json:"sources"`
	Documents          []SourceDocument          `json:"documents"`
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
	ID             string          `json:"id"`
	Domain         string          `json:"domain"`
	Name           string          `json:"name"`
	Kind           ObjectKind      `json:"kind"`
	KindExplicit   bool            `json:"kindExplicit"`
	AggregateOwner string          `json:"aggregateOwner,omitempty"`
	StorageBackend string          `json:"storageBackend,omitempty"`
	SourcePath     string          `json:"sourcePath"`
	Members        []Member        `json:"members,omitempty"`
	DDDLayer       DDDLayerMapping `json:"dddLayerMapping,omitempty"`
	// DeferredOperations 登记对象显式推迟的公开命令（V1 不实现且不进入
	// ContractGraph operation 集合），用于豁免 aggregate root 的零入口校验。
	DeferredOperations []string `json:"deferredOperations,omitempty"`
}

// DDDLayerMapping is the generated-code and ownership routing contract. The
// compiler keeps it in the AST so generators never reconstruct directories
// from aggregate names or maintain a second path table.
type DDDLayerMapping struct {
	DomainModel  string `json:"domainModel,omitempty"`
	Ports        string `json:"ports,omitempty"`
	Application  string `json:"application,omitempty"`
	Persistence  string `json:"persistence,omitempty"`
	AdapterREST  string `json:"adapterRest,omitempty"`
	AdapterEvent string `json:"adapterEvent,omitempty"`
}

type Member struct {
	Name           string     `json:"name"`
	Kind           ObjectKind `json:"kind,omitempty"`
	Cardinality    string     `json:"cardinality,omitempty"`
	MaxCardinality int        `json:"maxCardinality,omitempty"`
	AggregateOwner string     `json:"aggregateOwner,omitempty"`
}

type Operation struct {
	ID               string            `json:"id"`
	LocalID          string            `json:"localId"`
	Domain           string            `json:"domain"`
	ObjectID         string            `json:"objectId"`
	Method           string            `json:"method"`
	PathTemplate     string            `json:"pathTemplate"`
	Kind             OperationKind     `json:"kind"`
	KindExplicit     bool              `json:"kindExplicit"`
	Facet            string            `json:"facet,omitempty"`
	FacadeMethod     string            `json:"facadeMethod,omitempty"`
	AggregateOwner   string            `json:"aggregateOwner,omitempty"`
	AppendSink       string            `json:"appendSink,omitempty"`
	MutationTarget   string            `json:"mutationTarget,omitempty"`
	InvariantTarget  string            `json:"invariantTarget,omitempty"`
	SessionOwner     string            `json:"sessionOwner,omitempty"`
	Reader           string            `json:"reader,omitempty"`
	Slice            string            `json:"slice,omitempty"`
	ActorRequirement string            `json:"actorRequirement,omitempty"`
	RequestEntity    string            `json:"requestEntity,omitempty"`
	RequestBodyKind  string            `json:"requestBodyKind,omitempty"`
	ResponseEntity   string            `json:"responseEntity,omitempty"`
	ResponseBody     string            `json:"responseBody,omitempty"`
	ResponseBodyKind string            `json:"responseBodyKind,omitempty"`
	SourcePath       string            `json:"sourcePath"`
	Security         map[string]string `json:"security,omitempty"`
	AuthMode         string            `json:"authMode"`
	Principal        string            `json:"principal,omitempty"`
	Scopes           []string          `json:"scopes,omitempty"`
	Permissions      []string          `json:"permissions,omitempty"`
	OwnershipPolicy  string            `json:"ownershipPolicy,omitempty"`
	Commercial       CommercialBinding `json:"commercial"`
	Reliability      ReliabilityPolicy `json:"reliability"`
	Concurrency      ConcurrencyPolicy `json:"concurrency,omitempty"`
	ErrorCodes       []string          `json:"errorCodes,omitempty"`
	Privacy          PrivacyPolicy     `json:"privacy"`
	Telemetry        TelemetryPolicy   `json:"telemetry"`
	SLO              SLOPolicy         `json:"slo"`
	ClientContract   *ClientContract   `json:"clientContract,omitempty"`
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
	DartImport      string            `json:"dartImport"`
	RequestType     string            `json:"requestType"`
	ResponseType    string            `json:"responseType"`
	RequestEncoder  string            `json:"requestEncoder"`
	ResponseDecoder string            `json:"responseDecoder"`
	PathBindings    map[string]string `json:"pathBindings,omitempty"`
	QueryBindings   map[string]string `json:"queryBindings,omitempty"`
}

type Projection struct {
	ID         string `json:"id"`
	Domain     string `json:"domain"`
	ObjectID   string `json:"objectId"`
	ReadModel  string `json:"readModel"`
	DartClass  string `json:"dartClass,omitempty"`
	SourcePath string `json:"sourcePath"`
}

// BusinessObjectMap 是字段角色与对象边界的 typed canonical 输入。
// validator 与 generator 禁止再从 SourceDocument.Content 二次解析该语义。
type BusinessObjectMap struct {
	Domain          string                       `json:"domain"`
	DecisionRefs    []string                     `json:"decisionRefs"`
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
