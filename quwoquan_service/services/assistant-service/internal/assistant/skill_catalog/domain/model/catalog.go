package model

const PersonalContentAccessSkillID = "personal_content_access"

// Item 是 SkillCatalog 的只读目录项。账号授权信息只允许投影到 Description，
// 不进入 canonical manifest 或其他账号的目录响应。
type Item struct {
	SkillID         string `json:"skillId"`
	DisplayName     string `json:"displayName"`
	Description     string `json:"description,omitempty"`
	Category        string `json:"category,omitempty"`
	RequiresConsent bool   `json:"requiresConsent"`
	IconHint        string `json:"iconHint,omitempty"`
}

type ListView struct {
	Items []Item `json:"items"`
}
