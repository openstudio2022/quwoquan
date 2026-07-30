// Package resource loads immutable AssistantPolicyRelease artifacts shipped
// with the service image. It never discovers policies from a working tree or
// accepts paths outside the configured resource root.
package resource

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
)

const ReleaseArtifactSchema = "assistant.policy_release"

var ErrInvalidArtifact = errors.New("assistant policy release artifact is invalid")

type ReleaseArtifact struct {
	Schema    string        `json:"schema"`
	CommandID string        `json:"commandId"`
	Release   model.Release `json:"release"`
}

func LoadReleaseArtifact(
	resourceRoot string,
	reference string,
) (ReleaseArtifact, error) {
	path, err := ResolveArtifactPath(resourceRoot, reference)
	if err != nil {
		return ReleaseArtifact{}, err
	}
	file, err := os.Open(path)
	if err != nil {
		return ReleaseArtifact{}, fmt.Errorf("%w: open: %v", ErrInvalidArtifact, err)
	}
	defer file.Close()

	var artifact ReleaseArtifact
	decoder := json.NewDecoder(io.LimitReader(file, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&artifact); err != nil {
		return ReleaseArtifact{}, fmt.Errorf("%w: decode: %v", ErrInvalidArtifact, err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return ReleaseArtifact{}, fmt.Errorf(
				"%w: artifact must contain one JSON value",
				ErrInvalidArtifact,
			)
		}
		return ReleaseArtifact{}, fmt.Errorf("%w: trailing content: %v", ErrInvalidArtifact, err)
	}
	if artifact.Schema != ReleaseArtifactSchema ||
		artifact.Release.AggregateVersion != 0 ||
		!artifact.Release.StagedAt.IsZero() {
		return ReleaseArtifact{}, ErrInvalidArtifact
	}
	expectedCommandID := "policy-release:" +
		strings.TrimSpace(artifact.Release.PolicyID) + ":" +
		strings.TrimSpace(artifact.Release.ReleaseDigest)
	if artifact.CommandID != expectedCommandID {
		return ReleaseArtifact{}, ErrInvalidArtifact
	}
	digest, err := model.Digest(artifact.Release)
	if err != nil {
		return ReleaseArtifact{}, fmt.Errorf("%w: %v", ErrInvalidArtifact, err)
	}
	if digest != artifact.Release.ReleaseDigest {
		return ReleaseArtifact{}, fmt.Errorf("%w: release digest mismatch", ErrInvalidArtifact)
	}
	return artifact, nil
}

// ResolveArtifactPath returns an existing artifact below resourceRoot.
// Composition roots use it before passing sibling policy artifacts to their
// object-owned decoders, keeping path containment out of sibling adapters.
func ResolveArtifactPath(resourceRoot string, reference string) (string, error) {
	resourceRoot = strings.TrimSpace(resourceRoot)
	reference = strings.TrimSpace(reference)
	if resourceRoot == "" || reference == "" || filepath.IsAbs(reference) {
		return "", ErrInvalidArtifact
	}
	root, err := filepath.Abs(filepath.Clean(resourceRoot))
	if err != nil {
		return "", fmt.Errorf("%w: resolve resource root: %v", ErrInvalidArtifact, err)
	}
	candidate := filepath.Join(root, filepath.Clean(reference))
	relative, err := filepath.Rel(root, candidate)
	if err != nil || relative == "." || relative == ".." ||
		strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return "", ErrInvalidArtifact
	}
	resolvedRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", fmt.Errorf("%w: resolve resource root symlink: %v", ErrInvalidArtifact, err)
	}
	resolvedCandidate, err := filepath.EvalSymlinks(candidate)
	if err != nil {
		return "", fmt.Errorf("%w: resolve artifact symlink: %v", ErrInvalidArtifact, err)
	}
	resolvedRelative, err := filepath.Rel(resolvedRoot, resolvedCandidate)
	if err != nil || resolvedRelative == ".." ||
		strings.HasPrefix(resolvedRelative, ".."+string(filepath.Separator)) {
		return "", ErrInvalidArtifact
	}
	return resolvedCandidate, nil
}
