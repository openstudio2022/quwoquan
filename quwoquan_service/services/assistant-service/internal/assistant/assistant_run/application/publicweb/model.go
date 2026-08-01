// Package publicweb defines the assistant_run-owned boundary for reading public
// internet evidence. Values in this package never carry caller credentials and
// fetched content is always treated as untrusted data.
package publicweb

import (
	"context"
	"errors"
	"time"
)

type TargetKind string

const (
	TargetURL          TargetKind = "url"
	TargetSource       TargetKind = "source"
	TargetDocumentLink TargetKind = "document_link"
)

type Target struct {
	Kind  TargetKind `json:"kind" bson:"kind"`
	Value string     `json:"value" bson:"value"`
}

type OpenRequest struct {
	RunID   string
	SkillID string
	Target  Target
	Method  string
}

// ResolvedTarget is produced only by the server-side target resolver. Origin
// and parent identifiers therefore cannot be supplied by the model.
type ResolvedTarget struct {
	URL            string
	Origin         string
	ParentSourceID string
}

// TargetLedgerEntry records both the opaque caller target and the
// server-resolved URL. Downstream workers must use TargetID instead of
// reconstructing a URL or lineage from model output.
type TargetLedgerEntry struct {
	TargetID       string    `json:"targetId" bson:"targetId"`
	RunID          string    `json:"runId" bson:"runId"`
	Requested      Target    `json:"requestedTarget" bson:"requestedTarget"`
	ResolvedURL    string    `json:"resolvedUrl" bson:"resolvedUrl"`
	Origin         string    `json:"origin" bson:"origin"`
	ParentSourceID string    `json:"parentSourceId,omitempty" bson:"parentSourceId,omitempty"`
	ResolvedAt     time.Time `json:"resolvedAt" bson:"resolvedAt"`
}

type NetworkRequest struct {
	URL      string
	Method   string
	MaxBytes int64
}

type NetworkResult struct {
	FinalURL      string
	RedirectChain []string
	ContentType   string
	Body          []byte
	FetchedAt     time.Time
}

type SourceLedgerEntry struct {
	SourceID       string    `json:"sourceId" bson:"sourceId"`
	TargetID       string    `json:"targetId" bson:"targetId"`
	Origin         string    `json:"origin" bson:"origin"`
	ParentSourceID string    `json:"parentSourceId,omitempty" bson:"parentSourceId,omitempty"`
	RunID          string    `json:"runId" bson:"runId"`
	SkillID        string    `json:"skillId,omitempty" bson:"skillId,omitempty"`
	NormalizedURL  string    `json:"normalizedUrl" bson:"normalizedUrl"`
	RedirectChain  []string  `json:"redirectChain,omitempty" bson:"redirectChain,omitempty"`
	ContentDigest  string    `json:"contentDigest" bson:"contentDigest"`
	FetchedAt      time.Time `json:"fetchedAt" bson:"fetchedAt"`
}

type DocumentLink struct {
	LinkID string `json:"linkId" bson:"linkId"`
	Title  string `json:"title,omitempty" bson:"title,omitempty"`
	Target Target `json:"target" bson:"target"`
}

type Document struct {
	DocumentID    string            `json:"documentId" bson:"documentId"`
	TargetID      string            `json:"targetId" bson:"targetId"`
	Target        Target            `json:"target" bson:"target"`
	Source        SourceLedgerEntry `json:"source" bson:"source"`
	Title         string            `json:"title,omitempty" bson:"title,omitempty"`
	ContentText   string            `json:"contentText,omitempty" bson:"contentText,omitempty"`
	ContentDigest string            `json:"contentDigest" bson:"contentDigest"`
	ContentType   string            `json:"contentType,omitempty" bson:"contentType,omitempty"`
	FetchedAt     time.Time         `json:"fetchedAt" bson:"fetchedAt"`
	Links         []DocumentLink    `json:"links,omitempty" bson:"links,omitempty"`
	ArtifactRef   string            `json:"artifactRef" bson:"artifactRef"`
	Untrusted     bool              `json:"untrusted" bson:"untrusted"`
}

// Artifact is the immutable, content-addressed raw response. Body never enters
// a tool observation; it is available only through the run-scoped ledger.
type Artifact struct {
	ArtifactID    string    `json:"artifactId" bson:"artifactId"`
	ArtifactRef   string    `json:"artifactRef" bson:"artifactRef"`
	RunID         string    `json:"runId" bson:"runId"`
	ContentDigest string    `json:"contentDigest" bson:"contentDigest"`
	ContentType   string    `json:"contentType" bson:"contentType"`
	ByteLength    int64     `json:"byteLength" bson:"byteLength"`
	Body          []byte    `json:"-" bson:"body"`
	FetchedAt     time.Time `json:"fetchedAt" bson:"fetchedAt"`
	Untrusted     bool      `json:"untrusted" bson:"untrusted"`
}

type EvidenceRecord struct {
	Target   TargetLedgerEntry
	Source   SourceLedgerEntry
	Document Document
	Artifact Artifact
}

type EvidenceStatus string

const (
	EvidenceAccepted     EvidenceStatus = "accepted"
	EvidenceInsufficient EvidenceStatus = "insufficient"
	EvidenceRejected     EvidenceStatus = "rejected"
)

// EvidenceAssessment is the deterministic hand-off from a public-web tool to
// the durable planner. It says whether another bounded step is required and
// cites only authoritative ledger identities.
type EvidenceAssessment struct {
	Status             EvidenceStatus `json:"status"`
	EvidenceSufficient bool           `json:"evidenceSufficient"`
	ReplanRequired     bool           `json:"replanRequired"`
	Reason             string         `json:"reason"`
	TargetIDs          []string       `json:"targetIds"`
	DocumentIDs        []string       `json:"documentIds"`
	ArtifactRefs       []string       `json:"artifactRefs"`
	SourceIDs          []string       `json:"sourceIds"`
}

type SearchReference struct {
	Title   string
	URL     string
	Source  string
	Snippet string
}

type DiscoveredSource struct {
	SourceID      string
	NormalizedURL string
}

type DiscoveryLedger interface {
	RecordSearchReferences(
		context.Context,
		string,
		[]SearchReference,
	) ([]DiscoveredSource, error)
}

type TargetResolver interface {
	ResolveTarget(context.Context, string, Target) (ResolvedTarget, error)
}

type NetworkFetcher interface {
	Fetch(context.Context, NetworkRequest) (NetworkResult, error)
}

// EvidenceStore commits the source ledger entry, parsed document and raw
// artifact atomically. Implementations must be idempotent by DocumentID.
type EvidenceStore interface {
	CommitEvidence(context.Context, EvidenceRecord) error
}

type BudgetGate interface {
	ReserveFetch(context.Context, string, int64) (BudgetReservation, error)
}

type BudgetReservation interface {
	AllowedBytes() int64
	Commit(int64) error
	Release()
}

var (
	ErrInvalidTarget       = errors.New("invalid public web target")
	ErrTargetUnavailable   = errors.New("public web target unavailable")
	ErrTargetRejected      = errors.New("public web target rejected")
	ErrFetchUnavailable    = errors.New("public web fetch unavailable")
	ErrBudgetExhausted     = errors.New("public web run budget exhausted")
	ErrBudgetUnavailable   = errors.New("public web run budget unavailable")
	ErrEvidenceCommit      = errors.New("public web evidence commit failed")
	ErrEvidenceUnavailable = errors.New("public web evidence unavailable")
)
