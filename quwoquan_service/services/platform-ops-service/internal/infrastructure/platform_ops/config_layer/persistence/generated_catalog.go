package persistence

import (
	"fmt"
	"sort"
	"strings"

	"quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/model"
	"quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/ports"
)

type GeneratedConfigKeyCatalog struct {
	byKey map[string]ports.ConfigKeyDescriptor
	items []ports.ConfigKeyDescriptor
}

func NewGeneratedConfigKeyCatalog(document map[string]any) (*GeneratedConfigKeyCatalog, error) {
	rawConfigs, ok := document["configs"].([]any)
	if !ok || len(rawConfigs) == 0 {
		return nil, fmt.Errorf("generated platform config schema must contain configs")
	}
	catalog := &GeneratedConfigKeyCatalog{byKey: make(map[string]ports.ConfigKeyDescriptor, len(rawConfigs))}
	for index, raw := range rawConfigs {
		config, ok := raw.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("generated config[%d] must be an object", index)
		}
		descriptor, err := decodeConfigKeyDescriptor(config)
		if err != nil {
			return nil, fmt.Errorf("generated config[%d]: %w", index, err)
		}
		if _, exists := catalog.byKey[descriptor.Key]; exists {
			return nil, fmt.Errorf("duplicate generated config key %q", descriptor.Key)
		}
		catalog.byKey[descriptor.Key] = descriptor
		catalog.items = append(catalog.items, descriptor)
	}
	sort.Slice(catalog.items, func(i, j int) bool { return catalog.items[i].Key < catalog.items[j].Key })
	return catalog, nil
}

func (c *GeneratedConfigKeyCatalog) Get(key string) (ports.ConfigKeyDescriptor, bool) {
	descriptor, found := c.byKey[strings.TrimSpace(key)]
	return descriptor, found
}

func (c *GeneratedConfigKeyCatalog) List() []ports.ConfigKeyDescriptor {
	return append([]ports.ConfigKeyDescriptor(nil), c.items...)
}

func decodeConfigKeyDescriptor(raw map[string]any) (ports.ConfigKeyDescriptor, error) {
	key := strings.TrimSpace(fmt.Sprint(raw["key"]))
	kind := model.ValueKind(strings.TrimSpace(fmt.Sprint(raw["type"])))
	if key == "" {
		return ports.ConfigKeyDescriptor{}, fmt.Errorf("key is required")
	}
	value, err := generatedDefaultValue(kind, raw["default"])
	if err != nil {
		return ports.ConfigKeyDescriptor{}, fmt.Errorf("config %s default: %w", key, err)
	}
	return ports.ConfigKeyDescriptor{
		Key: key, Kind: kind, Owner: strings.TrimSpace(fmt.Sprint(raw["owner"])),
		Scope: strings.TrimSpace(fmt.Sprint(raw["scope"])), Reload: strings.TrimSpace(fmt.Sprint(raw["reload"])),
		Rollout: strings.TrimSpace(fmt.Sprint(raw["rollout"])), RiskLevel: strings.TrimSpace(fmt.Sprint(raw["risk_level"])),
		UIEditable: raw["ui_editable"] == true, Default: value,
	}, nil
}

func generatedDefaultValue(kind model.ValueKind, raw any) (model.ConfigValue, error) {
	switch kind {
	case model.ValueKindString:
		value := ""
		if raw != nil {
			value = fmt.Sprint(raw)
		}
		return model.ConfigValue{Kind: kind, StringValue: &value}, nil
	case model.ValueKindInt:
		value, ok := asInt64(raw)
		if !ok {
			return model.ConfigValue{}, fmt.Errorf("must be an integer")
		}
		return model.ConfigValue{Kind: kind, IntValue: &value}, nil
	case model.ValueKindFloat:
		value, ok := asFloat64(raw)
		if !ok {
			return model.ConfigValue{}, fmt.Errorf("must be a number")
		}
		return model.ConfigValue{Kind: kind, FloatValue: &value}, nil
	case model.ValueKindBool:
		value, ok := raw.(bool)
		if !ok {
			return model.ConfigValue{}, fmt.Errorf("must be a boolean")
		}
		return model.ConfigValue{Kind: kind, BoolValue: &value}, nil
	default:
		return model.ConfigValue{}, fmt.Errorf("unsupported kind %q", kind)
	}
}

func asInt64(value any) (int64, bool) {
	switch typed := value.(type) {
	case int:
		return int64(typed), true
	case int64:
		return typed, true
	case float64:
		if typed == float64(int64(typed)) {
			return int64(typed), true
		}
	}
	return 0, false
}

func asFloat64(value any) (float64, bool) {
	switch typed := value.(type) {
	case float64:
		return typed, true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	}
	return 0, false
}

var _ ports.ConfigKeyCatalog = (*GeneratedConfigKeyCatalog)(nil)
