package trust

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"fmt"

	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/readiness"
)

// SignedSnapshotProvider is package-bound to one signature-verified snapshot.
// CurrentSnapshot additionally binds that assertion to the graph passed by the
// evaluator, so a valid signature over a stale ContractGraph hash still fails.
type SignedSnapshotProvider struct {
	snapshot   readiness.EvaluationContext
	sourceHash string
}

func NewSignedSnapshotProvider(
	envelopeBytes []byte,
	keyringBytes []byte,
	schemas *readiness.WireSchemas,
) (*SignedSnapshotProvider, error) {
	authorities, err := decodeSnapshotKeyring(keyringBytes)
	if err != nil {
		return nil, err
	}
	var envelope SignedCurrentSnapshot
	if err := decodeStrict(envelopeBytes, &envelope, "signed current snapshot"); err != nil {
		return nil, err
	}
	if !validIdentity(envelope.KeyID) {
		return nil, fmt.Errorf("signed current snapshot identity is invalid")
	}
	publicKey, exists := authorities[envelope.KeyID]
	if !exists {
		return nil, fmt.Errorf("signed current snapshot keyId is not trusted")
	}
	payload, err := base64.StdEncoding.Strict().DecodeString(envelope.Payload)
	if err != nil || len(payload) == 0 {
		return nil, fmt.Errorf("signed current snapshot payload must be non-empty base64")
	}
	signature, err := decodeSignature(envelope.Signature)
	if err != nil {
		return nil, fmt.Errorf("signed current snapshot: %w", err)
	}
	if !ed25519.Verify(publicKey, SnapshotSigningMessage(payload), signature) {
		return nil, fmt.Errorf("signed current snapshot signature is invalid")
	}
	if schemas == nil {
		return nil, fmt.Errorf("current snapshot schema authority is required")
	}
	if err := schemas.ValidateCurrentSnapshot(payload); err != nil {
		return nil, err
	}
	var snapshot CurrentSnapshot
	if err := decodeStrict(payload, &snapshot, "current snapshot payload"); err != nil {
		return nil, err
	}
	if err := validateCurrentSnapshot(snapshot); err != nil {
		return nil, err
	}
	return &SignedSnapshotProvider{
		sourceHash: snapshot.ContractGraphSourceHash,
		snapshot: readiness.EvaluationContext{
			CommitSHA: snapshot.CommitSHA,
			Deployments: map[string]readiness.DeploymentBinding{
				"alpha": snapshot.Deployments.Alpha,
				"beta":  snapshot.Deployments.Beta,
				"gamma": snapshot.Deployments.Gamma,
				"prod":  snapshot.Deployments.Prod,
			},
			CandidateDigest: snapshot.CandidateDigest,
			ReleaseDigest:   snapshot.ReleaseDigest,
		},
	}, nil
}

func (provider *SignedSnapshotProvider) CurrentSnapshot(
	ctx context.Context,
	current *graph.ContractGraph,
) (readiness.EvaluationContext, error) {
	if err := ctx.Err(); err != nil {
		return readiness.EvaluationContext{}, err
	}
	if provider == nil {
		return readiness.EvaluationContext{}, fmt.Errorf("signed current snapshot provider is nil")
	}
	actual, err := readiness.ContractGraphSourceHash(current)
	if err != nil {
		return readiness.EvaluationContext{}, fmt.Errorf("derive current ContractGraph source hash: %w", err)
	}
	if actual != provider.sourceHash {
		return readiness.EvaluationContext{}, fmt.Errorf("signed current snapshot is stale for ContractGraph source hash")
	}
	copy := provider.snapshot
	copy.Deployments = map[string]readiness.DeploymentBinding{}
	for environment, deployment := range provider.snapshot.Deployments {
		copy.Deployments[environment] = deployment
	}
	return copy, nil
}

func decodeSnapshotKeyring(data []byte) (map[string]ed25519.PublicKey, error) {
	var keyring SnapshotKeyring
	if err := decodeStrict(data, &keyring, "snapshot keyring"); err != nil {
		return nil, err
	}
	if len(keyring.Authorities) == 0 {
		return nil, fmt.Errorf("snapshot keyring identity is invalid")
	}
	result := make(map[string]ed25519.PublicKey, len(keyring.Authorities))
	for _, authority := range keyring.Authorities {
		if !validIdentity(authority.KeyID) {
			return nil, fmt.Errorf("snapshot keyring contains invalid keyId")
		}
		if _, duplicate := result[authority.KeyID]; duplicate {
			return nil, fmt.Errorf("snapshot keyring contains duplicate keyId %q", authority.KeyID)
		}
		publicKey, err := decodePublicKey(authority.PublicKey)
		if err != nil {
			return nil, fmt.Errorf("snapshot keyring key %q: %w", authority.KeyID, err)
		}
		result[authority.KeyID] = publicKey
	}
	return result, nil
}

func validateCurrentSnapshot(snapshot CurrentSnapshot) error {
	if !isCommitSHA(snapshot.CommitSHA) ||
		!isSHA256(snapshot.ContractGraphSourceHash) ||
		!isDigest(snapshot.CandidateDigest) ||
		!isDigest(snapshot.ReleaseDigest) {
		return fmt.Errorf("current snapshot identity and candidate/release digests are required")
	}
	deployments := []readiness.DeploymentBinding{
		snapshot.Deployments.Alpha,
		snapshot.Deployments.Beta,
		snapshot.Deployments.Gamma,
		snapshot.Deployments.Prod,
	}
	for _, deployment := range deployments {
		if !validIdentity(deployment.DeploymentTarget) ||
			!validIdentity(deployment.BaselineID) ||
			!isDigest(deployment.PackageDigest) ||
			!isDigest(deployment.ConfigurationDigest) ||
			!isSHA256(deployment.CandidateManifestSHA256) {
			return fmt.Errorf("current snapshot requires one complete package-bound deployment per environment")
		}
	}
	for _, deployment := range deployments[1:] {
		if deployment.PackageDigest != deployments[0].PackageDigest ||
			deployment.CandidateManifestSHA256 != deployments[0].CandidateManifestSHA256 {
			return fmt.Errorf("current snapshot environments must bind one candidate package and manifest")
		}
	}
	return nil
}
