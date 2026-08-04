package model

import "encoding/json"

type SemanticLabel struct {
	ID          string `json:"id"`
	DisplayText string `json:"displayText"`
	Description string `json:"description,omitempty"`
}

type ResolvedExample struct {
	ExampleID                  string `json:"exampleId"`
	Title                      string `json:"title"`
	Summary                    string `json:"summary"`
	IconToken                  string `json:"iconToken,omitempty"`
	MediaRef                   string `json:"mediaRef,omitempty"`
	PresentationTemplateRef    string `json:"presentationTemplateRef"`
	PresentationTemplateDigest string `json:"presentationTemplateDigest"`
}

// Item 是 active immutable SkillPackageRelease 的只读目录投影；账号
// Consent、Setting 与 Subscription 由各自对象读取，不得混入目录。
type Item struct {
	PackageID                   string            `json:"packageId"`
	ReleaseDigest               string            `json:"releaseDigest"`
	SkillID                     string            `json:"skillId"`
	DomainID                    string            `json:"domainId"`
	DisplayName                 string            `json:"displayName"`
	Description                 string            `json:"description,omitempty"`
	CatalogGroup                SemanticLabel     `json:"catalogGroup"`
	RequiresConsent             bool              `json:"requiresConsent"`
	RequiredConsentScopes       []string          `json:"requiredConsentScopes"`
	ConsentScopeLabels          []SemanticLabel   `json:"consentScopeLabels"`
	IconHint                    string            `json:"iconHint,omitempty"`
	CoverMediaRef               string            `json:"coverMediaRef,omitempty"`
	TargetAudiences             []SemanticLabel   `json:"targetAudiences"`
	DataUseSummary              string            `json:"dataUseSummary"`
	Examples                    []ResolvedExample `json:"examples"`
	ActivationMode              string            `json:"activationMode"`
	SurfaceKinds                []SemanticLabel   `json:"surfaceKinds"`
	ConfigurationSchemaDigest   string            `json:"configurationSchemaDigest"`
	ConfigurationSchema         json.RawMessage   `json:"-"`
	SetupTemplateRef            string            `json:"setupTemplateRef"`
	ConfigurationRequiredFields []string          `json:"configurationRequiredFields"`
}

type ListView struct {
	Items []Item `json:"items"`
}

type DetailView struct {
	Item                Item            `json:"item"`
	ConfigurationSchema json.RawMessage `json:"configurationSchema"`
}
