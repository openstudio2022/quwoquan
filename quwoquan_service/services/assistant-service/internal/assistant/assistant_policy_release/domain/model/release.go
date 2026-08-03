package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"time"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

var (
	ErrInvalidArgument     = errors.New("assistant policy release is invalid")
	ErrDigestMismatch      = errors.New("assistant policy release digest mismatch")
	ErrIdempotencyConflict = errors.New("assistant policy release idempotency conflict")
	ErrStorageUnavailable  = errors.New("assistant policy release storage unavailable")
)

type Template struct {
	TemplateID      string   `json:"templateId" bson:"templateId"`
	SkillID         string   `json:"skillId" bson:"skillId"`
	DomainID        string   `json:"domainId" bson:"domainId"`
	PromptPolicy    string   `json:"promptPolicy" bson:"promptPolicy"`
	AllowedTools    []string `json:"allowedTools" bson:"allowedTools"`
	SearchIntensity string   `json:"searchIntensity" bson:"searchIntensity"`
}

type RoutingRule struct {
	RuleID     string `json:"ruleId" bson:"ruleId"`
	Priority   int    `json:"priority" bson:"priority"`
	DomainID   string `json:"domainId,omitempty" bson:"domainId,omitempty"`
	SkillID    string `json:"skillId,omitempty" bson:"skillId,omitempty"`
	TemplateID string `json:"templateId" bson:"templateId"`
}

type LearningContextPolicy struct {
	Enabled                  bool     `json:"enabled" bson:"enabled"`
	AllowedSignals           []string `json:"allowedSignals" bson:"allowedSignals"`
	AllowedMetricIDs         []string `json:"allowedMetricIds" bson:"allowedMetricIds"`
	AllowedReasonCodes       []string `json:"allowedReasonCodes" bson:"allowedReasonCodes"`
	MinimumFeedbackSamples   int      `json:"minimumFeedbackSamples" bson:"minimumFeedbackSamples"`
	WindowDays               int      `json:"windowDays" bson:"windowDays"`
	SnapshotTrainingEligible bool     `json:"snapshotTrainingEligible" bson:"snapshotTrainingEligible"`
}

type Release struct {
	PolicyID              string                `json:"policyId" bson:"policyId"`
	ReleaseDigest         string                `json:"releaseDigest" bson:"releaseDigest"`
	AggregateVersion      int                   `json:"aggregateVersion" bson:"aggregateVersion"`
	DefaultTemplateID     string                `json:"defaultTemplateId" bson:"defaultTemplateId"`
	Templates             []Template            `json:"templates" bson:"templates"`
	RoutingRules          []RoutingRule         `json:"routingRules" bson:"routingRules"`
	LearningContextPolicy LearningContextPolicy `json:"learningContextPolicy" bson:"learningContextPolicy"`
	StagedAt              time.Time             `json:"stagedAt" bson:"stagedAt"`
}

func Stage(input Release, now time.Time) (Release, error) {
	normalized, err := normalize(input, true)
	if err != nil {
		return Release{}, err
	}
	digest, err := Digest(normalized)
	if err != nil {
		return Release{}, err
	}
	if normalized.ReleaseDigest != digest {
		return Release{}, ErrDigestMismatch
	}
	normalized.AggregateVersion = 1
	// MongoDB persists BSON datetimes at millisecond precision. Normalize the
	// aggregate before both the first response and durable receipt are produced
	// so an idempotent replay is byte-identical to the original command result.
	normalized.StagedAt = now.UTC().Truncate(time.Millisecond)
	return normalized, nil
}

