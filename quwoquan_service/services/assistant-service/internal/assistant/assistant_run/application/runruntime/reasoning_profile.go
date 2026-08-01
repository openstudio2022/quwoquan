package runruntime

import (
	"errors"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type CapabilityRequirements struct {
	ToolCalling     bool
	ParallelTools   bool
	Background      bool
	Compaction      bool
	ReasoningEffort bool
}

type ReasoningBudget struct {
	MaxDuration  time.Duration
	MaxTokens    int64
	MaxCostUnits int64
	MaxToolCalls int
	MaxSubagents int
	MaxSources   int
}

type ReasoningStopRules struct {
	RequireDefinitionOfDone bool
	RequireEvidence         bool
	RequireVerifier         bool
	StopOnBudgetExhaustion  bool
}

type ReasoningProfileConfig struct {
	Profile              generated.AssistantReasoningProfile
	Capability           CapabilityRequirements
	Budget               ReasoningBudget
	ReflectionEverySteps int
	SourceBreadth        int
	SourceDepth          int
	CheckpointEvery      time.Duration
	StopRules            ReasoningStopRules
}

type ReasoningProfileCatalog struct {
	profiles map[generated.AssistantReasoningProfile]ReasoningProfileConfig
}

func NewReasoningProfileCatalog(
	configs []ReasoningProfileConfig,
) (*ReasoningProfileCatalog, error) {
	catalog := &ReasoningProfileCatalog{
		profiles: make(map[generated.AssistantReasoningProfile]ReasoningProfileConfig, len(configs)),
	}
	for _, config := range configs {
		if err := validateReasoningProfile(config); err != nil {
			return nil, err
		}
		if _, exists := catalog.profiles[config.Profile]; exists {
			return nil, fmt.Errorf("duplicate reasoning profile %s", config.Profile)
		}
		catalog.profiles[config.Profile] = config
	}
	for _, required := range []generated.AssistantReasoningProfile{
		generated.AssistantReasoningProfileFast,
		generated.AssistantReasoningProfileBalanced,
		generated.AssistantReasoningProfileDeep,
		generated.AssistantReasoningProfileBackgroundLong,
	} {
		if _, ok := catalog.profiles[required]; !ok {
			return nil, fmt.Errorf("required reasoning profile %s is missing", required)
		}
	}
	return catalog, nil
}

func (c *ReasoningProfileCatalog) Resolve(
	profile generated.AssistantReasoningProfile,
) (ReasoningProfileConfig, error) {
	if c == nil {
		return ReasoningProfileConfig{}, errors.New("reasoning profile catalog is nil")
	}
	config, ok := c.profiles[profile]
	if !ok {
		return ReasoningProfileConfig{}, fmt.Errorf("reasoning profile %s is unavailable", profile)
	}
	return config, nil
}

func validateReasoningProfile(config ReasoningProfileConfig) error {
	if strings.TrimSpace(config.Profile.WireName()) == "" ||
		config.Budget.MaxDuration <= 0 || config.Budget.MaxTokens <= 0 ||
		config.Budget.MaxToolCalls < 0 || config.Budget.MaxSubagents < 0 ||
		config.Budget.MaxSources < 0 || config.ReflectionEverySteps <= 0 ||
		config.CheckpointEvery <= 0 {
		return fmt.Errorf("invalid reasoning profile %s", config.Profile)
	}
	if (config.Profile == generated.AssistantReasoningProfileDeep ||
		config.Profile == generated.AssistantReasoningProfileBackgroundLong) &&
		(!config.StopRules.RequireDefinitionOfDone || !config.StopRules.RequireVerifier) {
		return fmt.Errorf("reasoning profile %s lacks honest completion gates", config.Profile)
	}
	if config.Profile == generated.AssistantReasoningProfileBackgroundLong &&
		(!config.Capability.Background || !config.Capability.Compaction) {
		return errors.New("background_long requires background execution and compaction")
	}
	return nil
}
