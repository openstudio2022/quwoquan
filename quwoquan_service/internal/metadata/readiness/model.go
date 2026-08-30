package readiness

import (
	"time"

	"quwoquan_service/internal/metadata/ast"
)

// Static readiness policy is compiled by metadata/load into the ContractGraph.
// Keep the dynamic evaluator on that same closed vocabulary instead of
// maintaining a second, caller-authored type system.
type Layer = ast.ReadinessLayer

const (
	LayerLocalContract         = ast.ReadinessLayerLocalContract
	LayerAPIIntegration        = ast.ReadinessLayerAPIIntegration
	LayerUserAcceptance        = ast.ReadinessLayerUserAcceptance
	LayerEnvironmentAcceptance = ast.ReadinessLayerEnvironmentAcceptance
	LayerRollback              = ast.ReadinessLayerRollback
	LayerReplay                = ast.ReadinessLayerReplay
)

type Producer = ast.ReadinessProducer

const (
	ProducerService = ast.ReadinessProducerService
	ProducerApp     = ast.ReadinessProducerApp
	ProducerOps     = ast.ReadinessProducerOps
)

type Status string

const (
	StatusPassed  Status = "passed"
	StatusFailed  Status = "failed"
	StatusBlocked Status = "blocked"
	StatusSkipped Status = "skipped"
)

type TargetKind = ast.ReadinessTargetKind

const (
	TargetOperation = ast.ReadinessTargetOperation
	TargetPage      = ast.ReadinessTargetPage
	TargetObject    = ast.ReadinessTargetObject
)

type ReadinessTarget = ast.ReadinessCaseTarget

// ReadinessResultBundle is dynamic runner output. GeneratedAt identifies the
// bundle only and is deliberately excluded from closure decisions.
type ReadinessResultBundle struct {
	GeneratedAt time.Time             `json:"generatedAt"`
	Results     []ReadinessCaseResult `json:"results"`
}

// DeploymentBinding is the immutable package/configuration identity of one
// environment deployment. Every dynamic result repeats this binding so a
// passed case cannot be replayed against a different baseline or package.
type DeploymentBinding struct {
	DeploymentTarget        string `json:"deploymentTarget"`
	BaselineID              string `json:"baselineId"`
	PackageDigest           string `json:"packageDigest"`
	ConfigurationDigest     string `json:"configurationDigest"`
	CandidateManifestSHA256 string `json:"candidateManifestSha256"`
}

type ReadinessCaseResult struct {
	ObjectID                string          `json:"objectId"`
	SpecRef                 string          `json:"specRef"`
	CaseID                  string          `json:"caseId"`
	Producer                Producer        `json:"producer"`
	Layer                   Layer           `json:"layer"`
	Status                  Status          `json:"status"`
	Target                  ReadinessTarget `json:"target"`
	CommitSHA               string          `json:"commitSha"`
	ContractGraphSourceHash string          `json:"contractGraphSourceHash"`
	DeploymentTarget        string          `json:"deploymentTarget"`
	BaselineID              string          `json:"baselineId"`
	PackageDigest           string          `json:"packageDigest"`
	ConfigurationDigest     string          `json:"configurationDigest"`
	CandidateManifestSHA256 string          `json:"candidateManifestSha256"`
	CandidateDigest         string          `json:"candidateDigest,omitempty"`
	ReleaseDigest           string          `json:"releaseDigest,omitempty"`
	ReleaseID               string          `json:"releaseId,omitempty"`
	TargetUATBindingDigest  string          `json:"targetUatBindingDigest,omitempty"`
	EntrySurface            string          `json:"entrySurface,omitempty"`
	Carrier                 string          `json:"carrier,omitempty"`
	DeviceIdentity          string          `json:"deviceIdentity,omitempty"`
	UATProfile              string          `json:"uatProfile,omitempty"`
	NonPromotable           bool            `json:"nonPromotable"`
	ArtifactClass           string          `json:"artifactClass,omitempty"`
	PhysicalDevice          bool            `json:"physicalDevice"`
	ReasonCode              string          `json:"reasonCode,omitempty"`
	ObservedOutcome         string          `json:"observedOutcome,omitempty"`
	ObservedReleaseID       string          `json:"observedReleaseId,omitempty"`
	PreviousReleaseID       string          `json:"previousReleaseId,omitempty"`
	Environment             string          `json:"environment"`
	Platform                string          `json:"platform"`
	DeviceClass             string          `json:"deviceClass"`
	DeviceRegistered        bool            `json:"deviceRegistered"`
	Provider                string          `json:"provider"`
	StartedAt               time.Time       `json:"startedAt"`
	CompletedAt             time.Time       `json:"completedAt"`
	RunnerIdentity          string          `json:"runnerIdentity"`
	ArtifactSHA256          string          `json:"artifactSha256"`
	ArtifactPath            string          `json:"artifactPath,omitempty"`
	ReceiptRef              string          `json:"receiptRef,omitempty"`
}