func Digest(input Release) (string, error) {
	normalized, err := normalize(input, false)
	if err != nil {
		return "", err
	}
	payload := struct {
		PolicyID              string                `json:"policyId"`
		DefaultTemplateID     string                `json:"defaultTemplateId"`
		Templates             []Template            `json:"templates"`
		RoutingRules          []RoutingRule         `json:"routingRules"`
		LearningContextPolicy LearningContextPolicy `json:"learningContextPolicy"`
	}{
		PolicyID:              normalized.PolicyID,
		DefaultTemplateID:     normalized.DefaultTemplateID,
		Templates:             normalized.Templates,
		RoutingRules:          normalized.RoutingRules,
		LearningContextPolicy: normalized.LearningContextPolicy,
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return "", ErrInvalidArgument
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

func normalize(input Release, requireReleaseDigest bool) (Release, error) {
	input.PolicyID = strings.TrimSpace(input.PolicyID)
	input.ReleaseDigest = strings.TrimSpace(input.ReleaseDigest)
	input.DefaultTemplateID = strings.TrimSpace(input.DefaultTemplateID)
	if input.PolicyID == "" ||
		(requireReleaseDigest && !isCanonicalReleaseDigest(input.ReleaseDigest)) ||
		input.DefaultTemplateID == "" ||
		len(input.Templates) == 0 || len(input.Templates) > 128 ||
		len(input.RoutingRules) > 256 {
		return Release{}, ErrInvalidArgument
	}
	templates := append([]Template(nil), input.Templates...)
	templateIDs := make(map[string]struct{}, len(templates))
	for index := range templates {
		template := &templates[index]
		template.TemplateID = strings.TrimSpace(template.TemplateID)
		template.SkillID = strings.TrimSpace(template.SkillID)
		template.DomainID = strings.TrimSpace(template.DomainID)
		template.PromptPolicy = strings.TrimSpace(template.PromptPolicy)
		template.SearchIntensity = strings.TrimSpace(template.SearchIntensity)
		template.AllowedTools = normalizeStrings(template.AllowedTools)
		if template.TemplateID == "" || template.SkillID == "" ||
			template.DomainID == "" || template.PromptPolicy == "" ||
			template.SearchIntensity == "" {
			return Release{}, ErrInvalidArgument
		}
		if _, parseErr := assistantgenerated.ParseSearchIntensity(
			template.SearchIntensity,
		); parseErr != nil {
			return Release{}, ErrInvalidArgument
		}
		if _, duplicate := templateIDs[template.TemplateID]; duplicate {
			return Release{}, ErrInvalidArgument
		}
		templateIDs[template.TemplateID] = struct{}{}
	}
	if _, ok := templateIDs[input.DefaultTemplateID]; !ok {
		return Release{}, ErrInvalidArgument
	}
	sort.Slice(templates, func(i, j int) bool {
		return templates[i].TemplateID < templates[j].TemplateID
	})

	rules := append([]RoutingRule(nil), input.RoutingRules...)
	ruleIDs := make(map[string]struct{}, len(rules))
	priorities := make(map[int]struct{}, len(rules))
	for index := range rules {
		rule := &rules[index]
		rule.RuleID = strings.TrimSpace(rule.RuleID)
		rule.DomainID = strings.TrimSpace(rule.DomainID)
		rule.SkillID = strings.TrimSpace(rule.SkillID)
		rule.TemplateID = strings.TrimSpace(rule.TemplateID)
		if rule.RuleID == "" || rule.TemplateID == "" ||
			(rule.DomainID == "" && rule.SkillID == "") {
			return Release{}, ErrInvalidArgument
		}
		if _, ok := templateIDs[rule.TemplateID]; !ok {
			return Release{}, ErrInvalidArgument
		}
		if _, duplicate := ruleIDs[rule.RuleID]; duplicate {
			return Release{}, ErrInvalidArgument
		}
		if _, duplicate := priorities[rule.Priority]; duplicate {
			return Release{}, ErrInvalidArgument
		}
		ruleIDs[rule.RuleID] = struct{}{}
		priorities[rule.Priority] = struct{}{}
	}
	sort.Slice(rules, func(i, j int) bool {
		if rules[i].Priority == rules[j].Priority {
			return rules[i].RuleID < rules[j].RuleID
		}
		return rules[i].Priority < rules[j].Priority
	})
	input.Templates = templates
	input.RoutingRules = rules
	policy, err := normalizeLearningContextPolicy(input.LearningContextPolicy)
	if err != nil {
		return Release{}, err
	}
	input.LearningContextPolicy = policy
	return input, nil
}

func isCanonicalReleaseDigest(value string) bool {
	if len(value) != sha256.Size*2 || value != strings.ToLower(value) {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}

func normalizeLearningContextPolicy(
	policy LearningContextPolicy,
) (LearningContextPolicy, error) {
	policy.AllowedSignals = normalizeStrings(policy.AllowedSignals)
	policy.AllowedMetricIDs = normalizeStrings(policy.AllowedMetricIDs)
	policy.AllowedReasonCodes = normalizeStrings(policy.AllowedReasonCodes)
	if !policy.Enabled {
		return LearningContextPolicy{}, nil
	}
	if policy.MinimumFeedbackSamples < 1 ||
		policy.MinimumFeedbackSamples > 1000 ||
		policy.WindowDays < 1 ||
		policy.WindowDays > 90 {
		return LearningContextPolicy{}, ErrInvalidArgument
	}
	allowedSignalNames := map[string]struct{}{
		"feedback_counts":  {},
		"metric_summaries": {},
		"top_reason_codes": {},
	}
	if len(policy.AllowedSignals) == 0 {
		return LearningContextPolicy{}, ErrInvalidArgument
	}
	for _, signal := range policy.AllowedSignals {
		if _, ok := allowedSignalNames[signal]; !ok {
			return LearningContextPolicy{}, ErrInvalidArgument
		}
	}
	return policy, nil
}

func normalizeStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	out := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, duplicate := seen[value]; duplicate {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}
