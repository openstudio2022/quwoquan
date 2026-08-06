package trust

import (
	"encoding/json"

	"quwoquan_service/internal/metadata/readiness"
)

const (
	snapshotSignatureDomain       = "quwoquan/readiness/current-snapshot/v1\x00"
	receiptSignatureDomain        = "quwoquan/readiness/receipt/v1\x00"
	journeyCatalogSignatureDomain = "quwoquan/readiness/journey-catalog/v1\x00"
	journeyReceiptSignatureDomain = "quwoquan/readiness/journey-receipt/v1\x00"
)

// EnvironmentDeployments is deliberately a closed four-environment object.
// A map would permit an unknown environment or silently omit one. Each value
// is package-bound and is covered by the CurrentSnapshot signature.
type EnvironmentDeployments struct {
	Alpha readiness.DeploymentBinding `json:"alpha"`
	Beta  readiness.DeploymentBinding `json:"beta"`
	Gamma readiness.DeploymentBinding `json:"gamma"`
	Prod  readiness.DeploymentBinding `json:"prod"`
}

// CurrentSnapshot is the release authority's exact current-state assertion.
// All fields participate in the Ed25519 signature.
type CurrentSnapshot struct {
	CommitSHA               string                 `json:"commitSha"`
	ContractGraphSourceHash string                 `json:"contractGraphSourceHash"`
	Deployments             EnvironmentDeployments `json:"deployments"`
	CandidateDigest         string                 `json:"candidateDigest"`
	ReleaseDigest           string                 `json:"releaseDigest"`
}

// SignedCurrentSnapshot carries base64-encoded exact payload bytes. Signing
// decoded/normalized JSON would permit producer and verifier canonicalization
// to drift, so the signature is always over the decoded payload bytes.
type SignedCurrentSnapshot struct {
	KeyID     string `json:"keyId"`
	Payload   string `json:"payload"`
	Signature string `json:"signature"`
}

type SnapshotKeyring struct {
	Authorities []SnapshotAuthority `json:"authorities"`
}

type SnapshotAuthority struct {
	KeyID     string `json:"keyId"`
	PublicKey string `json:"publicKey"`
}

type RunnerKeyring struct {
	Runners []RunnerAuthority `json:"runners"`
}

// RunnerAuthority is a closed runnerIdentity -> public key binding. The wire
// contains no private-key, credential, endpoint or secret-bearing field.
type RunnerAuthority struct {
	RunnerIdentity string `json:"runnerIdentity"`
	KeyID          string `json:"keyId"`
	PublicKey      string `json:"publicKey"`
}

// DetachedReceiptSignature signs the exact readiness receipt bytes. It is
// stored next to the receipt as <receipt>.sig.json and is not itself included
// in artifactSha256.
type DetachedReceiptSignature struct {
	KeyID     string `json:"keyId"`
	Signature string `json:"signature"`
}

// CurrentJourneyCatalog is the release-governance authority's complete
// AppRoot Journey policy. It is bound to the same current ContractGraph source
// identity as the result bundle, but remains separate from untrusted runner
// output so a runner cannot omit a required Journey or execution slot.
type CurrentJourneyCatalog struct {
	ContractGraphSourceHash string                       `json:"contractGraphSourceHash"`
	Catalog                 readiness.JourneyCaseCatalog `json:"catalog"`
}

type SignedCurrentJourneyCatalog struct {
	KeyID     string `json:"keyId"`
	Payload   string `json:"payload"`
	Signature string `json:"signature"`
}

type JourneyCatalogKeyring struct {
	Authorities []JourneyCatalogAuthority `json:"authorities"`
}

type JourneyCatalogAuthority struct {
	KeyID     string `json:"keyId"`
	PublicKey string `json:"publicKey"`
}

// RawPayload exists only to make exact signed bytes explicit to callers that
// prepare snapshot envelopes outside this package.
type RawPayload = json.RawMessage

// SnapshotSigningMessage and ReceiptSigningMessage domain-separate the two
// Ed25519 protocols even when an authority deliberately reuses a public key.
func SnapshotSigningMessage(payload []byte) []byte {
	return signingMessage(snapshotSignatureDomain, payload)
}

func ReceiptSigningMessage(receipt []byte) []byte {
	return signingMessage(receiptSignatureDomain, receipt)
}

func JourneyCatalogSigningMessage(payload []byte) []byte {
	return signingMessage(journeyCatalogSignatureDomain, payload)
}

func JourneyReceiptSigningMessage(receipt []byte) []byte {
	return signingMessage(journeyReceiptSignatureDomain, receipt)
}

func signingMessage(domain string, payload []byte) []byte {
	message := make([]byte, 0, len(domain)+len(payload))
	message = append(message, domain...)
	message = append(message, payload...)
	return message
}
