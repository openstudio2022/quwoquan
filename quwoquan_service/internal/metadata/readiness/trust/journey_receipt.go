package trust

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"path/filepath"
	"strings"

	"quwoquan_service/internal/metadata/readiness"
)

// SignedJourneyReceiptResolver is the production Journey attestation
// boundary. Journey receipts use their own signature domain and cannot be
// substituted with otherwise-valid object readiness receipts.
type SignedJourneyReceiptResolver struct {
	receiptRoot  string
	evidenceRoot string
	runners      map[string]runnerKey
	schemas      *readiness.WireSchemas
}

func NewSignedJourneyReceiptResolver(
	receiptRoot string,
	evidenceRoot string,
	runnerKeyringBytes []byte,
	schemas *readiness.WireSchemas,
) (*SignedJourneyReceiptResolver, error) {
	if schemas == nil {
		return nil, fmt.Errorf("Journey readiness receipt schema authority is required")
	}
	resolvedReceiptRoot, err := resolveDirectoryRoot(receiptRoot, "Journey receipt")
	if err != nil {
		return nil, err
	}
	resolvedEvidenceRoot, err := resolveDirectoryRoot(evidenceRoot, "Journey evidence")
	if err != nil {
		return nil, err
	}
	runners, err := decodeRunnerKeyring(runnerKeyringBytes)
	if err != nil {
		return nil, err
	}
	return &SignedJourneyReceiptResolver{
		receiptRoot: resolvedReceiptRoot, evidenceRoot: resolvedEvidenceRoot,
		runners: runners, schemas: schemas,
	}, nil
}

func (resolver *SignedJourneyReceiptResolver) ResolveJourney(
	ctx context.Context,
	result readiness.JourneyReadinessCaseResult,
) (readiness.ResolvedJourneyReceipt, error) {
	if err := ctx.Err(); err != nil {
		return readiness.ResolvedJourneyReceipt{}, err
	}
	if resolver == nil {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"signed Journey receipt resolver is nil",
		)
	}
	relative, err := journeyReceiptRelativePath(result)
	if err != nil {
		return readiness.ResolvedJourneyReceipt{}, err
	}
	receiptBytes, err := readContainedRegularFile(
		resolver.receiptRoot, relative, maxReceiptBytes,
	)
	if err != nil {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf("read Journey receipt: %w", err)
	}
	receipt, _, err := resolver.schemas.DecodeJourneyReceipt(bytes.NewReader(receiptBytes))
	if err != nil {
		return readiness.ResolvedJourneyReceipt{}, err
	}
	authority, trusted := resolver.runners[receipt.Binding.RunnerIdentity]
	if !trusted {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"Journey receipt runnerIdentity is not trusted",
		)
	}
	if !journeyBindingMatchesResult(receipt.Binding, result) {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"signed Journey receipt binding does not match result",
		)
	}
	signatureBytes, err := readContainedRegularFile(
		resolver.receiptRoot, relative+".sig.json", maxSignatureBytes,
	)
	if err != nil {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"read Journey receipt signature: %w", err,
		)
	}
	var signature DetachedReceiptSignature
	if err := decodeStrict(
		signatureBytes, &signature, "detached Journey receipt signature",
	); err != nil {
		return readiness.ResolvedJourneyReceipt{}, err
	}
	if signature.KeyID != authority.keyID {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"detached Journey receipt signature identity is invalid",
		)
	}
	decodedSignature, err := decodeSignature(signature.Signature)
	if err != nil {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"detached Journey receipt signature: %w", err,
		)
	}
	if !ed25519.Verify(
		authority.publicKey,
		JourneyReceiptSigningMessage(receiptBytes),
		decodedSignature,
	) {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"detached Journey receipt signature is invalid",
		)
	}
	evidenceRelative := filepath.ToSlash(
		filepath.Join("sha256", receipt.EvidenceSHA256),
	)
	evidence, err := readContainedRegularFile(
		resolver.evidenceRoot, evidenceRelative, maxEvidenceBytes,
	)
	if err != nil {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"read content-addressed Journey evidence: %w", err,
		)
	}
	if len(evidence) == 0 {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"content-addressed Journey evidence is empty",
		)
	}
	digest := sha256.Sum256(evidence)
	if hex.EncodeToString(digest[:]) != receipt.EvidenceSHA256 {
		return readiness.ResolvedJourneyReceipt{}, fmt.Errorf(
			"content-addressed Journey evidence digest mismatch",
		)
	}
	return readiness.ResolvedJourneyReceipt{
		Bytes: receiptBytes, Binding: receipt.Binding, Trusted: true,
	}, nil
}

func journeyReceiptRelativePath(
	result readiness.JourneyReadinessCaseResult,
) (string, error) {
	hasArtifact := strings.TrimSpace(result.ArtifactPath) != ""
	hasReference := strings.TrimSpace(result.ReceiptRef) != ""
	if hasArtifact == hasReference {
		return "", fmt.Errorf("exactly one artifactPath or receiptRef is required")
	}
	if hasArtifact {
		if err := validateRelativePath(result.ArtifactPath); err != nil {
			return "", fmt.Errorf("artifactPath: %w", err)
		}
		return result.ArtifactPath, nil
	}
	if err := validateRelativePath(result.ReceiptRef); err != nil {
		return "", fmt.Errorf("receiptRef: %w", err)
	}
	return filepath.ToSlash(
		filepath.Join("refs", result.ReceiptRef+".json"),
	), nil
}

func journeyBindingMatchesResult(
	binding readiness.JourneyReceiptBinding,
	result readiness.JourneyReadinessCaseResult,
) bool {
	return binding.JourneyID == result.JourneyID &&
		binding.SpecRef == result.SpecRef &&
		binding.CaseID == result.CaseID &&
		binding.Producer == result.Producer &&
		binding.Layer == result.Layer &&
		binding.Status == result.Status &&
		binding.Target == result.Target &&
		binding.CommitSHA == result.CommitSHA &&
		binding.ContractGraphSourceHash == result.ContractGraphSourceHash &&
		binding.DeploymentTarget == result.DeploymentTarget &&
		binding.BaselineID == result.BaselineID &&
		binding.PackageDigest == result.PackageDigest &&
		binding.ConfigurationDigest == result.ConfigurationDigest &&
		binding.CandidateManifestSHA256 == result.CandidateManifestSHA256 &&
		binding.CandidateDigest == result.CandidateDigest &&
		binding.ReleaseDigest == result.ReleaseDigest &&
		binding.Environment == result.Environment &&
		binding.Platform == result.Platform &&
		binding.DeviceClass == result.DeviceClass &&
		binding.Provider == result.Provider &&
		binding.StartedAt.Equal(result.StartedAt) &&
		binding.CompletedAt.Equal(result.CompletedAt) &&
		binding.RunnerIdentity == result.RunnerIdentity
}
