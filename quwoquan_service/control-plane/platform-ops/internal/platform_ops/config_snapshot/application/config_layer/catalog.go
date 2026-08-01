package config_layer

import (
	"fmt"
	"sort"
	"strings"
)

// ConfigKeyDescriptor 描述 codegen 键目录中的单个配置键治理语义。
// IaC 收口后所有键均不可在线编辑（uiEditable 恒为 false），值只随发布包变化。
type ConfigKeyDescriptor struct {
	Key        string `json:"key"`
	Kind       string `json:"kind"`
	Owner      string `json:"owner"`
	Scope      string `json:"scope"`
	Reload     string `json:"reload"`
	Rollout    string `json:"rollout"`
	RiskLevel  string `json:"riskLevel"`
	UIEditable bool   `json:"uiEditable"`
	Default    any    `json:"default"`
}

type ConfigKeyCatalog struct {
	byKey      map[string]ConfigKeyDescriptor
	items      []ConfigKeyDescriptor
	namespaces []string
}

func NewConfigKeyCatalog(document map[string]any) (*ConfigKeyCatalog, error) {
	rawConfigs, ok := document["configs"].([]any)
	if !ok || len(rawConfigs) == 0 {
		return nil, fmt.Errorf("generated platform config schema must contain configs")
	}
	catalog := &ConfigKeyCatalog{byKey: make(map[string]ConfigKeyDescriptor, len(rawConfigs))}
	for index, raw := range rawConfigs {
		config, ok := raw.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("generated config[%d] must be an object", index)
		}
		key := strings.TrimSpace(fmt.Sprint(config["key"]))
		if key == "" {
			return nil, fmt.Errorf("generated config[%d]: key is required", index)
		}
		if config["key_namespace"] == true {
			catalog.namespaces = append(catalog.namespaces, key+".")
			continue
		}
		if _, exists := catalog.byKey[key]; exists {
			return nil, fmt.Errorf("duplicate generated config key %q", key)
		}
		descriptor := ConfigKeyDescriptor{
			Key:        key,
			Kind:       strings.TrimSpace(fmt.Sprint(config["type"])),
			Owner:      strings.TrimSpace(fmt.Sprint(config["owner"])),
			Scope:      strings.TrimSpace(fmt.Sprint(config["scope"])),
			Reload:     strings.TrimSpace(fmt.Sprint(config["reload"])),
			Rollout:    strings.TrimSpace(fmt.Sprint(config["rollout"])),
			RiskLevel:  strings.TrimSpace(fmt.Sprint(config["risk_level"])),
			UIEditable: config["ui_editable"] == true,
			Default:    config["default"],
		}
		catalog.byKey[key] = descriptor
		catalog.items = append(catalog.items, descriptor)
	}
	sort.Slice(catalog.items, func(i, j int) bool { return catalog.items[i].Key < catalog.items[j].Key })
	return catalog, nil
}

func (c *ConfigKeyCatalog) Get(key string) (ConfigKeyDescriptor, bool) {
	descriptor, found := c.byKey[strings.TrimSpace(key)]
	return descriptor, found
}

func (c *ConfigKeyCatalog) List() []ConfigKeyDescriptor {
	return append([]ConfigKeyDescriptor(nil), c.items...)
}

// InNamespace 判断 key 是否落在登记的前缀命名空间内
// （如 sys.error_message.<code>.<locale> 动态键）。
func (c *ConfigKeyCatalog) InNamespace(key string) bool {
	key = strings.TrimSpace(key)
	for _, prefix := range c.namespaces {
		if strings.HasPrefix(key, prefix) {
			return true
		}
	}
	return false
}
