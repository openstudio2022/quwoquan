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

type JourneyReceiptResolver interface {
	ResolveJourney(context.Context, JourneyReadinessCaseResult) (ResolvedJourneyReceipt, error)
}

type JourneyReceiptAttestationVerifier interface {
	VerifyJourney(
		context.Context,
		JourneyReadinessCaseResult,
		ResolvedJourneyReceipt,
	) error
}

// VerifiedJourneyReceiptResolver is the trust boundary that turns resolved
// bytes into a trusted environment/device/Provider receipt. A file resolver by
// itself can never promote a Journey result.
type VerifiedJourneyReceiptResolver struct {
	Source   JourneyReceiptResolver
	Verifier JourneyReceiptAttestationVerifier
}

func (resolver VerifiedJourneyReceiptResolver) ResolveJourney(
	ctx context.Context,
	result JourneyReadinessCaseResult,
) (ResolvedJourneyReceipt, error) {
	if resolver.Source == nil || resolver.Verifier == nil {
		return ResolvedJourneyReceipt{}, fmt.Errorf("journey receipt source and attestation verifier are required")
	}
	receipt, err := resolver.Source.ResolveJourney(ctx, result)
	if err != nil {
		return ResolvedJourneyReceipt{}, err
	}
	receipt.Trusted = false
	if err := resolver.Verifier.VerifyJourney(ctx, result, receipt); err != nil {
		return ResolvedJourneyReceipt{}, fmt.Errorf("verify journey receipt attestation: %w", err)
	}
	receipt.Trusted = true
	return receipt, nil
}

type ResolvedJourneyReceipt struct {
	Bytes   []byte
	Binding JourneyReceiptBinding
	Trusted bool
}

func DecodeJourneyReceipt(reader io.Reader) (JourneyReadinessReceipt, error) {
	data, err := io.ReadAll(io.LimitReader(reader, maxReceiptDocumentBytes+1))
	if err != nil {
		return JourneyReadinessReceipt{}, fmt.Errorf("read journey readiness receipt: %w", err)
	}
	if len(data) == 0 || len(data) > maxReceiptDocumentBytes {
		return JourneyReadinessReceipt{}, fmt.Errorf("journey readiness receipt size is invalid")
	}
	return decodeJourneyReceiptBytes(data)
}

func decodeJourneyReceiptBytes(data []byte) (JourneyReadinessReceipt, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var receipt JourneyReadinessReceipt
	if err := decoder.Decode(&receipt); err != nil {
		return JourneyReadinessReceipt{}, fmt.Errorf("decode journey readiness receipt: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return JourneyReadinessReceipt{}, fmt.Errorf("decode journey readiness receipt: trailing JSON document")
		}
		return JourneyReadinessReceipt{}, fmt.Errorf("decode journey readiness receipt trailing content: %w", err)
	}
	if !isSHA256(receipt.EvidenceSHA256) {
		return JourneyReadinessReceipt{}, fmt.Errorf("journey readiness receipt identity is invalid")
	}
	return receipt, nil
}

// FileJourneyReceiptResolver provides contained byte resolution only. The
// returned receipt remains untrusted until a separate attestation verifier has
// checked its runner, physical device, environment and Provider evidence.
type FileJourneyReceiptResolver struct {
	Root string
}

func (resolver FileJourneyReceiptResolver) ResolveJourney(
	_ context.Context,
	result JourneyReadinessCaseResult,
) (ResolvedJourneyReceipt, error) {
	if strings.TrimSpace(result.ArtifactPath) == "" || strings.TrimSpace(result.ReceiptRef) != "" {
		return ResolvedJourneyReceipt{}, fmt.Errorf("file journey receipt resolver requires artifactPath only")
	}
	root, err := filepath.Abs(resolver.Root)
	if err != nil {
		return ResolvedJourneyReceipt{}, fmt.Errorf("resolve journey receipt root: %w", err)
	}
	root, err = filepath.EvalSymlinks(root)
	if err != nil {
		return ResolvedJourneyReceipt{}, fmt.Errorf("resolve journey receipt root symlinks: %w", err)
	}
	candidate := result.ArtifactPath
	if !filepath.IsAbs(candidate) {
		candidate = filepath.Join(root, candidate)
	}
	candidate, err = filepath.EvalSymlinks(candidate)
	if err != nil {
		return ResolvedJourneyReceipt{}, fmt.Errorf("resolve journey receipt artifact: %w", err)
	}
	relative, err := filepath.Rel(root, candidate)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return ResolvedJourneyReceipt{}, fmt.Errorf("journey receipt artifact escapes approved root")
	}
	data, err := os.ReadFile(candidate)
	if err != nil {
		return ResolvedJourneyReceipt{}, fmt.Errorf("read journey receipt artifact: %w", err)
	}
	receipt, err := DecodeJourneyReceipt(bytes.NewReader(data))
	if err != nil {
		return ResolvedJourneyReceipt{}, err
	}
	return ResolvedJourneyReceipt{Bytes: data, Binding: receipt.Binding, Trusted: false}, nil
}
