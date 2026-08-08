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
	// ObjectKindProcessManager 是长流程编排器（saga）：它拥有自己的状态机、补偿、
	// 超时与取消语义，进度由 checkpoint 而不是聚合版本表达。把它记成 aggregate_root
	// 会让这些语义无处声明，因此它是独立 kind 而不是聚合根的一种用法。
	ObjectKindProcessManager ObjectKind = "process_manager"
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
	ReadinessCases     []ReadinessCaseContract   `json:"readinessCases"`
	ReadinessEvidence  []ObjectReadinessEvidence `json:"readinessEvidence"`
	Sources            []SourceDigest            `json:"sources"`
	Documents          []SourceDocument          `json:"documents"`
	Governance         MetadataGovernance        `json:"-"`
}

// ReadinessLayer is the closed set of dynamic acceptance layers that can bind
// a runner result. The case contract is static metadata; pass/fail history is
// deliberately absent from this AST.
type ReadinessLayer string

const (
	ReadinessLayerLocalContract         ReadinessLayer = "local_contract"
	ReadinessLayerAPIIntegration        ReadinessLayer = "api_integration"
	ReadinessLayerUserAcceptance        ReadinessLayer = "user_acceptance"
	ReadinessLayerEnvironmentAcceptance ReadinessLayer = "environment_acceptance"
	ReadinessLayerRollback              ReadinessLayer = "rollback"
	ReadinessLayerReplay                ReadinessLayer = "replay"
)

// ReadinessProducer identifies the system boundary that owns both the case
// contract and its runner. Layer alone is not sufficient: service and App both
// execute local_contract/api_integration cases, and one producer's receipt must
// never satisfy the other producer's responsibility.
type ReadinessProducer string

const (
	ReadinessProducerService ReadinessProducer = "service"
	ReadinessProducerApp     ReadinessProducer = "app"
	ReadinessProducerOps     ReadinessProducer = "ops"
)

type ReadinessTargetKind string

const (
	ReadinessTargetOperation ReadinessTargetKind = "operation"
	ReadinessTargetPage      ReadinessTargetKind = "page"
	ReadinessTargetObject    ReadinessTargetKind = "object"
)

type ReadinessDigestBinding string

const (
	ReadinessDigestCandidate ReadinessDigestBinding = "candidate"
	ReadinessDigestRelease   ReadinessDigestBinding = "release"
	ReadinessDigestEither    ReadinessDigestBinding = "candidate_or_release"
)

type ReadinessCaseTarget struct {
	Kind ReadinessTargetKind `json:"kind"`
	ID   string              `json:"id"`
}

// ReadinessExecutionRequirement is one exact runner responsibility. It is a
// tuple rather than a cartesian product so that one provider/device result can
// never satisfy another environment slot.
type ReadinessExecutionRequirement struct {
	Environment   string                 `json:"environment"`
	Platform      string                 `json:"platform"`
	DeviceClass   string                 `json:"deviceClass"`
	Provider      string                 `json:"provider"`
	DigestBinding ReadinessDigestBinding `json:"digestBinding"`
}

// ReadinessCaseContract comes only from the owning object's operations.yaml.
// Operation targets are normalized to their fully-qualified operation ID by
// load. RunnerSourcePath is the exact, verified test runner identity that a
// receipt must attest; SourcePath preserves which object-local source authored
// the contract.
type ReadinessCaseContract struct {
	ObjectID         string                          `json:"objectId"`
	SpecRef          string                          `json:"specRef"`
	CaseID           string                          `json:"caseId"`
	Producer         ReadinessProducer               `json:"producer"`
	Layer            ReadinessLayer                  `json:"layer"`
	Target           ReadinessCaseTarget             `json:"target"`
	RunnerSourcePath string                          `json:"runnerSourcePath"`
	Executions       []ReadinessExecutionRequirement `json:"executions"`
	SourcePath       string                          `json:"sourcePath"`
}

// EvidenceArtifact binds a readiness claim to the exact bytes consumed by the
// compiler. Paths are repository-relative; hashes are derived, never written
// by metadata authors.
type EvidenceArtifact struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

// StorageEvidence binds a named storage seam to one artifact without adding
// ownership fields to EvidenceArtifact. Artifact identity remains exactly
// {path, sha256}; storage ownership is a separate, typed relationship.
type StorageEvidence struct {
	Storage  string           `json:"storage"`
	Artifact EvidenceArtifact `json:"artifact"`
}