// ReceiptBinding is the non-secret identity attested by a trusted runner
// receipt. It deliberately excludes artifactSha256 to avoid a self-hash cycle;
// the bundle hashes the complete receipt bytes separately.
type ReceiptBinding struct {
	ObjectID                string          `json:"objectId"`
	SpecRef                 string          `json:"specRef"`
	CaseID                  string          `json:"caseId"`
	Producer                Producer        `json:"producer"`
	Layer                   Layer           `json:"layer"`
	Status                  Status          `json:"status"`
	Target                  ReadinessTarget `json:"target"`
	CommitSHA               string          `json:"commitSha"`
	ContractGraphSourceHash string          `json:"contractGraphSourceHash"`
	DeploymentTarget        string          `json:"deploymentTarget"`
	BaselineID              string          `json:"baselineId"`
	PackageDigest           string          `json:"packageDigest"`
	ConfigurationDigest     string          `json:"configurationDigest"`
	CandidateManifestSHA256 string          `json:"candidateManifestSha256"`
	CandidateDigest         string          `json:"candidateDigest,omitempty"`
	ReleaseDigest           string          `json:"releaseDigest,omitempty"`
	ReleaseID               string          `json:"releaseId,omitempty"`
	TargetUATBindingDigest  string          `json:"targetUatBindingDigest,omitempty"`
	EntrySurface            string          `json:"entrySurface,omitempty"`
	Carrier                 string          `json:"carrier,omitempty"`
	DeviceIdentity          string          `json:"deviceIdentity,omitempty"`
	UATProfile              string          `json:"uatProfile,omitempty"`
	NonPromotable           bool            `json:"nonPromotable"`
	ArtifactClass           string          `json:"artifactClass,omitempty"`
	PhysicalDevice          bool            `json:"physicalDevice"`
	ReasonCode              string          `json:"reasonCode,omitempty"`
	ObservedOutcome         string          `json:"observedOutcome,omitempty"`
	ObservedReleaseID       string          `json:"observedReleaseId,omitempty"`
	PreviousReleaseID       string          `json:"previousReleaseId,omitempty"`
	Environment             string          `json:"environment"`
	Platform                string          `json:"platform"`
	DeviceClass             string          `json:"deviceClass"`
	DeviceRegistered        bool            `json:"deviceRegistered"`
	Provider                string          `json:"provider"`
	StartedAt               time.Time       `json:"startedAt"`
	CompletedAt             time.Time       `json:"completedAt"`
	RunnerIdentity          string          `json:"runnerIdentity"`
	RunnerSourcePath        string          `json:"runnerSourcePath"`
	RemoteComposition       bool            `json:"remoteComposition"`
	FixtureFree             bool            `json:"fixtureFree"`
	DependenciesReady       bool            `json:"dependenciesReady"`
	ProviderVerified        bool            `json:"providerVerified"`
}

// ReadinessReceipt is a small, rebuildable manifest over the real runner
// evidence. Raw logs, credentials, endpoints and device secrets stay outside
// this wire; EvidenceSHA256 binds the separately governed proof bytes.
type ReadinessReceipt struct {
	Binding        ReceiptBinding `json:"binding"`
	EvidenceSHA256 string         `json:"evidenceSha256"`
}

type DigestBinding = ast.ReadinessDigestBinding

const (
	DigestCandidate = ast.ReadinessDigestCandidate
	DigestRelease   = ast.ReadinessDigestRelease
	DigestEither    = ast.ReadinessDigestEither
)

type ExecutionRequirement = ast.ReadinessExecutionRequirement

type ReadinessCaseContract = ast.ReadinessCaseContract

type EvaluationContext struct {
	CommitSHA       string
	Deployments     map[string]DeploymentBinding
	CandidateDigest string
	ReleaseDigest   string
}

type ClosureResult struct {
	CommercialReady bool            `json:"commercialReady"`
	Objects         []ObjectClosure `json:"objects"`
	Violations      []Violation     `json:"violations"`
}

type ObjectClosure struct {
	ObjectID        string   `json:"objectId"`
	Implemented     bool     `json:"implemented"`
	CommercialReady bool     `json:"commercialReady"`
	Missing         []string `json:"missing"`
}

type Violation struct {
	Code     string `json:"code"`
	ObjectID string `json:"objectId,omitempty"`
	CaseID   string `json:"caseId,omitempty"`
	Message  string `json:"message"`
}
