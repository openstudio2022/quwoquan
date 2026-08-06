package trust

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"quwoquan_service/internal/metadata/readiness"
)

const (
	maxReceiptBytes   = 1 << 20
	maxSignatureBytes = 64 << 10
	maxEvidenceBytes  = 64 << 20
)

type runnerKey struct {
	keyID     string
	publicKey ed25519.PublicKey
}

// SignedReceiptResolver verifies, in order: contained regular receipt bytes,
// their runner-bound detached Ed25519 signature, and separately governed
// content-addressed evidence bytes. Only then does it return Trusted=true.
type SignedReceiptResolver struct {
	receiptRoot  string
	evidenceRoot string
	runners      map[string]runnerKey
	schemas      *readiness.WireSchemas
}

func NewSignedReceiptResolver(
	receiptRoot string,
	evidenceRoot string,
	runnerKeyringBytes []byte,
	schemas *readiness.WireSchemas,
) (*SignedReceiptResolver, error) {
	if schemas == nil {
		return nil, fmt.Errorf("readiness receipt schema authority is required")
	}
	resolvedReceiptRoot, err := resolveDirectoryRoot(receiptRoot, "receipt")
	if err != nil {
		return nil, err
	}
	resolvedEvidenceRoot, err := resolveDirectoryRoot(evidenceRoot, "evidence")
	if err != nil {
		return nil, err
	}
	runners, err := decodeRunnerKeyring(runnerKeyringBytes)
	if err != nil {
		return nil, err
	}
	return &SignedReceiptResolver{
		receiptRoot: resolvedReceiptRoot, evidenceRoot: resolvedEvidenceRoot,
		runners: runners, schemas: schemas,
	}, nil
}

