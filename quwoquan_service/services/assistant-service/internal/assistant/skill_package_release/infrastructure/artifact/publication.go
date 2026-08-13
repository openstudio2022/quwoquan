package artifact

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

type PublicationArtifact struct {
	CommandID        string               `json:"commandId"`
	ExpectedRevision int                  `json:"expectedRevision"`
	ActivatedBy      string               `json:"activatedBy"`
	Release          packagemodel.Release `json:"release"`
	// EvaluationReceipt 是激活的必备输入:证明轨迹回放评测在 exact package
	// digest 与 exact replay corpus asset digest 上通过。
	EvaluationReceipt packagemodel.EvaluationReceipt `json:"evaluationReceipt"`
}

func (artifact PublicationArtifact) Validate() error {
	if strings.TrimSpace(artifact.CommandID) == "" ||
		artifact.ExpectedRevision < 0 ||
		strings.TrimSpace(artifact.ActivatedBy) == "" {
		return fmt.Errorf("Skill package publication identity is invalid")
	}
	normalized, err := packagemodel.Normalize(artifact.Release)
	if err != nil {
		return fmt.Errorf("Skill package release descriptor is invalid: %w", err)
	}
	digest, err := packagemodel.Digest(normalized)
	if err != nil || digest != normalized.ReleaseDigest {
		return fmt.Errorf("Skill package release digest is invalid")
	}
	if err := packagemodel.ValidateEvaluationReceipt(
		artifact.EvaluationReceipt,
		normalized,
	); err != nil {
		return fmt.Errorf("Skill package publication evaluation receipt is invalid: %w", err)
	}
	return nil
}

func DecodePublicationArtifact(reader io.Reader) (PublicationArtifact, error) {
	if reader == nil {
		return PublicationArtifact{}, fmt.Errorf("Skill package publication reader is required")
	}
	decoder := json.NewDecoder(io.LimitReader(reader, 4<<20))
	decoder.DisallowUnknownFields()
	var artifact PublicationArtifact
	if err := decoder.Decode(&artifact); err != nil {
		return PublicationArtifact{}, fmt.Errorf("decode Skill package publication: %w", err)
	}
	if err := artifact.Validate(); err != nil {
		return PublicationArtifact{}, err
	}
	return artifact, nil
}

func LoadPublicationArtifact(
	root string,
	reference string,
) (PublicationArtifact, error) {
	root = strings.TrimSpace(root)
	reference = strings.TrimSpace(reference)
	if root == "" || reference == "" || filepath.IsAbs(reference) ||
		reference != filepath.ToSlash(filepath.Clean(reference)) ||
		reference == ".." || strings.HasPrefix(reference, "../") {
		return PublicationArtifact{}, fmt.Errorf("Skill package publication reference is invalid")
	}
	absoluteRoot, err := filepath.Abs(root)
	if err != nil {
		return PublicationArtifact{}, err
	}
	resolvedRoot, err := filepath.EvalSymlinks(absoluteRoot)
	if err != nil {
		return PublicationArtifact{}, err
	}
	path := filepath.Join(resolvedRoot, filepath.FromSlash(reference))
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return PublicationArtifact{}, err
	}
	relative, err := filepath.Rel(resolvedRoot, resolved)
	if err != nil || relative == ".." ||
		strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return PublicationArtifact{}, fmt.Errorf("Skill package publication escapes root")
	}
	file, err := os.Open(resolved)
	if err != nil {
		return PublicationArtifact{}, err
	}
	defer file.Close()
	return DecodePublicationArtifact(file)
}
