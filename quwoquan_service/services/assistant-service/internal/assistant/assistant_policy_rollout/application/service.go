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
		releaseDigest string,
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
	ReleaseDigest         string
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
			assignment.ReleaseDigest,
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

// ResolveSkillCandidates 返回该策略在此人群下真正能服务的技能集合。技能选择必须在这个集合
// 内进行，否则选出的技能没有对应模板，运行会静默回落到默认模板并丢掉用户意图。
func (service *Service) ResolveSkillCandidates(
	ctx context.Context,
	policyID string,
	personaID string,
) ([]string, error) {
	active, err := service.resolveActiveRelease(ctx, policyID, personaID)
	if err != nil {
		return nil, err
	}
	release := active.Release
	seen := map[string]bool{}
	candidates := []string{}
	appendCandidate := func(skillID string) {
		skillID = strings.TrimSpace(skillID)
		if skillID == "" || seen[skillID] {
			return
		}
		seen[skillID] = true
		candidates = append(candidates, skillID)
	}
	for _, rule := range release.RoutingRules {
		appendCandidate(rule.SkillID)
	}
	for _, template := range release.Templates {
		appendCandidate(template.SkillID)
	}
	return candidates, nil
}

func (service *Service) ResolveFrozenSelection(
	ctx context.Context,
	policyID string,
	personaID string,
	skillID string,
	domainID string,
) (FrozenSelection, error) {
	active, err := service.resolveActiveRelease(ctx, policyID, personaID)
	if err != nil {
		return FrozenSelection{}, err
	}
	release := active.Release
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
		PolicyID:              strings.TrimSpace(policyID),
		ReleaseDigest:         active.ReleaseDigest,
		Cohort:                active.Cohort,
		RolloutRevision:       active.RolloutRevision,
		RuleID:                ruleID,
		Template:              selected,
		LearningContextPolicy: release.LearningContextPolicy,
	}, nil
}

type activeRelease struct {
	Release         releasemodel.Release
	Cohort          string
	ReleaseDigest   string
	RolloutRevision int
}

// resolveActiveRelease 把"人群分桶 -> 发布摘要 -> 发布内容"这一段解析收在一处，保证冻结选择
// 与技能候选集合读到同一份发布。
func (service *Service) resolveActiveRelease(
	ctx context.Context,
	policyID string,
	personaID string,
) (activeRelease, error) {
	policyID = strings.TrimSpace(policyID)
	personaID = strings.TrimSpace(personaID)
	if policyID == "" || personaID == "" ||
		service == nil || service.releases == nil {
		return activeRelease{}, model.ErrInvalidArgument
	}
	rollout, found, err := service.GetActive(ctx, policyID)
	if err != nil {
		return activeRelease{}, err
	}
	if !found {
		return activeRelease{}, model.ErrRolloutNotFound
	}
	buckets := make([]runtimeexperiments.BucketDef, 0, len(rollout.BucketDefinitions))
	for _, bucket := range rollout.BucketDefinitions {
		buckets = append(buckets, runtimeexperiments.BucketDef{
			Name:              bucket.Cohort,
			WeightBasisPoints: bucket.WeightBasisPoints,
		})
	}
	cohort, err := runtimeexperiments.AssignBucket(policyID, personaID, buckets)
	if err != nil {
		return activeRelease{}, fmt.Errorf(
			"%w: invalid rollout bucket policy: %v",
			model.ErrInvalidArgument,
			err,
		)
	}
	releaseDigest := ""
	for _, assignment := range rollout.Assignments {
		if assignment.Cohort == cohort {
			releaseDigest = assignment.ReleaseDigest
			break
		}
	}
	if releaseDigest == "" {
		return activeRelease{}, fmt.Errorf(
			"%w: cohort %q has no release mapping",
			model.ErrInvalidArgument,
			cohort,
		)
	}
	release, found, err := service.releases.Get(ctx, policyID, releaseDigest)
	if err != nil {
		return activeRelease{}, err
	}
	if !found {
		return activeRelease{}, model.ErrReleaseNotFound
	}
	return activeRelease{
		Release:         release,
		Cohort:          cohort,
		ReleaseDigest:   releaseDigest,
		RolloutRevision: rollout.Revision,
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
