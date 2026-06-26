package main

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

func readShared(path string) (*sharedTypes, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed sharedTypes
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readFields(path string) (*fieldsFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed fieldsFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readService(path string) (*serviceFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed serviceFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readIntegrationLocationService(path string) (*integrationLocationServiceFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed integrationLocationServiceFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readProjection(path string) (*projectionFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed projectionFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

// collectProjectionReadModelDartClass 建立 projection read_model -> client_projection.dart_class
// 的全仓索引（跨域可见），供 operation response_body 解析其端侧 DTO 类名。
// 同时把 dart_class 自身登记为键，兼容 response_body 直接写 dart_class 的情况。
func collectProjectionReadModelDartClass(metadataDir string) (map[string]string, error) {
	index := map[string]string{}
	err := filepath.WalkDir(metadataDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || !strings.HasSuffix(d.Name(), ".yaml") {
			return nil
		}
		if filepath.Base(filepath.Dir(path)) != "projections" {
			return nil
		}
		p, readErr := readProjection(path)
		if readErr != nil {
			return nil
		}
		dartClass := strings.TrimSpace(p.ClientProjection.DartClass)
		if dartClass == "" {
			return nil
		}
		if rm := strings.TrimSpace(p.ReadModel); rm != "" {
			index[rm] = dartClass
		}
		index[dartClass] = dartClass
		return nil
	})
	return index, err
}

// ── builders ──────────────────────────────────────────────────────────────────

func collectDomainServiceRoutes(metadataDir string) (map[string][]routeDef, error) {
	grouped := map[string][]routeDef{}
	seen := map[string]bool{}
	err := filepath.WalkDir(metadataDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || d.Name() != "service.yaml" {
			return nil
		}
		service, readErr := readService(path)
		if readErr != nil {
			return readErr
		}
		domain := strings.TrimSpace(service.Service.Domain)
		if domain == "" {
			return nil
		}
		for _, route := range service.APIRoutes {
			if strings.TrimSpace(route.Operation) == "" || strings.TrimSpace(route.Path) == "" {
				continue
			}
			key := domain + ":" + route.Operation
			if seen[key] {
				continue
			}
			seen[key] = true
			grouped[domain] = append(grouped[domain], route)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	for domain := range grouped {
		sort.Slice(grouped[domain], func(i, j int) bool {
			return grouped[domain][i].Operation < grouped[domain][j].Operation
		})
	}
	return grouped, nil
}

func readErrors(path string) (*errorsFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed errorsFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readMergedErrors(paths []string) (*errorsFile, error) {
	merged := &errorsFile{}
	for _, path := range paths {
		ef, err := readErrors(path)
		if err != nil {
			return nil, err
		}
		if merged.Domain == "" {
			merged.Domain = ef.Domain
		}
		merged.Errors = append(merged.Errors, ef.Errors...)
	}
	return merged, nil
}

func readUserDomainErrors(metadataDir string) (*errorsFile, error) {
	root := filepath.Join(metadataDir, "user")
	var paths []string
	if err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		if filepath.Base(path) == "errors.yaml" {
			paths = append(paths, path)
		}
		return nil
	}); err != nil {
		return nil, err
	}
	sort.Strings(paths)
	if len(paths) == 0 {
		return nil, fmt.Errorf("no user errors metadata found under %s", root)
	}
	return readMergedErrors(paths)
}

func readBehaviors(path string) (*behaviorsFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed behaviorsFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readPrivacy(path string) (*privacyFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed privacyFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readUIConfig(path string) (*uiConfigFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed uiConfigFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readRequestContext(path string) (*requestContextFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed requestContextFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readAppRoutes(path string) (*appRoutesFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed appRoutesFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readUISurfaces(path string) (*uiSurfacesFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed uiSurfacesFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readSearchContract(path string) (*searchContractFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed searchContractFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

func readSearchObjects(path string) (*searchObjectsFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var parsed searchObjectsFile
	return &parsed, yaml.Unmarshal(data, &parsed)
}

// ── new cross-cutting renderers ───────────────────────────────────────────────
