package skill

import (
	"encoding/json"
	"os"
)

type Loader interface {
	Load() ([]Manifest, error)
}

type StaticLoader struct {
	Manifests []Manifest
}

func (l StaticLoader) Load() ([]Manifest, error) {
	if len(l.Manifests) == 0 {
		return []Manifest{DefaultManifest()}, nil
	}
	return append([]Manifest{}, l.Manifests...), nil
}

type JSONFileLoader struct {
	Path string
}

func (l JSONFileLoader) Load() ([]Manifest, error) {
	if l.Path == "" {
		return []Manifest{DefaultManifest()}, nil
	}
	raw, err := os.ReadFile(l.Path)
	if err != nil {
		return nil, err
	}
	var manifests []Manifest
	if err := json.Unmarshal(raw, &manifests); err != nil {
		return nil, err
	}
	return manifests, nil
}
