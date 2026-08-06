package readiness

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

type ReceiptResolver interface {
	Resolve(context.Context, ReadinessCaseResult) (ResolvedReceipt, error)
}

// ReceiptAttestationVerifier is implemented by the environment/release trust
// boundary. It verifies the runner identity, provider/device binding and the
// separately governed evidence bytes (for example a signed external Provider
// receipt) before commercial closure may consume the manifest.
type ReceiptAttestationVerifier interface {
	Verify(context.Context, ReadinessCaseResult, ResolvedReceipt) error
}

// VerifiedReceiptResolver composes byte resolution with independent
// attestation verification. The source resolver never gets to self-promote a
// local file by path existence alone.
type VerifiedReceiptResolver struct {
	Source   ReceiptResolver
	Verifier ReceiptAttestationVerifier
}

func (resolver VerifiedReceiptResolver) Resolve(
	ctx context.Context,
	result ReadinessCaseResult,
) (ResolvedReceipt, error) {
	if resolver.Source == nil || resolver.Verifier == nil {
		return ResolvedReceipt{}, fmt.Errorf("receipt source and attestation verifier are required")
	}
	receipt, err := resolver.Source.Resolve(ctx, result)
	if err != nil {
		return ResolvedReceipt{}, err
	}
	receipt.Trusted = false
	if err := resolver.Verifier.Verify(ctx, result, receipt); err != nil {
		return ResolvedReceipt{}, fmt.Errorf("verify receipt attestation: %w", err)
	}
	receipt.Trusted = true
	return receipt, nil
}

type ResolvedReceipt struct {
	Bytes   []byte
	Binding ReceiptBinding
	// Trusted is set only by a resolver that has independently verified the
	// runner/environment attestation and the separately governed evidence
	// bytes. Reading a JSON file from disk alone is never that verification.
	Trusted bool
}

func DecodeReceipt(reader io.Reader) (ReadinessReceipt, error) {
	data, err := io.ReadAll(io.LimitReader(reader, maxReceiptDocumentBytes+1))
	if err != nil {
		return ReadinessReceipt{}, fmt.Errorf("read readiness receipt: %w", err)
	}
	if len(data) == 0 || len(data) > maxReceiptDocumentBytes {
		return ReadinessReceipt{}, fmt.Errorf("readiness receipt size is invalid")
	}
	return decodeReceiptBytes(data)
}

func decodeReceiptBytes(data []byte) (ReadinessReceipt, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var receipt ReadinessReceipt
	if err := decoder.Decode(&receipt); err != nil {
		return ReadinessReceipt{}, fmt.Errorf("decode readiness receipt: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return ReadinessReceipt{}, fmt.Errorf("decode readiness receipt: trailing JSON document")
		}
		return ReadinessReceipt{}, fmt.Errorf("decode readiness receipt trailing content: %w", err)
	}
	if !isSHA256(receipt.EvidenceSHA256) {
		return ReadinessReceipt{}, fmt.Errorf("readiness receipt identity is invalid")
	}
	return receipt, nil
}

// FileReceiptResolver reads only artifactPath values contained by Root. It
// resolves symlinks before the containment check so a disposable runner path
// cannot escape into credentials or unrelated repository files. It deliberately
// returns Trusted=false: a local manifest is useful input for a higher-level
// signature/evidence verifier, but cannot by itself close commercial readiness.
type FileReceiptResolver struct {
	Root string
}

func (resolver FileReceiptResolver) Resolve(
	_ context.Context,
	result ReadinessCaseResult,
) (ResolvedReceipt, error) {
	if strings.TrimSpace(result.ArtifactPath) == "" ||
		strings.TrimSpace(result.ReceiptRef) != "" {
		return ResolvedReceipt{}, fmt.Errorf("file receipt resolver requires artifactPath only")
	}
	root, err := filepath.Abs(resolver.Root)
	if err != nil {
		return ResolvedReceipt{}, fmt.Errorf("resolve receipt root: %w", err)
	}
	root, err = filepath.EvalSymlinks(root)
	if err != nil {
		return ResolvedReceipt{}, fmt.Errorf("resolve receipt root symlinks: %w", err)
	}
	candidate := result.ArtifactPath
	if !filepath.IsAbs(candidate) {
		candidate = filepath.Join(root, candidate)
	}
	candidate, err = filepath.EvalSymlinks(candidate)
	if err != nil {
		return ResolvedReceipt{}, fmt.Errorf("resolve receipt artifact: %w", err)
	}
	relative, err := filepath.Rel(root, candidate)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return ResolvedReceipt{}, fmt.Errorf("receipt artifact escapes approved root")
	}
	data, err := os.ReadFile(candidate)
	if err != nil {
		return ResolvedReceipt{}, fmt.Errorf("read receipt artifact: %w", err)
	}
	receipt, err := DecodeReceipt(bytes.NewReader(data))
	if err != nil {
		return ResolvedReceipt{}, err
	}
	return ResolvedReceipt{Bytes: data, Binding: receipt.Binding, Trusted: false}, nil
}
