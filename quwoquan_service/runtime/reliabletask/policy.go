package reliabletask

import (
	"fmt"
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

type PolicyCatalog struct {
	Version    int                        `yaml:"version"`
	Policies   map[string]RetentionPolicy `yaml:"policies"`
	RateLimits map[string]RateLimitPolicy `yaml:"rateLimits"`
}

type RetentionPolicy struct {
	Outbox         RetentionBucket `yaml:"outbox"`
	Task           RetentionBucket `yaml:"task"`
	Notification   RetentionBucket `yaml:"notification"`
	DeliveryLedger RetentionBucket `yaml:"deliveryLedger"`
	DLQ            DLQPolicy       `yaml:"dlq"`
}

type RetentionBucket struct {
	DispatchedTTL time.Duration `yaml:"-"`
	FailedTTL     time.Duration `yaml:"-"`
	DoneTTL       time.Duration `yaml:"-"`
	DeadTTL       time.Duration `yaml:"-"`
	DeliveredTTL  time.Duration `yaml:"-"`
	ArchiveAfter  time.Duration `yaml:"-"`
}

func (b *RetentionBucket) UnmarshalYAML(value *yaml.Node) error {
	var decoded map[string]string
	if err := value.Decode(&decoded); err != nil {
		return err
	}
	var err error
	if b.DispatchedTTL, err = parseOptionalDuration(decoded["dispatchedTtl"]); err != nil {
		return fmt.Errorf("parse dispatchedTtl: %w", err)
	}
	if b.FailedTTL, err = parseOptionalDuration(decoded["failedTtl"]); err != nil {
		return fmt.Errorf("parse failedTtl: %w", err)
	}
	if b.DoneTTL, err = parseOptionalDuration(decoded["doneTtl"]); err != nil {
		return fmt.Errorf("parse doneTtl: %w", err)
	}
	if b.DeadTTL, err = parseOptionalDuration(decoded["deadTtl"]); err != nil {
		return fmt.Errorf("parse deadTtl: %w", err)
	}
	if b.DeliveredTTL, err = parseOptionalDuration(decoded["deliveredTtl"]); err != nil {
		return fmt.Errorf("parse deliveredTtl: %w", err)
	}
	if b.ArchiveAfter, err = parseOptionalDuration(decoded["archiveAfter"]); err != nil {
		return fmt.Errorf("parse archiveAfter: %w", err)
	}
	return nil
}

type DLQPolicy struct {
	TTL                        time.Duration `yaml:"-"`
	RequiresManualRecoveryPlan bool          `yaml:"requiresManualRecoveryPlan"`
}

func (p *DLQPolicy) UnmarshalYAML(value *yaml.Node) error {
	var decoded struct {
		TTL                        string `yaml:"ttl"`
		RequiresManualRecoveryPlan bool   `yaml:"requiresManualRecoveryPlan"`
	}
	if err := value.Decode(&decoded); err != nil {
		return err
	}
	ttl, err := parseOptionalDuration(decoded.TTL)
	if err != nil {
		return fmt.Errorf("parse dlq ttl: %w", err)
	}
	p.TTL = ttl
	p.RequiresManualRecoveryPlan = decoded.RequiresManualRecoveryPlan
	return nil
}

type RateLimitPolicy struct {
	DispatchPerSecond int    `yaml:"dispatchPerSecond"`
	ClaimPerSecond    int    `yaml:"claimPerSecond"`
	RetryPerSecond    int    `yaml:"retryPerSecond"`
	Priority          string `yaml:"priority"`
}

func LoadPolicyCatalog(path string) (PolicyCatalog, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return PolicyCatalog{}, err
	}
	var catalog PolicyCatalog
	if err := yaml.Unmarshal(raw, &catalog); err != nil {
		return PolicyCatalog{}, err
	}
	if err := catalog.Validate(); err != nil {
		return PolicyCatalog{}, err
	}
	return catalog, nil
}

func (p PolicyCatalog) Validate() error {
	if p.Version <= 0 {
		return fmt.Errorf("policy catalog version is required")
	}
	if len(p.Policies) == 0 {
		return fmt.Errorf("retention policies are required")
	}
	if len(p.RateLimits) == 0 {
		return fmt.Errorf("rate limit policies are required")
	}
	for name, policy := range p.Policies {
		if policy.DLQ.TTL <= 0 {
			return fmt.Errorf("retention policy %s dlq ttl is required", name)
		}
	}
	for name, policy := range p.RateLimits {
		if policy.DispatchPerSecond <= 0 || policy.ClaimPerSecond <= 0 || policy.RetryPerSecond <= 0 {
			return fmt.Errorf("rate limit policy %s requires positive limits", name)
		}
	}
	return nil
}

func parseOptionalDuration(raw string) (time.Duration, error) {
	if raw == "" {
		return 0, nil
	}
	return time.ParseDuration(raw)
}
