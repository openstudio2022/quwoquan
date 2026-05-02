package reliabletask

import (
	"fmt"
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

type Catalog struct {
	Version                  int                   `yaml:"version"`
	CompatibleRuntimeVersion string                `yaml:"compatibleRuntimeVersion"`
	SchemaVersion            int                   `yaml:"schemaVersion"`
	Modules                  map[string]ModuleSpec `yaml:"modules"`
	Tasks                    map[string]TaskSpec   `yaml:"tasks"`
	Policies                 PolicyCatalog         `yaml:"-"`
}

type ModuleSpec struct {
	Domain                 string   `yaml:"domain"`
	Capabilities           []string `yaml:"capabilities"`
	RequiredStores         []string `yaml:"requiredStores"`
	RequiredQueues         []string `yaml:"requiredQueues"`
	Planes                 []string `yaml:"planes"`
	AllowOnebox            bool     `yaml:"allowOnebox"`
	AllowStandalonePackage bool     `yaml:"allowStandalonePackage"`
}

type TaskSpec struct {
	OwnerDomain          string          `yaml:"ownerDomain"`
	DispatcherModule     string          `yaml:"dispatcherModule"`
	WorkerModule         string          `yaml:"workerModule"`
	Queue                string          `yaml:"queue"`
	PartitionKey         string          `yaml:"partitionKey"`
	PayloadAllowlist     []string        `yaml:"payloadAllowlist"`
	MergePolicy          MergePolicySpec `yaml:"mergePolicy"`
	RetryPolicy          RetryPolicySpec `yaml:"retryPolicy"`
	RetentionPolicyRef   string          `yaml:"retentionPolicyRef"`
	RateLimitPolicyRef   string          `yaml:"rateLimitPolicyRef"`
	RuntimeFailureModule string          `yaml:"runtimeFailureModule"`
}

type MergePolicySpec struct {
	DelayFromNow time.Duration     `yaml:"-"`
	MaxDelay     time.Duration     `yaml:"-"`
	Fields       map[string]string `yaml:"fields"`
}

func (m *MergePolicySpec) UnmarshalYAML(value *yaml.Node) error {
	var decoded struct {
		DelayFromNow string            `yaml:"delayFromNow"`
		MaxDelay     string            `yaml:"maxDelay"`
		Fields       map[string]string `yaml:"fields"`
	}
	if err := value.Decode(&decoded); err != nil {
		return err
	}
	m.Fields = decoded.Fields
	if decoded.DelayFromNow != "" {
		duration, err := time.ParseDuration(decoded.DelayFromNow)
		if err != nil {
			return fmt.Errorf("parse merge delayFromNow %q: %w", decoded.DelayFromNow, err)
		}
		m.DelayFromNow = duration
	}
	if decoded.MaxDelay != "" {
		duration, err := time.ParseDuration(decoded.MaxDelay)
		if err != nil {
			return fmt.Errorf("parse merge maxDelay %q: %w", decoded.MaxDelay, err)
		}
		m.MaxDelay = duration
	}
	return nil
}

type RetryPolicySpec struct {
	MaxAttempts int    `yaml:"maxAttempts"`
	Backoff     string `yaml:"backoff"`
}

func LoadCatalog(path string) (Catalog, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Catalog{}, err
	}
	var catalog Catalog
	if err := yaml.Unmarshal(raw, &catalog); err != nil {
		return Catalog{}, err
	}
	if err := catalog.Validate(); err != nil {
		return Catalog{}, err
	}
	return catalog, nil
}

func LoadCatalogWithPolicies(catalogPath string, policyPath string) (Catalog, error) {
	catalog, err := LoadCatalog(catalogPath)
	if err != nil {
		return Catalog{}, err
	}
	policies, err := LoadPolicyCatalog(policyPath)
	if err != nil {
		return Catalog{}, err
	}
	catalog.Policies = policies
	if err := catalog.ValidatePolicyRefs(); err != nil {
		return Catalog{}, err
	}
	return catalog, nil
}

