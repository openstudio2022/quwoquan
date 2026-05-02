package skill

type Manifest struct {
	SkillID         string     `json:"skillId"`
	DisplayName     string     `json:"displayName"`
	Description     string     `json:"description,omitempty"`
	DomainID        string     `json:"domainId"`
	TagRefs         []string   `json:"tagRefs,omitempty"`
	IconHint        string     `json:"iconHint,omitempty"`
	ExecutionTarget string     `json:"executionTarget"`
	RoutingHints    []string   `json:"routingHints,omitempty"`
	PromptAssets    []string   `json:"promptAssets,omitempty"`
	ToolPolicy      ToolPolicy `json:"toolPolicy"`
	Examples        []string   `json:"examples,omitempty"`
}

type ToolPolicy struct {
	AllowedTools              []string `json:"allowedTools,omitempty"`
	PreferredTools            []string `json:"preferredTools,omitempty"`
	MaxToolCalls              int      `json:"maxToolCalls,omitempty"`
	AllowDeviceContext        bool     `json:"allowDeviceContext,omitempty"`
	AllowDeviceActionProposal bool     `json:"allowDeviceActionProposal,omitempty"`
}

func DefaultManifest() Manifest {
	return Manifest{
		SkillID:         "general_qa",
		DisplayName:     "通用问答",
		Description:     "M5 云侧通用问答 skill",
		DomainID:        "assistant",
		ExecutionTarget: "cloud",
		RoutingHints:    []string{"assistant", "general"},
		ToolPolicy: ToolPolicy{
			AllowedTools:   []string{"mock_search"},
			PreferredTools: []string{"mock_search"},
			MaxToolCalls:   3,
		},
	}
}