func (resolver *SignedReceiptResolver) Resolve(
	ctx context.Context,
	result readiness.ReadinessCaseResult,
) (readiness.ResolvedReceipt, error) {
	if err := ctx.Err(); err != nil {
		return readiness.ResolvedReceipt{}, err
	}
	if resolver == nil {
		return readiness.ResolvedReceipt{}, fmt.Errorf("signed receipt resolver is nil")
	}
	relative, err := receiptRelativePath(result)
	if err != nil {
		return readiness.ResolvedReceipt{}, err
	}
	receiptBytes, err := readContainedRegularFile(resolver.receiptRoot, relative, maxReceiptBytes)
	if err != nil {
		return readiness.ResolvedReceipt{}, fmt.Errorf("read receipt: %w", err)
	}
	receipt, _, err := resolver.schemas.DecodeReceipt(bytes.NewReader(receiptBytes))
	if err != nil {
		return readiness.ResolvedReceipt{}, err
	}
	authority, trusted := resolver.runners[receipt.Binding.RunnerIdentity]
	if !trusted {
		return readiness.ResolvedReceipt{}, fmt.Errorf("receipt runnerIdentity is not trusted")
	}
	if receipt.Binding.ObjectID != result.ObjectID ||
		receipt.Binding.SpecRef != result.SpecRef ||
		receipt.Binding.CaseID != result.CaseID ||
		receipt.Binding.Producer != result.Producer ||
		receipt.Binding.Layer != result.Layer ||
		receipt.Binding.Status != result.Status ||
		receipt.Binding.Target != result.Target ||
		receipt.Binding.CommitSHA != result.CommitSHA ||
		receipt.Binding.ContractGraphSourceHash != result.ContractGraphSourceHash ||
		receipt.Binding.DeploymentTarget != result.DeploymentTarget ||
		receipt.Binding.BaselineID != result.BaselineID ||
		receipt.Binding.PackageDigest != result.PackageDigest ||
		receipt.Binding.ConfigurationDigest != result.ConfigurationDigest ||
		receipt.Binding.CandidateManifestSHA256 != result.CandidateManifestSHA256 ||
		receipt.Binding.CandidateDigest != result.CandidateDigest ||
		receipt.Binding.ReleaseDigest != result.ReleaseDigest ||
		receipt.Binding.RunnerIdentity != result.RunnerIdentity ||
		receipt.Binding.Environment != result.Environment ||
		receipt.Binding.Platform != result.Platform ||
		receipt.Binding.DeviceClass != result.DeviceClass ||
		receipt.Binding.Provider != result.Provider ||
		!receipt.Binding.StartedAt.Equal(result.StartedAt) ||
		!receipt.Binding.CompletedAt.Equal(result.CompletedAt) {
		return readiness.ResolvedReceipt{}, fmt.Errorf("signed receipt execution binding does not match result")
	}
	signatureBytes, err := readContainedRegularFile(
		resolver.receiptRoot, relative+".sig.json", maxSignatureBytes,
	)
	if err != nil {
		return readiness.ResolvedReceipt{}, fmt.Errorf("read receipt signature: %w", err)
	}
	var signature DetachedReceiptSignature
	if err := decodeStrict(signatureBytes, &signature, "detached receipt signature"); err != nil {
		return readiness.ResolvedReceipt{}, err
	}
	if signature.KeyID != authority.keyID {
		return readiness.ResolvedReceipt{}, fmt.Errorf("detached receipt signature identity is invalid")
	}
	decodedSignature, err := decodeSignature(signature.Signature)
	if err != nil {
		return readiness.ResolvedReceipt{}, fmt.Errorf("detached receipt signature: %w", err)
	}
	if !ed25519.Verify(authority.publicKey, ReceiptSigningMessage(receiptBytes), decodedSignature) {
		return readiness.ResolvedReceipt{}, fmt.Errorf("detached receipt signature is invalid")
	}
	evidenceRelative := filepath.ToSlash(filepath.Join("sha256", receipt.EvidenceSHA256))
	evidence, err := readContainedRegularFile(
		resolver.evidenceRoot, evidenceRelative, maxEvidenceBytes,
	)
	if err != nil {
		return readiness.ResolvedReceipt{}, fmt.Errorf("read content-addressed evidence: %w", err)
	}
	if len(evidence) == 0 {
		return readiness.ResolvedReceipt{}, fmt.Errorf("content-addressed evidence is empty")
	}
	digest := sha256.Sum256(evidence)
	if hex.EncodeToString(digest[:]) != receipt.EvidenceSHA256 {
		return readiness.ResolvedReceipt{}, fmt.Errorf("content-addressed evidence digest mismatch")
	}
	return readiness.ResolvedReceipt{
		Bytes: receiptBytes, Binding: receipt.Binding, Trusted: true,
	}, nil
}

func decodeRunnerKeyring(data []byte) (map[string]runnerKey, error) {
	var keyring RunnerKeyring
	if err := decodeStrict(data, &keyring, "runner keyring"); err != nil {
		return nil, err
	}
	if len(keyring.Runners) == 0 {
		return nil, fmt.Errorf("runner keyring identity is invalid")
	}
	result := make(map[string]runnerKey, len(keyring.Runners))
	keyOwners := map[string]string{}
	for _, runner := range keyring.Runners {
		if !validIdentity(runner.RunnerIdentity) || !validIdentity(runner.KeyID) {
			return nil, fmt.Errorf("runner keyring contains invalid identity")
		}
		if _, duplicate := result[runner.RunnerIdentity]; duplicate {
			return nil, fmt.Errorf("runner keyring contains duplicate runnerIdentity %q", runner.RunnerIdentity)
		}
		if owner, duplicate := keyOwners[runner.KeyID]; duplicate && owner != runner.RunnerIdentity {
			return nil, fmt.Errorf("runner keyring keyId %q is assigned to multiple runners", runner.KeyID)
		}
		publicKey, err := decodePublicKey(runner.PublicKey)
		if err != nil {
			return nil, fmt.Errorf("runner keyring runner %q: %w", runner.RunnerIdentity, err)
		}
		result[runner.RunnerIdentity] = runnerKey{keyID: runner.KeyID, publicKey: publicKey}
		keyOwners[runner.KeyID] = runner.RunnerIdentity
	}
	return result, nil
}