func (c Catalog) Validate() error {
	if c.Version <= 0 {
		return fmt.Errorf("catalog version is required")
	}
	if len(c.Modules) == 0 {
		return fmt.Errorf("catalog modules are required")
	}
	if len(c.Tasks) == 0 {
		return fmt.Errorf("catalog tasks are required")
	}
	for name, task := range c.Tasks {
		if task.OwnerDomain == "" {
			return fmt.Errorf("task %s ownerDomain is required", name)
		}
		dispatcher, ok := c.Modules[task.DispatcherModule]
		if !ok {
			return fmt.Errorf("task %s dispatcher module %s is not defined", name, task.DispatcherModule)
		}
		worker, ok := c.Modules[task.WorkerModule]
		if !ok {
			return fmt.Errorf("task %s worker module %s is not defined", name, task.WorkerModule)
		}
		if dispatcher.Domain != task.OwnerDomain {
			return fmt.Errorf("task %s dispatcher domain mismatch: %s", name, dispatcher.Domain)
		}
		if worker.Domain != task.OwnerDomain && task.OwnerDomain != "notification" {
			return fmt.Errorf("task %s worker domain mismatch: %s", name, worker.Domain)
		}
		if task.PartitionKey == "" {
			return fmt.Errorf("task %s partitionKey is required", name)
		}
		if len(task.PayloadAllowlist) == 0 {
			return fmt.Errorf("task %s payloadAllowlist is required", name)
		}
		if task.RetryPolicy.MaxAttempts <= 0 {
			return fmt.Errorf("task %s retryPolicy.maxAttempts is required", name)
		}
	}
	return nil
}

func (c Catalog) ValidatePolicyRefs() error {
	if len(c.Policies.Policies) == 0 && len(c.Policies.RateLimits) == 0 {
		return nil
	}
	for name, task := range c.Tasks {
		if _, ok := c.Policies.Policies[task.RetentionPolicyRef]; !ok {
			return fmt.Errorf("task %s retention policy %s is not defined", name, task.RetentionPolicyRef)
		}
		if _, ok := c.Policies.RateLimits[task.RateLimitPolicyRef]; !ok {
			return fmt.Errorf("task %s rate limit policy %s is not defined", name, task.RateLimitPolicyRef)
		}
	}
	return nil
}

func (c Catalog) DeclareRequestForTask(taskType string, aggregateID string, payload map[string]string, trigger string, now time.Time) (DeclareTaskRequest, error) {
	spec, ok := c.Tasks[taskType]
	if !ok {
		return DeclareTaskRequest{}, fmt.Errorf("task %s is not defined", taskType)
	}
	if err := validatePayloadAllowlist(payload, spec.PayloadAllowlist); err != nil {
		return DeclareTaskRequest{}, err
	}
	startAt := now.UTC().Add(spec.MergePolicy.DelayFromNow)
	return DeclareTaskRequest{
		TaskType:        taskType,
		OwnerDomain:     spec.OwnerDomain,
		AggregateType:   spec.PartitionKey,
		AggregateID:     aggregateID,
		DedupeKey:       taskType + ":" + aggregateID,
		IdempotencyKey:  taskType + ":" + aggregateID,
		PartitionKey:    aggregateID,
		Payload:         payload,
		PayloadAllow:    spec.PayloadAllowlist,
		Trigger:         trigger,
		StartAt:         startAt,
		MaxDelayUntil:   now.UTC().Add(spec.MergePolicy.MaxDelay),
		MergeWindow:     spec.MergePolicy.MaxDelay,
		CreatedByModule: spec.DispatcherModule,
	}, nil
}

func (t TaskSpec) RetryPolicyConfig() RetryPolicy {
	policy := DefaultRetryPolicy()
	if t.RetryPolicy.MaxAttempts > 0 {
		policy.MaxAttempts = t.RetryPolicy.MaxAttempts
	}
	return policy
}