// ServiceStructureEvidence is the service-produced half of one object packet.
// Every value is a repository file identity, never a pass/fail result.
type ServiceStructureEvidence struct {
	Domain         []EvidenceArtifact `json:"domain"`
	Store          []EvidenceArtifact `json:"store"`
	Outbox         []StorageEvidence  `json:"outbox"`
	Reader         []EvidenceArtifact `json:"reader"`
	Transport      []EvidenceArtifact `json:"transport"`
	LocalContract  []EvidenceArtifact `json:"localContract"`
	APIIntegration []EvidenceArtifact `json:"apiIntegration"`
}

// AppStructureEvidence is derived from the canonical object-shaped App tree.
// PageParticipant is informational; only PageOwned can require presentation.
// This prevents a multi-object page from forcing every participant to create a
// second presentation root.
type AppStructureEvidence struct {
	Domain          []EvidenceArtifact `json:"domain"`
	Application     []EvidenceArtifact `json:"application"`
	Adapters        []EvidenceArtifact `json:"adapters"`
	Presentation    []EvidenceArtifact `json:"presentation"`
	LocalContract   []EvidenceArtifact `json:"localContract"`
	APIIntegration  []EvidenceArtifact `json:"apiIntegration"`
	UserAcceptance  []EvidenceArtifact `json:"userAcceptance"`
	PageParticipant bool               `json:"pageParticipant"`
	PageOwned       bool               `json:"pageOwned"`
}

// OpsStructureEvidence records only runner entrypoints. Runtime results live in
// readiness.ReadinessResultBundle and are deliberately absent from ContractGraph.
type OpsStructureEvidence struct {
	EnvironmentAcceptance []EvidenceArtifact `json:"environmentAcceptance"`
	RollbackRunner        []EvidenceArtifact `json:"rollbackRunner"`
	ReplayRunner          []EvidenceArtifact `json:"replayRunner"`
}

// ObjectReadinessEvidence is a static, producer-separated structure packet.
// graph.Build may derive at most the implemented stage from it. Environment
// history and result status are forbidden here.
type ObjectReadinessEvidence struct {
	ObjectID     string                   `json:"objectId"`
	OperationIDs []string                 `json:"operationIds"`
	Service      ServiceStructureEvidence `json:"service"`
	App          AppStructureEvidence     `json:"app"`
	Ops          OpsStructureEvidence     `json:"ops"`
	// PublicationStores 是该对象在自己的 `storage.yaml` 里标注为发布 seam
	// （`transactional_outbox` / `transactional_event_log`）的存储名。它表达**归属**：
	// 哪张存储归这个对象。Outbox 证据只针对这些存储去代码里取真，写入方所在目录是实现
	// 细节——共享 store、参数化 store、装配处注入集合名都是正当形态。
	PublicationStores []string `json:"publicationStores,omitempty"`
	// DeliveryStores 是 PublicationStores 里被标注为 `transactional_outbox` 的子集：只有
	// 它们需要投递实现。事务性事件表按定义没有具名消费者，不在此列。
	DeliveryStores []string `json:"deliveryStores,omitempty"`
	// PublicationDelivery 是存储名 → 投递实现位置（读取存储并推进进度）。判定既不看文件名
	// 也不看契约声明的索引，只看实际行为，理由见 load/publication_evidence.go。
	PublicationDelivery []StorageEvidence `json:"publicationDelivery,omitempty"`
	// UnannotatedStores 是该对象声明了但没有标注 `publication_role` 的存储名。未标注不是
	// 「不发布」，是判别位缺失，必须成为可见缺口。
	UnannotatedStores []string `json:"unannotatedStores,omitempty"`
	// UnresolvedPublicationWrites 是「关系名在服务里被绑定过，但写入发生在 Go AST 跟不动的
	// 地方」的发布 seam。这是**维度盲点**不是缺口：解析器不跨函数跟踪构造参数注入的句柄与
	// 调用方传入的事务上下文，报成缺口等于让人去补一份本来就存在的实现。
	UnresolvedPublicationWrites []string `json:"unresolvedPublicationWrites,omitempty"`
	// UnresolvedPublicationDelivery 是「投递实现在扫描范围之外」的发件箱：表名被参数化地
	// 交给共享 dispatcher（`pgoutbox.NewDispatcher(pool, publisher, "product_ops_outbox")`），
	// 服务树内看不到任何读取语句。同样是盲点不是缺口。
	UnresolvedPublicationDelivery []string `json:"unresolvedPublicationDelivery,omitempty"`
	// UndeclaredStorageWrites 是反方向的缺陷：对象实现树里有事务性写入，目标关系名却在全仓
	// 任何 `storage.yaml` 里都没有声明位。它与「声明了但没观测到写入」修法不同，必须分开。
	UndeclaredStorageWrites []string `json:"undeclaredStorageWrites,omitempty"`
	// PythonImplementation 表示实现树里有 Python 生产代码。Go AST 对它完全不可见，该对象的
	// 发布判定只能记盲点，既不判达标也不判缺口。
	PythonImplementation bool   `json:"pythonImplementation,omitempty"`
	SourcePath           string `json:"sourcePath"`
}

