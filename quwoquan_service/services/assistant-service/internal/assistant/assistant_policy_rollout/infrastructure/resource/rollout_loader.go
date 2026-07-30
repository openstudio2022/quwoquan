// Package resource loads rollout artifacts that are explicitly supplied to
// the policy publisher. Rollouts are never inferred from a release artifact.
package resource

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
)

const RolloutArtifactSchema = "assistant.policy_rollout"

var ErrInvalidArtifact = errors.New("assistant policy rollout artifact is invalid")

type RolloutArtifact struct {
	Schema            string                   `json:"schema"`
	CommandID         string                   `json:"commandId"`
	PolicyID          string                   `json:"policyId"`
	ExpectedRevision  int                      `json:"expectedRevision"`
	ActivatedBy       string                   `json:"activatedBy"`
	BucketDefinitions []model.BucketDefinition `json:"bucketDefinitions"`
	Assignments       []model.CohortAssignment `json:"assignments"`
}

func DecodeRolloutArtifact(reader io.Reader) (RolloutArtifact, error) {
	if reader == nil {
		return RolloutArtifact{}, ErrInvalidArtifact
	}
	var artifact RolloutArtifact
	decoder := json.NewDecoder(io.LimitReader(reader, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&artifact); err != nil {
		return RolloutArtifact{}, fmt.Errorf("%w: decode: %v", ErrInvalidArtifact, err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return RolloutArtifact{}, fmt.Errorf(
				"%w: artifact must contain one JSON value",
				ErrInvalidArtifact,
			)
		}
		return RolloutArtifact{}, fmt.Errorf("%w: trailing content: %v", ErrInvalidArtifact, err)
	}
	if artifact.Schema != RolloutArtifactSchema ||
		strings.TrimSpace(artifact.PolicyID) == "" ||
		artifact.ExpectedRevision < 0 {
		return RolloutArtifact{}, ErrInvalidArtifact
	}
	if !strings.HasPrefix(
		artifact.CommandID,
		"policy-rollout:"+strings.TrimSpace(artifact.PolicyID)+":",
	) {
		return RolloutArtifact{}, ErrInvalidArtifact
	}
	current := (*model.Rollout)(nil)
	if artifact.ExpectedRevision > 0 {
		current = &model.Rollout{
			PolicyID: artifact.PolicyID,
			Revision: artifact.ExpectedRevision,
		}
	}
	if _, err := model.Activate(
		current,
		artifact.PolicyID,
		artifact.ExpectedRevision,
		artifact.BucketDefinitions,
		artifact.Assignments,
		artifact.ActivatedBy,
		time.Unix(0, 0),
	); err != nil {
		return RolloutArtifact{}, fmt.Errorf("%w: %v", ErrInvalidArtifact, err)
	}
	return artifact, nil
}
