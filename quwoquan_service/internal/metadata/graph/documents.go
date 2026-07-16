package graph

import (
	"encoding/json"
	"fmt"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

func (g *ContractGraph) DecodeDocument(path string, target any) error {
	normalized := filepath.ToSlash(filepath.Clean(path))
	for _, document := range g.Documents {
		if document.Path != normalized {
			continue
		}
		if err := json.Unmarshal(document.Content, target); err != nil {
			return fmt.Errorf("decode metadata document %s: %w", normalized, err)
		}
		return nil
	}
	return fmt.Errorf("metadata document %s not found in ContractGraph", normalized)
}

// DecodeDocumentYAML 让迁移中的 generator 继续复用 yaml tag，
// 但输入只能来自 ContractGraph 内嵌的规范化 JSON。
func (g *ContractGraph) DecodeDocumentYAML(path string, target any) error {
	normalized := filepath.ToSlash(filepath.Clean(path))
	for _, document := range g.Documents {
		if document.Path != normalized {
			continue
		}
		if err := yaml.Unmarshal(document.Content, target); err != nil {
			return fmt.Errorf("decode metadata document %s: %w", normalized, err)
		}
		return nil
	}
	return fmt.Errorf("metadata document %s not found in ContractGraph", normalized)
}

func (g *ContractGraph) HasDocument(path string) bool {
	normalized := filepath.ToSlash(filepath.Clean(path))
	for _, document := range g.Documents {
		if document.Path == normalized {
			return true
		}
	}
	return false
}

func (g *ContractGraph) DocumentContent(path string) ([]byte, error) {
	normalized := filepath.ToSlash(filepath.Clean(path))
	for _, document := range g.Documents {
		if document.Path == normalized {
			return append([]byte(nil), document.Content...), nil
		}
	}
	return nil, fmt.Errorf("metadata document %s not found in ContractGraph", normalized)
}