type Object struct {
	ID             string               `json:"id"`
	Domain         string               `json:"domain"`
	Name           string               `json:"name"`
	Kind           ObjectKind           `json:"kind"`
	KindExplicit   bool                 `json:"kindExplicit"`
	AggregateOwner string               `json:"aggregateOwner,omitempty"`
	StorageBackend string               `json:"storageBackend,omitempty"`
	SourcePath     string               `json:"sourcePath"`
	Members        []Member             `json:"members,omitempty"`
	Lifecycle      *LifecycleDefinition `json:"lifecycle,omitempty"`
}

type Member struct {
	Name           string     `json:"name"`
	Kind           ObjectKind `json:"kind,omitempty"`
	Identity       []string   `json:"identity,omitempty"`
	Cardinality    string     `json:"cardinality,omitempty"`
	MaxCardinality int        `json:"maxCardinality,omitempty"`
	Ownership      string     `json:"ownership,omitempty"`
	WriteAccess    string     `json:"writeAccess,omitempty"`
	AppendOnly     bool       `json:"appendOnly,omitempty"`
	AggregateOwner string     `json:"aggregateOwner,omitempty"`
	Description    string     `json:"description"`
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
	SourceObjects   []string      `json:"sourceObjects,omitempty"`
	Idempotency     string        `json:"idempotency,omitempty"`
	// Telemetry 与 HTTP operation 同语义：metric 是契约层逻辑标识（join key），
	// 只以 contract_metric label 形式被 PromQL 消费，不是 series 发射承诺。
	Telemetry  TelemetryPolicy      `json:"telemetry"`
	SLO        RuntimeEntrypointSLO `json:"slo"`
	SourcePath string               `json:"sourcePath"`
}

