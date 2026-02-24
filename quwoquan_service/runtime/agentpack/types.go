package agentpack

import "time"

// TaskPack is the schema for agent_task_pack.yaml — the artifact produced after
// every feature development, capturing full context for the feature tree.
type TaskPack struct {
	Version     int            `yaml:"version"     json:"version"`
	Feature     FeatureInfo    `yaml:"feature"     json:"feature"`
	Metadata    MetadataRef    `yaml:"metadata"    json:"metadata"`
	Deliverables []Deliverable `yaml:"deliverables" json:"deliverables"`
	Tests       []TestRef      `yaml:"tests"       json:"tests"`
	Acceptance  AcceptanceRef  `yaml:"acceptance"  json:"acceptance"`
	Dependencies []string      `yaml:"dependencies" json:"dependencies"`
	CreatedAt   time.Time      `yaml:"created_at"  json:"createdAt"`
	Agent       AgentInfo      `yaml:"agent"       json:"agent"`
}

type FeatureInfo struct {
	ID          string   `yaml:"id"          json:"id"`
	Name        string   `yaml:"name"        json:"name"`
	Level       string   `yaml:"level"       json:"level"`
	Path        string   `yaml:"path"        json:"path"`
	Domain      string   `yaml:"domain"      json:"domain"`
	Tags        []string `yaml:"tags"        json:"tags"`
	Description string   `yaml:"description" json:"description"`
}

type MetadataRef struct {
	Aggregates []string `yaml:"aggregates" json:"aggregates"`
	Entities   []string `yaml:"entities"   json:"entities"`
	Events     []string `yaml:"events"     json:"events"`
	Services   []string `yaml:"services"   json:"services"`
}

type Deliverable struct {
	Type string `yaml:"type" json:"type"`
	Path string `yaml:"path" json:"path"`
	Desc string `yaml:"desc" json:"desc"`
}

type TestRef struct {
	Type string `yaml:"type" json:"type"`
	Path string `yaml:"path" json:"path"`
	Desc string `yaml:"desc" json:"desc"`
}

type AcceptanceRef struct {
	Criteria []string `yaml:"criteria" json:"criteria"`
	GateCmd  string   `yaml:"gate_cmd" json:"gateCmd"`
}

type AgentInfo struct {
	ID      string `yaml:"id"      json:"id"`
	Model   string `yaml:"model"   json:"model"`
	RunID   string `yaml:"run_id"  json:"runId"`
}
