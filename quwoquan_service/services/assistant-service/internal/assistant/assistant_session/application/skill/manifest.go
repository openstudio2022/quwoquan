package skill

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
)

const (
	// ActivationReactive 表示技能只在用户提问时被选中。
	ActivationReactive = "reactive"
	// ActivationProactive 表示技能由订阅调度触发，不参与用户提问的技能选择。
	ActivationProactive = "proactive"
)

type Manifest struct {
	SkillID                string   `json:"skillId"`
	DisplayName            string   `json:"displayName"`
	Description            string   `json:"description,omitempty"`
	DomainID               string   `json:"domainId"`
	ProblemClass           string   `json:"problemClass,omitempty"`
	TagRefs                []string `json:"tagRefs,omitempty"`
	ExecutionTarget        string   `json:"executionTarget"`
	RoutingHints           []string `json:"routingHints,omitempty"`
	ActivationProfileRef   string   `json:"activationProfileRef"`
	ContextProfileRef      string   `json:"contextProfileRef"`
	CapabilityProfileRef   string   `json:"capabilityProfileRef"`
	PresentationProfileRef string   `json:"presentationProfileRef"`
	EvaluationProfileRef   string   `json:"evaluationProfileRef"`
	ReplayAssetRef         string   `json:"replayAssetRef"`
	PromptAssets           []string `json:"promptAssets,omitempty"`
	Examples               []string `json:"examples,omitempty"`

	// 以下字段只由 digest 校验后的 profile assets 派生，不能从 manifest JSON
	// 反序列化。这样运行时调用点可以渐进迁移，而不保留 inline/ref 双真相源。
	Activation        string                `json:"-"`
	IconHint          string                `json:"-"`
	SlotSchema        SlotSchema            `json:"-"`
	ToolPolicy        ToolPolicy            `json:"-"`
	ContextProfile    ContextProfile        `json:"-"`
	Presentation      PresentationProfile   `json:"-"`
	Evaluation        EvaluationProfile     `json:"-"`
	ResolvedAssetRefs map[string]AssetProof `json:"-"`
}

type SlotSchema struct {
	RequiredSlots []string `json:"requiredSlots,omitempty"`
	OptionalSlots []string `json:"optionalSlots,omitempty"`
	CarryOver     bool     `json:"carryOver,omitempty"`
	StateID       string   `json:"stateId,omitempty"`
	NextStateID   string   `json:"nextStateId,omitempty"`
}

type ToolPolicy struct {
	AllowedTools              []string `json:"allowedTools,omitempty"`
	PreferredTools            []string `json:"preferredTools,omitempty"`
	MaxToolCalls              int      `json:"maxToolCalls,omitempty"`
	AllowDeviceContext        bool     `json:"allowDeviceContext,omitempty"`
	AllowDeviceActionProposal bool     `json:"allowDeviceActionProposal,omitempty"`
}

// ResolvedReleaseDigest binds a static Skill manifest to the exact immutable
// profile assets exposed to the runtime. Replay assets use this digest so a
// prompt/profile/catalog change cannot silently reuse an evaluation corpus
// built for another release.
func (m Manifest) ResolvedProfileDigest() (string, error) {
	return m.resolvedDigest(false)
}

func (m Manifest) ResolvedReleaseDigest() (string, error) {
	return m.resolvedDigest(true)
}

