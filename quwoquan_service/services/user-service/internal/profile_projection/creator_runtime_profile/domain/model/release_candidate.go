package model

import "time"

// ReleaseIdentity is the exact immutable Creator candidate identity. It is
// supplied by the Content active fence on public reads; User owns no pointer.
type ReleaseIdentity struct {
	Environment    string `json:"environment" bson:"environment"`
	SourceOwner    string `json:"sourceOwner" bson:"sourceOwner"`
	ReleaseID      string `json:"releaseId" bson:"releaseId"`
	ManifestDigest string `json:"manifestDigest" bson:"manifestDigest"`
}

// CreatorReleaseProjection is one creator snapshot inside an immutable
// release candidate. Same creatorId may coexist in any number of identities.
type CreatorReleaseProjection struct {
	ReleaseIdentity   `json:",inline" bson:",inline"`
	CreatorID         string                `json:"creatorId" bson:"creatorId"`
	PersonaID         string                `json:"personaId" bson:"personaId"`
	Profile           CreatorRuntimeProfile `json:"profile" bson:"profile"`
	AuthorID          string                `json:"authorId" bson:"authorId"`
	ProfileDigest     string                `json:"profileDigest" bson:"profileDigest"`
	DocumentDigest    string                `json:"documentDigest" bson:"documentDigest"`
	ProjectionVersion int64                 `json:"projectionVersion" bson:"projectionVersion"`
	VerifiedAt        time.Time             `json:"verifiedAt" bson:"verifiedAt"`
}

// CreatorProfileDigestBinding preserves which author/profile facts were staged.
type CreatorProfileDigestBinding struct {
	CreatorID string `json:"creatorId" bson:"creatorId"`
	AuthorID  string `json:"authorId" bson:"authorId"`
	Digest    string `json:"digest" bson:"digest"`
}

// CandidatePostgreSQLWriteCounts makes the stage-only zero-write proof explicit.
type CandidatePostgreSQLWriteCounts struct {
	UserAccounts    int `json:"userAccounts" bson:"userAccounts"`
	Personas        int `json:"personas" bson:"personas"`
	PersonaOutbox   int `json:"personaOutbox" bson:"personaOutbox"`
	CommandReceipts int `json:"commandReceipts" bson:"commandReceipts"`
}

// CreatorReleaseCandidateState attests the complete persisted Creator closure.
type CreatorReleaseCandidateState struct {
	ReleaseIdentity   `json:",inline" bson:",inline"`
	Status            string                         `json:"status" bson:"status"`
	ProjectionVersion int64                          `json:"projectionVersion" bson:"projectionVersion"`
	VerifiedAt        time.Time                      `json:"verifiedAt" bson:"verifiedAt"`
	ClosureDigest     string                         `json:"closureDigest" bson:"closureDigest"`
	ExpectedCount     int                            `json:"expectedCount" bson:"expectedCount"`
	ProjectedCount    int                            `json:"projectedCount" bson:"projectedCount"`
	AuthorIDs         []string                       `json:"authorIds" bson:"authorIds"`
	ProfileDigests    []CreatorProfileDigestBinding  `json:"profileDigests" bson:"profileDigests"`
	PostgreSQLWrites  CandidatePostgreSQLWriteCounts `json:"postgresqlWrites" bson:"postgresqlWrites"`
}
