package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	runtimeexperiments "quwoquan_service/runtime/experiments"
	releasemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
)

const (
	EventActivated  = "AssistantPolicyRolloutActivated"
	EventRolledBack = "AssistantPolicyRolloutRolledBack"
)

type Store interface {
	Get(ctx context.Context, policyID string) (model.Rollout, bool, error)
	GetCommandResult(
		ctx context.Context,
		commandID string,
		commandDigest string,
		policyID string,
	) (model.Rollout, bool, error)
	Commit(
		ctx context.Context,
		commandID string,
		commandDigest string,
		expectedRevision int,
		next model.Rollout,
		eventType string,
	) (stored model.Rollout, replayed bool, err error)
}

type ReleaseReader interface {
	Get(
		ctx context.Context,
		policyID string,
		releaseVersion string,
	) (releasemodel.Release, bool, error)
}

type Service struct {
	store    Store
	releases ReleaseReader
	now      func() time.Time
}

type ActivateInput struct {
	PolicyID          string                   `json:"policyId"`
	ExpectedRevision  int                      `json:"revision"`
	BucketDefinitions []model.BucketDefinition `json:"bucketDefinitions"`
	Assignments       []model.CohortAssignment `json:"assignments"`
	ActivatedBy       string                   `json:"activatedBy"`
}

type RollbackInput struct {
	PolicyID         string `json:"policyId"`
	ExpectedRevision int    `json:"revision"`
	ActivatedBy      string `json:"activatedBy"`
}

type CommandResult struct {
	Rollout  model.Rollout `json:"rollout"`
	Replayed bool          `json:"replayed"`
}

type FrozenSelection struct {
	PolicyID              string
	ReleaseVersion        string
	Cohort                string
	RolloutRevision       int
	RuleID                string
	Template              releasemodel.Template
	LearningContextPolicy releasemodel.LearningContextPolicy
}

func NewService(
	store Store,
	releases ReleaseReader,
	now func() time.Time,
) *Service {
	if now == nil {
		now = time.Now
	}
	return &Service{store: store, releases: releases, now: now}
}

func (service *Service) Activate(
	ctx context.Context,
	commandID string,
	input ActivateInput,
) (CommandResult, error) {
	if service == nil || service.store == nil || service.releases == nil ||
		strings.TrimSpace(commandID) == "" {
		return CommandResult{}, model.ErrInvalidArgument
	}
	digest, err := commandDigest(input)
	if err != nil {
		return CommandResult{}, err
	}
	if stored, replayed, err := service.store.GetCommandResult(
		ctx,
		strings.TrimSpace(commandID),
		digest,
		strings.TrimSpace(input.PolicyID),
	); err != nil || replayed {
		return CommandResult{Rollout: stored, Replayed: replayed}, err
	}
	current, found, err := service.store.Get(ctx, strings.TrimSpace(input.PolicyID))
	if err != nil {
		return CommandResult{}, err
	}
	var currentPtr *model.Rollout
	if found {
		currentPtr = &current
	}
	next, err := model.Activate(
		currentPtr,
		input.PolicyID,
		input.ExpectedRevision,
		input.BucketDefinitions,
		input.Assignments,
		input.ActivatedBy,
		service.now(),
	)
	if err != nil {
		return CommandResult{}, err
	}
	for _, assignment := range next.Assignments {
		_, exists, readErr := service.releases.Get(
			ctx,
			next.PolicyID,
			assignment.ReleaseVersion,
		)
		if readErr != nil {
			return CommandResult{}, readErr
		}
		if !exists {
			return CommandResult{}, model.ErrReleaseNotFound
		}
	}
	stored, replayed, err := service.store.Commit(
		ctx,
		strings.TrimSpace(commandID),
		digest,
		input.ExpectedRevision,
		next,
		EventActivated,
	)
	if err != nil {
		return CommandResult{}, err
	}
	return CommandResult{Rollout: stored, Replayed: replayed}, nil
}