func (m Manifest) resolvedDigest(includeReplay bool) (string, error) {
	type asset struct {
		Kind        string `json:"kind"`
		ProfileID   string `json:"profileId"`
		AssetDigest string `json:"assetDigest"`
	}
	kinds := []string{
		"activation",
		"context",
		"capability",
		"presentation",
		"evaluation",
	}
	if includeReplay {
		kinds = append(kinds, "replay")
	}
	assets := make([]asset, 0, len(kinds))
	for _, kind := range kinds {
		proof, found := m.ResolvedAssetRefs[kind]
		if !found ||
			strings.TrimSpace(proof.ProfileID) == "" ||
			!strings.HasPrefix(strings.TrimSpace(proof.AssetDigest), "sha256:") {
			return "", fmt.Errorf("skill %q has no resolved %s asset", m.SkillID, kind)
		}
		assets = append(assets, asset{
			Kind:        kind,
			ProfileID:   strings.TrimSpace(proof.ProfileID),
			AssetDigest: strings.TrimSpace(proof.AssetDigest),
		})
	}
	descriptor := struct {
		SchemaVersion          int      `json:"schemaVersion"`
		SkillID                string   `json:"skillId"`
		DisplayName            string   `json:"displayName"`
		Description            string   `json:"description,omitempty"`
		DomainID               string   `json:"domainId"`
		ProblemClass           string   `json:"problemClass,omitempty"`
		TagRefs                []string `json:"tagRefs,omitempty"`
		ExecutionTarget        string   `json:"executionTarget"`
		RoutingHints           []string `json:"routingHints,omitempty"`
		ActivationProfileRef   string   `json:"activationProfileRef"`
		ContextProfileRef      string   `json:"contextProfileRef"`
		CapabilityProfileRef   string   `json:"capabilityProfileRef"`
		PresentationProfileRef string   `json:"presentationProfileRef"`
		EvaluationProfileRef   string   `json:"evaluationProfileRef"`
		ReplayAssetRef         string   `json:"replayAssetRef,omitempty"`
		PromptAssets           []string `json:"promptAssets,omitempty"`
		Examples               []string `json:"examples,omitempty"`
		Assets                 []asset  `json:"assets"`
	}{
		SchemaVersion:          1,
		SkillID:                strings.TrimSpace(m.SkillID),
		DisplayName:            strings.TrimSpace(m.DisplayName),
		Description:            strings.TrimSpace(m.Description),
		DomainID:               strings.TrimSpace(m.DomainID),
		ProblemClass:           strings.TrimSpace(m.ProblemClass),
		TagRefs:                m.TagRefs,
		ExecutionTarget:        strings.TrimSpace(m.ExecutionTarget),
		RoutingHints:           m.RoutingHints,
		ActivationProfileRef:   strings.TrimSpace(m.ActivationProfileRef),
		ContextProfileRef:      strings.TrimSpace(m.ContextProfileRef),
		CapabilityProfileRef:   strings.TrimSpace(m.CapabilityProfileRef),
		PresentationProfileRef: strings.TrimSpace(m.PresentationProfileRef),
		EvaluationProfileRef:   strings.TrimSpace(m.EvaluationProfileRef),
		PromptAssets:           m.PromptAssets,
		Examples:               m.Examples,
		Assets:                 assets,
	}
	if includeReplay {
		descriptor.ReplayAssetRef = strings.TrimSpace(m.ReplayAssetRef)
	}
	encoded, err := json.Marshal(descriptor)
	if err != nil {
		return "", fmt.Errorf("encode skill release descriptor: %w", err)
	}
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func (m Manifest) IsProactive() bool {
	return m.Activation == ActivationProactive
}

func DefaultManifest() Manifest {
	return Manifest{
		SkillID:                "general_qa",
		Activation:             ActivationReactive,
		DisplayName:            "通用问答",
		Description:            "M5 云侧通用问答 skill",
		DomainID:               "assistant",
		ProblemClass:           "general",
		ExecutionTarget:        "cloud",
		RoutingHints:           []string{"assistant", "general"},
		ActivationProfileRef:   "activation.reactive",
		ContextProfileRef:      "context.none",
		CapabilityProfileRef:   "capability.none",
		PresentationProfileRef: "presentation.default",
		EvaluationProfileRef:   "evaluation.general",
		ToolPolicy: ToolPolicy{
			AllowedTools:   []string{},
			PreferredTools: []string{},
			MaxToolCalls:   0,
		},
	}
}
