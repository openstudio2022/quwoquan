package skill

import (
	"context"

	rctx "quwoquan_service/runtime/context"
)

// Skill is the interface all skills must implement.
type Skill interface {
	Manifest() SkillManifest
	Execute(ctx context.Context, input SkillInput) (SkillOutput, error)
}

// SkillManifest declares a skill's capabilities, constraints, and requirements.
type SkillManifest struct {
	ID                  string            `yaml:"id"                  json:"id"`
	Name                string            `yaml:"name"                json:"name"`
	Provider            string            `yaml:"provider"            json:"provider"`
	Version             string            `yaml:"version"             json:"version"`
	ApplicablePages     []PageMatcher     `yaml:"applicable_pages"    json:"applicablePages"`
	ContextRequirements ContextScope      `yaml:"context_requirements" json:"contextRequirements"`
	ToolDependencies    []string          `yaml:"tool_dependencies"   json:"toolDependencies"`
	OutputTypes         []string          `yaml:"output_types"        json:"outputTypes"`
	DataClassMax        DataClass         `yaml:"data_class_max"      json:"dataClassMax"`
	RequiresConsent     bool              `yaml:"requires_consent"    json:"requiresConsent"`
	Priority            int               `yaml:"priority"            json:"priority"`
	Description         string            `yaml:"description"        json:"description"`
}

type PageMatcher struct {
	PageType     string   `yaml:"page_type"     json:"pageType"`
	ContentTypes []string `yaml:"content_types" json:"contentTypes,omitempty"`
	TagMatch     []string `yaml:"tag_match"     json:"tagMatch,omitempty"`
}

type ContextScope struct {
	Page     bool     `yaml:"page"     json:"page"`
	Session  bool     `yaml:"session"  json:"session"`
	Profile  bool     `yaml:"profile"  json:"profile"`
	Dimensions []string `yaml:"dimensions" json:"dimensions,omitempty"`
}

type DataClass string

const (
	DataClassPublic    DataClass = "PUBLIC"
	DataClassPII       DataClass = "PII"
	DataClassSensitive DataClass = "SENSITIVE"
)

// SkillInput is provided by the runtime to a skill during execution.
type SkillInput struct {
	UserID     string                          `json:"userId"`
	SessionID  string                          `json:"sessionId"`
	PageContext *rctx.PageContextSnapshot       `json:"pageContext,omitempty"`
	SessionCtx *rctx.SessionSignalSnapshot     `json:"sessionCtx,omitempty"`
	ProfileCtx *rctx.UserHolisticProfile       `json:"profileCtx,omitempty"`
	Query      string                          `json:"query,omitempty"`
	Parameters map[string]any                  `json:"parameters,omitempty"`
	Tools      ToolProxy                       `json:"-"`
}

// SkillOutput is the result from a skill execution.
type SkillOutput struct {
	Type    string         `json:"type"`
	Content string         `json:"content,omitempty"`
	Data    map[string]any `json:"data,omitempty"`
	Actions []SkillAction  `json:"actions,omitempty"`
}

type SkillAction struct {
	Label   string         `json:"label"`
	Type    string         `json:"type"`
	Payload map[string]any `json:"payload,omitempty"`
}

// Tool is a callable business capability exposed to skills.
type Tool struct {
	ID           string    `yaml:"id"            json:"id"`
	Name         string    `yaml:"name"          json:"name"`
	Description  string    `yaml:"description"   json:"description"`
	DataClassMax DataClass `yaml:"data_class_max" json:"dataClassMax"`
	PageTypes    []string  `yaml:"page_types"    json:"pageTypes,omitempty"`
	InputSchema  string    `yaml:"input_schema"  json:"inputSchema"`
	OutputSchema string    `yaml:"output_schema" json:"outputSchema"`
}

// ToolProxy mediates skill access to tools with permission enforcement.
type ToolProxy interface {
	Call(ctx context.Context, toolID string, input map[string]any) (map[string]any, error)
	Available(ctx context.Context, pageType string) []Tool
}

// ConsentRecord tracks user authorization for skills.
type ConsentRecord struct {
	UserID    string `json:"userId"    bson:"userId"`
	SkillID   string `json:"skillId"   bson:"skillId"`
	Granted   bool   `json:"granted"   bson:"granted"`
	GrantedAt int64  `json:"grantedAt" bson:"grantedAt"`
}
