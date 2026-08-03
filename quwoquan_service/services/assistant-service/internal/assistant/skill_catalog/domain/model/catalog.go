package model

import "encoding/json"

const PersonalContentAccessSkillID = "personal_content_access"

// Item 是 active immutable SkillPackageRelease 的只读目录投影；账号
// Consent、Setting 与 Subscription 由各自对象读取，不得混入目录。
type Item struct {
	PackageID                   string          `json:"packageId"`
	ReleaseDigest               string          `json:"releaseDigest"`
	SkillID                     string          `json:"skillId"`
	DisplayName                 string          `json:"displayName"`
	Description                 string          `json:"description,omitempty"`
	Category                    string          `json:"category,omitempty"`
	RequiresConsent             bool            `json:"requiresConsent"`
	RequiredConsentScopes       []string        `json:"requiredConsentScopes"`
	IconHint                    string          `json:"iconHint,omitempty"`
	CoverMediaRef               string          `json:"coverMediaRef,omitempty"`
	TargetUsers                 []string        `json:"targetUsers"`
	DataUseSummary              string          `json:"dataUseSummary"`
	ExampleRefs                 []string        `json:"exampleRefs"`
	ActivationMode              string          `json:"activationMode"`
	AllowedSurfaceKinds         []string        `json:"allowedSurfaceKinds"`
	ConfigurationSchemaDigest   string          `json:"configurationSchemaDigest"`
	ConfigurationSchema         json.RawMessage `json:"-"`
	SetupTemplateRef            string          `json:"setupTemplateRef"`
	ConfigurationRequiredFields []string        `json:"configurationRequiredFields"`
}

type ListView struct {
	Items []Item `json:"items"`
}

type DetailView struct {
	Item                Item            `json:"item"`
	ConfigurationSchema json.RawMessage `json:"configurationSchema"`
}
