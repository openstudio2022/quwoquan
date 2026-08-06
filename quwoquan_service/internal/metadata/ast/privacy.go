package ast

// PrivacyClassification is the effective classification used by an App log
// policy. Governance requires it to be at least as restrictive as the owning
// field's canonical classification in fields.yaml.
type PrivacyClassification string

const (
	PrivacyClassificationPublic    PrivacyClassification = "PUBLIC"
	PrivacyClassificationInternal  PrivacyClassification = "INTERNAL"
	PrivacyClassificationPII       PrivacyClassification = "PII"
	PrivacyClassificationSensitive PrivacyClassification = "SENSITIVE"
	PrivacyClassificationSecret    PrivacyClassification = "SECRET"
)

type PrivacyAppLogAction string

const (
	PrivacyAppLogAllow         PrivacyAppLogAction = "allow"
	PrivacyAppLogMask          PrivacyAppLogAction = "mask"
	PrivacyAppLogDrop          PrivacyAppLogAction = "drop"
	PrivacyAppLogTruncate      PrivacyAppLogAction = "truncate"
	PrivacyAppLogCountOnly     PrivacyAppLogAction = "count_only"
	PrivacyAppLogDropIfTooLong PrivacyAppLogAction = "drop_if_gt_100chars"
)

type PrivacyDeletionStrategy string

const (
	PrivacyDeletionHardDelete             PrivacyDeletionStrategy = "hard_delete"
	PrivacyDeletionSoftDelete             PrivacyDeletionStrategy = "soft_delete"
	PrivacyDeletionSoftDeleteThenCDNPurge PrivacyDeletionStrategy = "soft_delete_then_cdn_purge"
	PrivacyDeletionScrub                  PrivacyDeletionStrategy = "scrub"
)

type PrivacyAnonymizationStrategy string

const (
	PrivacyAnonymizationReplaceWithPlaceholder PrivacyAnonymizationStrategy = "replace_with_placeholder"
	PrivacyAnonymizationDrop                   PrivacyAnonymizationStrategy = "drop"
)

// PrivacyDocument is the complete authored shape of one object-local
// privacy.yaml. Object identity is deliberately absent: load derives it from
// the canonical service/domain/context/object path.
type PrivacyDocument struct {
	Description     string                   `json:"description" yaml:"description"`
	AppLogPolicy    []PrivacyAppLogPolicy    `json:"app_log_policy,omitempty" yaml:"app_log_policy,omitempty"`
	DataLifecycle   *PrivacyDataLifecycle    `json:"data_lifecycle,omitempty" yaml:"data_lifecycle,omitempty"`
	FieldVisibility []PrivacyFieldVisibility `json:"field_visibility,omitempty" yaml:"field_visibility,omitempty"`
}

// PrivacyAppLogPolicy is an explicit App-log allow/sanitization entry. Fields
// absent from AppLogPolicy are denied by default; this metadata never implies
// that arbitrary object fields are safe to log.
type PrivacyAppLogPolicy struct {
	Field          string                `json:"field" yaml:"field"`
	Classification PrivacyClassification `json:"classification" yaml:"classification"`
	AppLog         PrivacyAppLogAction   `json:"app_log" yaml:"app_log"`
	MaskStrategy   string                `json:"mask_strategy,omitempty" yaml:"mask_strategy,omitempty"`
	TruncateChars  *int                  `json:"truncate_chars,omitempty" yaml:"truncate_chars,omitempty"`
	Description    string                `json:"description,omitempty" yaml:"description,omitempty"`
}

type PrivacyDataLifecycle struct {
	RetentionDays         *int                     `json:"retention_days" yaml:"retention_days"`
	DeletionOnUserRequest *bool                    `json:"deletion_on_user_request" yaml:"deletion_on_user_request"`
	DeletionCascade       []PrivacyDeletionCascade `json:"deletion_cascade,omitempty" yaml:"deletion_cascade,omitempty"`
	AnonymizationOnDelete []PrivacyAnonymization   `json:"anonymization_on_delete,omitempty" yaml:"anonymization_on_delete,omitempty"`
}

type PrivacyDeletionCascade struct {
	ObjectID           string                  `json:"object_id" yaml:"object_id"`
	Strategy           PrivacyDeletionStrategy `json:"strategy" yaml:"strategy"`
	SoftDeleteFirst    *bool                   `json:"soft_delete_first,omitempty" yaml:"soft_delete_first,omitempty"`
	CDNPurgeDelayHours *int                    `json:"cdn_purge_delay_hours,omitempty" yaml:"cdn_purge_delay_hours,omitempty"`
	Description        string                  `json:"description,omitempty" yaml:"description,omitempty"`
}

type PrivacyAnonymization struct {
	Field       string                       `json:"field" yaml:"field"`
	Strategy    PrivacyAnonymizationStrategy `json:"strategy" yaml:"strategy"`
	Placeholder string                       `json:"placeholder,omitempty" yaml:"placeholder,omitempty"`
}

type PrivacyFieldVisibility struct {
	Field       string   `json:"field" yaml:"field"`
	Visibility  []string `json:"visibility" yaml:"visibility"`
	Description string   `json:"description,omitempty" yaml:"description,omitempty"`
}
