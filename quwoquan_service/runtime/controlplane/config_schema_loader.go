package controlplane

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type configSchemaFile struct {
	Configs []configSchemaEntry `yaml:"configs"`
}

type configSchemaEntry struct {
	Key        string `yaml:"key"`
	Type       string `yaml:"type"`
	Owner      string `yaml:"owner"`
	Default    any    `yaml:"default"`
	Scope      string `yaml:"scope"`
	Reload     string `yaml:"reload"`
	RiskLevel  string `yaml:"risk_level"`
	UIEditable bool   `yaml:"ui_editable"`
	// KeyNamespace 标记该条目为「前缀命名空间」而非具体 key（如运营态错误提示语
	// override：完整 key 形如 sys.error_message.<code>.<locale> 动态生成）。
	// 命名空间条目仅用于治理/UI/reload 语义登记，不作为具体 resolved 默认值下发。
	KeyNamespace bool `yaml:"key_namespace"`
}

func LoadConfigKeysFromSchema(path string) ([]Document, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config_schema.yaml: %w", err)
	}
	var schema configSchemaFile
	if err := yaml.Unmarshal(data, &schema); err != nil {
		return nil, fmt.Errorf("parse config_schema.yaml: %w", err)
	}
	docs := make([]Document, 0, len(schema.Configs))
	for _, entry := range schema.Configs {
		if entry.KeyNamespace {
			continue
		}
		docs = append(docs, Document{
			"id":         entry.Key,
			"key":        entry.Key,
			"default":    entry.Default,
			"scope":      entry.Scope,
			"reload":     entry.Reload,
			"risk_level": entry.RiskLevel,
			"owner":      entry.Owner,
		})
	}
	return docs, nil
}
