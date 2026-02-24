package skillstore

import "time"

// SkillStatus tracks the lifecycle state of a skill in the store.
type SkillStatus string

const (
	StatusDraft     SkillStatus = "draft"
	StatusReview    SkillStatus = "review"
	StatusApproved  SkillStatus = "approved"
	StatusRejected  SkillStatus = "rejected"
	StatusGray      SkillStatus = "gray"
	StatusPublished SkillStatus = "published"
	StatusArchived  SkillStatus = "archived"
)

// SkillRegistration is the persisted record for a skill in the store.
type SkillRegistration struct {
	SkillID     string          `json:"skillId"     bson:"skillId"`
	Name        string          `json:"name"        bson:"name"`
	Provider    string          `json:"provider"    bson:"provider"`
	Version     string          `json:"version"     bson:"version"`
	Status      SkillStatus     `json:"status"      bson:"status"`
	Manifest    SkillManifestRef `json:"manifest"   bson:"manifest"`
	Review      *ReviewRecord   `json:"review,omitempty"   bson:"review,omitempty"`
	GrayConfig  *GrayConfig     `json:"grayConfig,omitempty" bson:"grayConfig,omitempty"`
	Metrics     SkillMetrics    `json:"metrics"     bson:"metrics"`
	CreatedAt   time.Time       `json:"createdAt"   bson:"createdAt"`
	UpdatedAt   time.Time       `json:"updatedAt"   bson:"updatedAt"`
	PublishedAt *time.Time      `json:"publishedAt,omitempty" bson:"publishedAt,omitempty"`
}

type SkillManifestRef struct {
	ApplicablePages     []string `json:"applicablePages"     bson:"applicablePages"`
	ContextRequirements []string `json:"contextRequirements" bson:"contextRequirements"`
	ToolDependencies    []string `json:"toolDependencies"    bson:"toolDependencies"`
	DataClassMax        string   `json:"dataClassMax"        bson:"dataClassMax"`
	RequiresConsent     bool     `json:"requiresConsent"     bson:"requiresConsent"`
}

type ReviewRecord struct {
	ReviewerID string      `json:"reviewerId" bson:"reviewerId"`
	Decision   SkillStatus `json:"decision"   bson:"decision"`
	Comment    string      `json:"comment"    bson:"comment"`
	ReviewedAt time.Time   `json:"reviewedAt" bson:"reviewedAt"`
	AutoChecks []AutoCheck `json:"autoChecks" bson:"autoChecks"`
}

type AutoCheck struct {
	Name   string `json:"name"   bson:"name"`
	Passed bool   `json:"passed" bson:"passed"`
	Detail string `json:"detail" bson:"detail"`
}

type GrayConfig struct {
	TrafficPercent float64   `json:"trafficPercent" bson:"trafficPercent"`
	StartedAt      time.Time `json:"startedAt"      bson:"startedAt"`
	Duration       string    `json:"duration"       bson:"duration"`
	BaselineID     string    `json:"baselineId"     bson:"baselineId"`
}

type SkillMetrics struct {
	TotalCalls   int64   `json:"totalCalls"   bson:"totalCalls"`
	SuccessRate  float64 `json:"successRate"  bson:"successRate"`
	AvgLatencyMs float64 `json:"avgLatencyMs" bson:"avgLatencyMs"`
	UserRating   float64 `json:"userRating"   bson:"userRating"`
	RatingCount  int64   `json:"ratingCount"  bson:"ratingCount"`
}

// SandboxConfig defines resource constraints for ecosystem skill execution.
type SandboxConfig struct {
	MaxMemoryMB    int           `json:"maxMemoryMb"`
	MaxCPUPercent  int           `json:"maxCpuPercent"`
	TimeoutSeconds int           `json:"timeoutSeconds"`
	AllowedAPIs    []string      `json:"allowedApis"`
	NetworkPolicy  NetworkPolicy `json:"networkPolicy"`
}

type NetworkPolicy string

const (
	NetworkNone     NetworkPolicy = "none"
	NetworkInternal NetworkPolicy = "internal"
	NetworkExternal NetworkPolicy = "external"
)
