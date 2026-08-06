package readiness

import (
	"context"
	"time"

	"quwoquan_service/internal/metadata/graph"
)

type JourneyTargetKind string

const (
	JourneyTargetPage    JourneyTargetKind = "page"
	JourneyTargetJourney JourneyTargetKind = "journey"
)

// JourneyTarget deliberately has no object identity. Root/shell pages and
// cross-object AppRoot journeys must never be forced through an invented
// objectId merely to reuse object readiness.
type JourneyTarget struct {
	Kind JourneyTargetKind `json:"kind"`
	ID   string            `json:"id"`
}

type JourneyDefinition struct {
	JourneyID string `json:"journeyId"`
	SpecRef   string `json:"specRef"`
}

// JourneyCaseCatalog is current policy supplied by a trusted authority. It is
// deliberately not part of the result bundle, so a runner cannot omit a case
// or weaken the execution matrix it is meant to prove.
type JourneyCaseCatalog struct {
	Journeys []JourneyDefinition   `json:"journeys"`
	Cases    []JourneyCaseContract `json:"cases"`
}

type JourneyCaseContract struct {
	JourneyID        string                 `json:"journeyId"`
	SpecRef          string                 `json:"specRef"`
	CaseID           string                 `json:"caseId"`
	Producer         Producer               `json:"producer"`
	Layer            Layer                  `json:"layer"`
	Target           JourneyTarget          `json:"target"`
	RunnerSourcePath string                 `json:"runnerSourcePath"`
	Executions       []ExecutionRequirement `json:"executions"`
}

// JourneyCaseAuthority resolves the complete, canonical AppRoot Journey set
// and its required cases for the checked-out source snapshot. Implementations
// are expected to parse the current AppRoot spec/test governance; callers may
// not pass an ad-hoc catalog to Evaluate.
type JourneyCaseAuthority interface {
	CurrentJourneyCatalog(context.Context, *graph.ContractGraph) (JourneyCaseCatalog, error)
}

type JourneyReadinessResultBundle struct {
	GeneratedAt time.Time                    `json:"generatedAt"`
	Results     []JourneyReadinessCaseResult `json:"results"`
}

type JourneyReadinessCaseResult struct {
	JourneyID               string        `json:"journeyId"`
	SpecRef                 string        `json:"specRef"`
	CaseID                  string        `json:"caseId"`
	Producer                Producer      `json:"producer"`
	Layer                   Layer         `json:"layer"`
	Status                  Status        `json:"status"`
	Target                  JourneyTarget `json:"target"`
	CommitSHA               string        `json:"commitSha"`
	ContractGraphSourceHash string        `json:"contractGraphSourceHash"`
	DeploymentTarget        string        `json:"deploymentTarget"`
	BaselineID              string        `json:"baselineId"`
	PackageDigest           string        `json:"packageDigest"`
	ConfigurationDigest     string        `json:"configurationDigest"`
	CandidateManifestSHA256 string        `json:"candidateManifestSha256"`
	CandidateDigest         string        `json:"candidateDigest,omitempty"`
	ReleaseDigest           string        `json:"releaseDigest,omitempty"`
	Environment             string        `json:"environment"`
	Platform                string        `json:"platform"`
	DeviceClass             string        `json:"deviceClass"`
	Provider                string        `json:"provider"`
	StartedAt               time.Time     `json:"startedAt"`
	CompletedAt             time.Time     `json:"completedAt"`
	RunnerIdentity          string        `json:"runnerIdentity"`
	ArtifactSHA256          string        `json:"artifactSha256"`
	ArtifactPath            string        `json:"artifactPath,omitempty"`
	ReceiptRef              string        `json:"receiptRef,omitempty"`
}

type JourneyReceiptBinding struct {
	JourneyID               string        `json:"journeyId"`
	SpecRef                 string        `json:"specRef"`
	CaseID                  string        `json:"caseId"`
	Producer                Producer      `json:"producer"`
	Layer                   Layer         `json:"layer"`
	Status                  Status        `json:"status"`
	Target                  JourneyTarget `json:"target"`
	CommitSHA               string        `json:"commitSha"`
	ContractGraphSourceHash string        `json:"contractGraphSourceHash"`
	DeploymentTarget        string        `json:"deploymentTarget"`
	BaselineID              string        `json:"baselineId"`
	PackageDigest           string        `json:"packageDigest"`
	ConfigurationDigest     string        `json:"configurationDigest"`
	CandidateManifestSHA256 string        `json:"candidateManifestSha256"`
	CandidateDigest         string        `json:"candidateDigest,omitempty"`
	ReleaseDigest           string        `json:"releaseDigest,omitempty"`
	Environment             string        `json:"environment"`
	Platform                string        `json:"platform"`
	DeviceClass             string        `json:"deviceClass"`
	Provider                string        `json:"provider"`
	StartedAt               time.Time     `json:"startedAt"`
	CompletedAt             time.Time     `json:"completedAt"`
	RunnerIdentity          string        `json:"runnerIdentity"`
	RunnerSourcePath        string        `json:"runnerSourcePath"`
	RemoteComposition       bool          `json:"remoteComposition"`
	FixtureFree             bool          `json:"fixtureFree"`
	DependenciesReady       bool          `json:"dependenciesReady"`
	ProviderVerified        bool          `json:"providerVerified"`
	PhysicalDevice          bool          `json:"physicalDevice"`
}

type JourneyReadinessReceipt struct {
	Binding        JourneyReceiptBinding `json:"binding"`
	EvidenceSHA256 string                `json:"evidenceSha256"`
}

type JourneyClosureResult struct {
	CommercialReady bool               `json:"commercialReady"`
	Journeys        []JourneyClosure   `json:"journeys"`
	Violations      []JourneyViolation `json:"violations"`
}

type JourneyClosure struct {
	JourneyID       string   `json:"journeyId"`
	CommercialReady bool     `json:"commercialReady"`
	Missing         []string `json:"missing"`
}

type JourneyViolation struct {
	Code      string `json:"code"`
	JourneyID string `json:"journeyId,omitempty"`
	CaseID    string `json:"caseId,omitempty"`
	Message   string `json:"message"`
}