func receiptRelativePath(result readiness.ReadinessCaseResult) (string, error) {
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
	return filepath.ToSlash(filepath.Join("refs", result.ReceiptRef+".json")), nil
}

func resolveDirectoryRoot(value, name string) (string, error) {
	if strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("%s root is required", name)
	}
	abs, err := filepath.Abs(value)
	if err != nil {
		return "", fmt.Errorf("resolve %s root: %w", name, err)
	}
	provided, err := os.Lstat(abs)
	if err != nil {
		return "", fmt.Errorf("inspect %s root: %w", name, err)
	}
	if provided.Mode()&os.ModeSymlink != 0 {
		return "", fmt.Errorf("%s root must not be a symlink", name)
	}
	real, err := filepath.EvalSymlinks(abs)
	if err != nil {
		return "", fmt.Errorf("resolve %s root symlinks: %w", name, err)
	}
	info, err := os.Stat(real)
	if err != nil || !info.IsDir() {
		return "", fmt.Errorf("%s root must be an existing directory", name)
	}
	return filepath.Clean(real), nil
}

func readContainedRegularFile(root, relative string, limit int64) ([]byte, error) {
	if err := validateRelativePath(relative); err != nil {
		return nil, err
	}
	type inspectedPath struct {
		path string
		info os.FileInfo
	}
	rootInfo, err := os.Lstat(root)
	if err != nil || rootInfo.Mode()&os.ModeSymlink != 0 || !rootInfo.IsDir() {
		return nil, fmt.Errorf("approved root is no longer a regular directory")
	}
	inspected := []inspectedPath{{path: root, info: rootInfo}}
	current := root
	parts := strings.Split(filepath.ToSlash(relative), "/")
	for index, part := range parts {
		current = filepath.Join(current, part)
		info, err := os.Lstat(current)
		if err != nil {
			return nil, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, fmt.Errorf("symlink is forbidden at %q", strings.Join(parts[:index+1], "/"))
		}
		if index < len(parts)-1 && !info.IsDir() {
			return nil, fmt.Errorf("path component is not a directory")
		}
		if index == len(parts)-1 && (!info.Mode().IsRegular() || info.Size() > limit) {
			return nil, fmt.Errorf("artifact must be a bounded regular file")
		}
		inspected = append(inspected, inspectedPath{path: current, info: info})
	}
	rel, err := filepath.Rel(root, current)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return nil, fmt.Errorf("artifact escapes approved root")
	}
	file, err := os.Open(current)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	openedInfo, err := file.Stat()
	if err != nil || !openedInfo.Mode().IsRegular() || openedInfo.Size() > limit ||
		!os.SameFile(inspected[len(inspected)-1].info, openedInfo) {
		return nil, fmt.Errorf("artifact changed while opening")
	}
	// Recheck every component after opening the final descriptor. This closes
	// the Lstat/open race without following a path again for the actual read.
	for _, item := range inspected {
		currentInfo, err := os.Lstat(item.path)
		if err != nil || currentInfo.Mode()&os.ModeSymlink != 0 ||
			!os.SameFile(item.info, currentInfo) {
			return nil, fmt.Errorf("artifact path changed while opening")
		}
	}
	data, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > limit {
		return nil, fmt.Errorf("artifact exceeds size limit")
	}
	return data, nil
}

func validateRelativePath(value string) error {
	if value == "" || len(value) > 512 || filepath.IsAbs(value) ||
		strings.Contains(value, "\\") || strings.Contains(value, ":") {
		return fmt.Errorf("path must be a bounded portable relative path")
	}
	for _, segment := range strings.Split(value, "/") {
		if segment == "" || segment == "." || segment == ".." {
			return fmt.Errorf("path contains a forbidden segment")
		}
		for _, current := range segment {
			if current >= 'a' && current <= 'z' || current >= 'A' && current <= 'Z' ||
				current >= '0' && current <= '9' || current == '.' || current == '_' || current == '-' {
				continue
			}
			return fmt.Errorf("path contains a forbidden character")
		}
	}
	return nil
}
