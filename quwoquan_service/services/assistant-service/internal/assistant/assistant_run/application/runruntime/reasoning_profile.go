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
	MaxVerificationRepairs  int
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

// DefaultReasoningProfileCatalog defines provider-neutral execution classes.
// Model/provider selection remains a capability negotiation performed by the
// executor; these values only bound durable Run work and honest stopping.
func DefaultReasoningProfileCatalog() (*ReasoningProfileCatalog, error) {
	return NewReasoningProfileCatalog([]ReasoningProfileConfig{
		{
			Profile: generated.AssistantReasoningProfileFast,
			Capability: CapabilityRequirements{
				ToolCalling:     true,
				ReasoningEffort: true,
			},
			Budget: ReasoningBudget{
				MaxDuration:  45 * time.Second,
				MaxTokens:    8_000,
				MaxCostUnits: 8_000,
				MaxToolCalls: 2,
				MaxSubagents: 0,
				MaxSources:   4,
			},
			ReflectionEverySteps: 1,
			SourceBreadth:        2,
			SourceDepth:          1,
			CheckpointEvery:      15 * time.Second,
			StopRules: ReasoningStopRules{
				RequireDefinitionOfDone: true,
				RequireVerifier:         true,
				StopOnBudgetExhaustion:  true,
				MaxVerificationRepairs:  0,
			},
		},
		{
			Profile: generated.AssistantReasoningProfileBalanced,
			Capability: CapabilityRequirements{
				ToolCalling:     true,
				ParallelTools:   true,
				ReasoningEffort: true,
			},
			Budget: ReasoningBudget{
				MaxDuration:  3 * time.Minute,
				MaxTokens:    24_000,
				MaxCostUnits: 24_000,
				MaxToolCalls: 8,
				MaxSubagents: 2,
				MaxSources:   12,
			},
			ReflectionEverySteps: 2,
			SourceBreadth:        4,
			SourceDepth:          2,
			CheckpointEvery:      30 * time.Second,
			StopRules: ReasoningStopRules{
				RequireDefinitionOfDone: true,
				RequireVerifier:         true,
				StopOnBudgetExhaustion:  true,
				MaxVerificationRepairs:  1,
			},
		},
		{
			Profile: generated.AssistantReasoningProfileDeep,
			Capability: CapabilityRequirements{
				ToolCalling:     true,
				ParallelTools:   true,
				Compaction:      true,
				ReasoningEffort: true,
			},
			Budget: ReasoningBudget{
				MaxDuration:  15 * time.Minute,
				MaxTokens:    96_000,
				MaxCostUnits: 96_000,
				MaxToolCalls: 24,
				MaxSubagents: 4,
				MaxSources:   32,
			},
			ReflectionEverySteps: 2,
			SourceBreadth:        8,
			SourceDepth:          4,
			CheckpointEvery:      time.Minute,
			StopRules: ReasoningStopRules{
				RequireDefinitionOfDone: true,
				RequireEvidence:         true,
				RequireVerifier:         true,
				StopOnBudgetExhaustion:  true,
				MaxVerificationRepairs:  2,
			},
		},
		{
			Profile: generated.AssistantReasoningProfileBackgroundLong,
			Capability: CapabilityRequirements{
				ToolCalling:     true,
				ParallelTools:   true,
				Background:      true,
				Compaction:      true,
				ReasoningEffort: true,
			},
			Budget: ReasoningBudget{
				MaxDuration:  2 * time.Hour,
				MaxTokens:    256_000,
				MaxCostUnits: 256_000,
				MaxToolCalls: 64,
				MaxSubagents: 8,
				MaxSources:   96,
			},
			ReflectionEverySteps: 3,
			SourceBreadth:        12,
			SourceDepth:          6,
			CheckpointEvery:      2 * time.Minute,
			StopRules: ReasoningStopRules{
				RequireDefinitionOfDone: true,
				RequireEvidence:         true,
				RequireVerifier:         true,
				StopOnBudgetExhaustion:  true,
				MaxVerificationRepairs:  3,
			},
		},
	})
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
		config.Budget.MaxCostUnits <= 0 ||
		config.Budget.MaxToolCalls < 0 || config.Budget.MaxSubagents < 0 ||
		config.Budget.MaxSources <= 0 || config.ReflectionEverySteps <= 0 ||
		config.SourceBreadth <= 0 || config.SourceDepth <= 0 ||
		config.CheckpointEvery <= 0 ||
		config.StopRules.MaxVerificationRepairs < 0 {
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

func validateReasoningProfileForRun(
	config ReasoningProfileConfig,
	definition DefinitionOfDone,
) error {
	if err := validateReasoningProfile(config); err != nil {
		return err
	}
	if config.StopRules.RequireDefinitionOfDone &&
		(strings.TrimSpace(definition.Outcome) == "" ||
			len(definition.VerificationRequirements) == 0 ||
			definition.FrozenAt.IsZero()) {
		return fmt.Errorf("reasoning profile %s requires a frozen Definition of Done", config.Profile)
	}
	if config.StopRules.RequireEvidence &&
		!definitionRequiresEvidence(definition.VerificationRequirements) {
		return fmt.Errorf("reasoning profile %s requires an evidence-backed completion requirement", config.Profile)
	}
	return nil
}

func definitionRequiresEvidence(requirements []string) bool {
	for _, requirement := range requirements {
		switch strings.TrimSpace(requirement) {
		case "evidence_present", "citations_present":
			return true
		}
	}
	return false
}
