package runtimeobservability

import (
	"fmt"
	"strings"
)

const (
	KVStrategyAllow = "allow"
	KVStrategyMask  = "mask"
	KVStrategyHash  = "hash"
)

type KVRule struct {
	Key      string
	Strategy string
}

type KVPolicy struct {
	Model     string
	Operation string
	Input     []KVRule
	Output    []KVRule
}

type KVMetadataFilter struct {
	policyMap map[string]KVPolicy
}

func NewKVMetadataFilter(policies []KVPolicy) *KVMetadataFilter {
	m := make(map[string]KVPolicy, len(policies))
	for _, p := range policies {
		key := policyKey(p.Model, p.Operation)
		m[key] = p
	}
	return &KVMetadataFilter{policyMap: m}
}

func (f *KVMetadataFilter) FilterInput(model string, operation string, payload map[string]any) (map[string]any, error) {
	return f.filter(model, operation, payload, true)
}

func (f *KVMetadataFilter) FilterOutput(model string, operation string, payload map[string]any) (map[string]any, error) {
	return f.filter(model, operation, payload, false)
}

func (f *KVMetadataFilter) filter(model string, operation string, payload map[string]any, isInput bool) (map[string]any, error) {
	policy, ok := f.policyMap[policyKey(model, operation)]
	if !ok {
		// default minimal strategy: no metadata entry -> no output
		return map[string]any{}, nil
	}

	rules := policy.Output
	if isInput {
		rules = policy.Input
	}

	output := make(map[string]any, len(rules))
	for _, rule := range rules {
		value, exists := payload[rule.Key]
		if !exists {
			continue
		}
		masked, err := applyKVStrategy(rule.Strategy, value)
		if err != nil {
			return nil, fmt.Errorf("invalid kv strategy for %s: %w", rule.Key, err)
		}
		output[rule.Key] = masked
	}
	return output, nil
}

func policyKey(model string, operation string) string {
	return strings.TrimSpace(model) + "::" + strings.TrimSpace(operation)
}

func applyKVStrategy(strategy string, value any) (any, error) {
	switch strategy {
	case KVStrategyAllow:
		return value, nil
	case KVStrategyMask:
		return "***", nil
	case KVStrategyHash:
		return "hash_redacted", nil
	default:
		return nil, fmt.Errorf("unsupported strategy: %s", strategy)
	}
}