// RuntimeEntrypointSLO 是非 HTTP seam 的可判定 SLO 维度闭集。它刻意不含
// availabilityPercent：那是 HTTP 5xx 错误预算，runtime seam 没有状态码。每个
// runtimeKind 只允许其中一组维度，闭集由 operations.schema.json 的 kind 分支裁定：
//
//   - middleware / internal_port（同步在途）：latency_p95_ms + failure_ratio_percent
//   - projector / event_handler / subscription（事件消费）：freshness_p95_seconds
//   - backlog_max_events + failure_ratio_percent
//   - external_port（外部调用）：latency_p95_ms + failure_ratio_percent
//   - dead_letter_ratio_percent
type RuntimeEntrypointSLO struct {
	LatencyP95Milliseconds int     `json:"latencyP95Milliseconds,omitempty"`
	FailureRatioPercent    float64 `json:"failureRatioPercent,omitempty"`
	FreshnessP95Seconds    int     `json:"freshnessP95Seconds,omitempty"`
	BacklogMaxEvents       int     `json:"backlogMaxEvents,omitempty"`
	DeadLetterRatioPercent float64 `json:"deadLetterRatioPercent,omitempty"`
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
	LifecycleOwner         string                   `json:"lifecycleOwner,omitempty"`
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
	ResponseEntityRef      string                   `json:"responseEntityRef,omitempty"`
	ResponseBody           string                   `json:"responseBody,omitempty"`
	ResponseBodyKind       string                   `json:"responseBodyKind,omitempty"`
	SuccessStatus          int                      `json:"successStatus,omitempty"`
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
	// ClientContractExplicit records a source-level client_contract block.
	// ContractGraph derives the App ABI from request_entity/response_entity;
	// validators use this marker to reject a handwritten second truth source.
	ClientContractExplicit bool `json:"-"`
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

// ReliabilityPolicy carries one operation's wall-clock and retry contract.
//
// TimeoutMilliseconds is the whole-request budget: admission until the response
// is complete. It is the value runtime/auth turns into the request deadline and
// the value the transport write ceiling is sized against.
//
// A streaming operation has no "response is complete" instant, so a single
// budget cannot describe it. Such an operation declares StreamBudget instead,
// and TimeoutMilliseconds is then derived from StreamBudget.MaxDurationMs by
// load, never authored: the two must not be independently writable, or the
// connection ceiling gains a second truth source.
type ReliabilityPolicy struct {
	TimeoutMilliseconds int                 `json:"timeoutMilliseconds,omitempty"`
	TimeoutExplicit     bool                `json:"-"`
	StreamBudget        *StreamBudgetPolicy `json:"streamBudget,omitempty"`
	Cancellation        string              `json:"cancellation,omitempty"`
	RetryMode           string              `json:"retryMode,omitempty"`
	MaxAttempts         int                 `json:"maxAttempts,omitempty"`
	Idempotency         string              `json:"idempotency,omitempty"`
}

// StreamBudgetPolicy is the three independent time limits of one long-lived
// connection. They answer three different failure questions and none of them
// can substitute for another:
//
//   - HandshakeMilliseconds: admission until the first byte of the stream is
//     flushed. Bounds "the server accepted the connection and then produced
//     nothing at all".
//   - IdleMilliseconds: the gap between two consecutive payload frames. Bounds
//     "the connection is open but the producer stopped making progress".
//     Keep-alive comments deliberately do not reset it, otherwise a stalled
//     producer looks identical to a healthy one.
//   - MaxDurationMilliseconds: admission until the connection is closed no
//     matter how healthy it is. Bounds "the underlying work legitimately never
//     ends"; the client resumes through the declared streaming resume field.
type StreamBudgetPolicy struct {
	HandshakeMilliseconds   int `json:"handshakeMilliseconds"`
	IdleMilliseconds        int `json:"idleMilliseconds"`
	MaxDurationMilliseconds int `json:"maxDurationMilliseconds"`
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
	States         []string                 `json:"states,omitempty"`
	StateField     string                   `json:"stateField,omitempty"`
	Immutable      bool                     `json:"immutable,omitempty"`
	SourceEvents   []string                 `json:"sourceEvents,omitempty"`
	Checkpoint     string                   `json:"checkpoint,omitempty"`
	Rebuild        string                   `json:"rebuild,omitempty"`
	Tombstone      string                   `json:"tombstone,omitempty"`
	Idempotency    string                   `json:"idempotency,omitempty"`
	EventConsumers []LifecycleEventConsumer `json:"eventConsumers,omitempty"`
	SourcePath     string                   `json:"-"`
}

// LifecycleEventConsumer records the object-local production handler for a
// lifecycle source edge. The edge itself is authored once in
// object.yaml#lifecycle.source_events; handler entries deliberately do not
// repeat event lists and are not exposed as synthetic operations.
type LifecycleEventConsumer struct {
	Name           string            `json:"name"`
	Kind           string            `json:"kind"`
	Facet          string            `json:"facet"`
	Method         string            `json:"method"`
	Idempotency    string            `json:"idempotency"`
	Implementation *EvidenceArtifact `json:"implementation,omitempty"`
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
	ObjectID       string
	Domain         string
	Entity         string
	Name           string
	Type           string
	EnumRef        string
	InlineValues   []string
	SemanticType   string
	Classification string
	LogPolicy      string
	SourcePath     string
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
	ObjectID string
	Name     string
	// DeliverySemantics 是受控投递保证，Topic 是该事件落在哪个具名主题上。
	// 两者由 `channel` 拆出：那个字段没有值域，同时混装机制、topic 名和笔误。
	DeliverySemantics     string
	WireEventType         string
	Topic                 string
	PayloadEntity         string
	PayloadShape          string
	PayloadFields         []string
	ClientWSType          string            `json:"clientWsType,omitempty"`
	ClientPayloadDefaults map[string]string `json:"clientPayloadDefaults,omitempty"`
	NoConsumerReason      string
	SourcePath            string
}

// PrivacyDefinition binds a complete authored privacy document to the object
// identity derived from its canonical path. Validators consume Document and do
// not reparse SourceDocument or keep a second private YAML view.
type PrivacyDefinition struct {
	ObjectID   string
	Document   PrivacyDocument
	SourcePath string
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