func (service *Service) Rollback(
	ctx context.Context,
	commandID string,
	input RollbackInput,
) (CommandResult, error) {
	if service == nil || service.store == nil ||
		strings.TrimSpace(commandID) == "" {
		return CommandResult{}, model.ErrInvalidArgument
	}
	digest, err := commandDigest(input)
	if err != nil {
		return CommandResult{}, err
	}
	if stored, replayed, err := service.store.GetCommandResult(
		ctx,
		strings.TrimSpace(commandID),
		digest,
		strings.TrimSpace(input.PolicyID),
	); err != nil || replayed {
		return CommandResult{Rollout: stored, Replayed: replayed}, err
	}
	current, found, err := service.store.Get(ctx, strings.TrimSpace(input.PolicyID))
	if err != nil {
		return CommandResult{}, err
	}
	if !found {
		return CommandResult{}, model.ErrRolloutNotFound
	}
	next, err := model.Rollback(
		current,
		input.ExpectedRevision,
		input.ActivatedBy,
		service.now(),
	)
	if err != nil {
		return CommandResult{}, err
	}
	stored, replayed, err := service.store.Commit(
		ctx,
		strings.TrimSpace(commandID),
		digest,
		input.ExpectedRevision,
		next,
		EventRolledBack,
	)
	if err != nil {
		return CommandResult{}, err
	}
	return CommandResult{Rollout: stored, Replayed: replayed}, nil
}

func (service *Service) GetActive(
	ctx context.Context,
	policyID string,
) (model.Rollout, bool, error) {
	if service == nil || service.store == nil {
		return model.Rollout{}, false, model.ErrStorageUnavailable
	}
	return service.store.Get(ctx, strings.TrimSpace(policyID))
}

func (service *Service) ResolveFrozenSelection(
	ctx context.Context,
	policyID string,
	personaID string,
	skillID string,
	domainID string,
) (FrozenSelection, error) {
	policyID = strings.TrimSpace(policyID)
	personaID = strings.TrimSpace(personaID)
	if policyID == "" || personaID == "" ||
		service == nil || service.releases == nil {
		return FrozenSelection{}, model.ErrInvalidArgument
	}
	rollout, found, err := service.GetActive(ctx, policyID)
	if err != nil {
		return FrozenSelection{}, err
	}
	if !found {
		return FrozenSelection{}, model.ErrRolloutNotFound
	}
	buckets := make([]runtimeexperiments.BucketDef, 0, len(rollout.BucketDefinitions))
	for _, bucket := range rollout.BucketDefinitions {
		buckets = append(buckets, runtimeexperiments.BucketDef{
			Name:              bucket.Cohort,
			WeightBasisPoints: bucket.WeightBasisPoints,
		})
	}
	cohort := runtimeexperiments.AssignBucket(policyID, personaID, buckets)
	releaseVersion := ""
	for _, assignment := range rollout.Assignments {
		if assignment.Cohort == cohort {
			releaseVersion = assignment.ReleaseVersion
			break
		}
	}
	if releaseVersion == "" {
		return FrozenSelection{}, fmt.Errorf(
			"%w: cohort %q has no release mapping",
			model.ErrInvalidArgument,
			cohort,
		)
	}
	release, found, err := service.releases.Get(ctx, policyID, releaseVersion)
	if err != nil {
		return FrozenSelection{}, err
	}
	if !found {
		return FrozenSelection{}, model.ErrReleaseNotFound
	}
	templateID := release.DefaultTemplateID
	ruleID := "default"
	skillID = strings.TrimSpace(skillID)
	domainID = strings.TrimSpace(domainID)
	for _, rule := range release.RoutingRules {
		if rule.SkillID != "" && rule.SkillID != skillID {
			continue
		}
		if rule.DomainID != "" && rule.DomainID != domainID {
			continue
		}
		templateID = rule.TemplateID
		ruleID = rule.RuleID
		break
	}
	var selected releasemodel.Template
	for _, template := range release.Templates {
		if template.TemplateID == templateID {
			selected = template
			break
		}
	}
	if selected.TemplateID == "" {
		return FrozenSelection{}, fmt.Errorf(
			"%w: template %q is absent",
			model.ErrInvalidArgument,
			templateID,
		)
	}
	return FrozenSelection{
		PolicyID:              policyID,
		ReleaseVersion:        releaseVersion,
		Cohort:                cohort,
		RolloutRevision:       rollout.Revision,
		RuleID:                ruleID,
		Template:              selected,
		LearningContextPolicy: release.LearningContextPolicy,
	}, nil
}

func commandDigest(input any) (string, error) {
	encoded, err := json.Marshal(input)
	if err != nil {
		return "", model.ErrInvalidArgument
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}
