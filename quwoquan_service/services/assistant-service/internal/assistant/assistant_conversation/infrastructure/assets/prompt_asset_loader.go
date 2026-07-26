package assets

import (
	"encoding/json"
	"os"
)

type PromptAssetLoader struct {
	Path string
}

func (l PromptAssetLoader) Load() (map[string]string, error) {
	if l.Path == "" {
		return map[string]string{}, nil
	}
	raw, err := os.ReadFile(l.Path)
	if err != nil {
		return nil, err
	}
	var templates map[string]string
	if err := json.Unmarshal(raw, &templates); err != nil {
		return nil, err
	}
	return templates, nil
}
