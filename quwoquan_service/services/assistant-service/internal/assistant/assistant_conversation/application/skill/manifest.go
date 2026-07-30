package skill

const (
	// ActivationReactive 表示技能只在用户提问时被选中。
	ActivationReactive = "reactive"
	// ActivationProactive 表示技能由订阅调度触发，不参与用户提问的技能选择。
	ActivationProactive = "proactive"
)

type Manifest struct {
	SkillID string `json:"skillId"`
	// Activation 决定该技能是被用户提问选中还是被订阅调度触发；缺省视为 reactive。
	Activation      string     `json:"activation,omitempty"`
	DisplayName     string     `json:"displayName"`
	Description     string     `json:"description,omitempty"`
	DomainID        string     `json:"domainId"`
	ProblemClass    string     `json:"problemClass,omitempty"`
	TagRefs         []string   `json:"tagRefs,omitempty"`
	IconHint        string     `json:"iconHint,omitempty"`
	ExecutionTarget string     `json:"executionTarget"`
	RoutingHints    []string   `json:"routingHints,omitempty"`
	PromptAssets    []string   `json:"promptAssets,omitempty"`
	SlotSchema      SlotSchema `json:"slotSchema,omitempty"`
	ToolPolicy      ToolPolicy `json:"toolPolicy"`
	Examples        []string   `json:"examples,omitempty"`
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

func (m Manifest) IsProactive() bool {
	return m.Activation == ActivationProactive
}

func DefaultManifest() Manifest {
	return Manifest{
		SkillID:         "general_qa",
		Activation:      ActivationReactive,
		DisplayName:     "通用问答",
		Description:     "M5 云侧通用问答 skill",
		DomainID:        "assistant",
		ProblemClass:    "general",
		ExecutionTarget: "cloud",
		RoutingHints:    []string{"assistant", "general"},
		ToolPolicy: ToolPolicy{
			AllowedTools:   []string{},
			PreferredTools: []string{},
			MaxToolCalls:   0,
		},
	}
}
