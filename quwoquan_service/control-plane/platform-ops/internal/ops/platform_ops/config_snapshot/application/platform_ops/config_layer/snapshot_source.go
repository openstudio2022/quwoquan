package config_layer

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// SnapshotSource 是 IaC 配置只读快照的文件系统数据源。
//
// 生产模式（configRoot 非空）：读服务自治包渲染出的 config-root 树
//
//	<service>.yaml
//	configs/app/<env>/*.{yaml,json}
//	data-catalogs/*.yaml
//
// 开发/测试模式（repoRoot）：直接读服务自治 environments/<env>/config.yaml。
type SnapshotSource struct {
	configRoot string
	repoRoot   string
}

type SnapshotFile struct {
	Path    string `json:"path"`
	Role    string `json:"role"`
	SHA256  string `json:"sha256"`
	Content string `json:"content"`
}

func NewSnapshotSource(configRoot, repoRoot string) (*SnapshotSource, error) {
	configRoot = strings.TrimSpace(configRoot)
	repoRoot = strings.TrimSpace(repoRoot)
	if configRoot == "" && repoRoot == "" {
		return nil, fmt.Errorf("config snapshot source requires CONFIG_ROOT or repo root")
	}
	return &SnapshotSource{configRoot: configRoot, repoRoot: repoRoot}, nil
}

func (s *SnapshotSource) usingConfigRoot() bool {
	return s.configRoot != ""
}

// Mode 返回快照数据源模式，供响应 snapshotSource 字段与诊断使用。
func (s *SnapshotSource) Mode() string {
	if s.usingConfigRoot() {
		return "config-root"
	}
	return "repo"
}

// ListCloudServices 列出可查看配置的云侧服务。
func (s *SnapshotSource) ListCloudServices() ([]string, error) {
	services := map[string]struct{}{}
	if s.usingConfigRoot() {
		entries, err := os.ReadDir(s.configRoot)
		if err != nil {
			return nil, fmt.Errorf("list effective service configs: %w", err)
		}
		for _, entry := range entries {
			if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".yaml") {
				services[strings.TrimSuffix(entry.Name(), ".yaml")] = struct{}{}
			}
		}
	} else {
		root := filepath.Join(s.repoRoot, "quwoquan_service", "services")
		entries, err := os.ReadDir(root)
		if err != nil {
			return nil, fmt.Errorf("list autonomous services: %w", err)
		}
		for _, entry := range entries {
			if entry.IsDir() {
				services[entry.Name()] = struct{}{}
			}
		}
		services["platform-ops-service"] = struct{}{}
	}
	result := make([]string, 0, len(services))
	for service := range services {
		result = append(result, service)
	}
	sort.Strings(result)
	return result, nil
}

// ServiceConfigFiles 返回仓库中的服务自治环境覆盖；生产只消费有效配置快照。
func (s *SnapshotSource) ServiceConfigFiles(environment, service string) ([]SnapshotFile, error) {
	if s.usingConfigRoot() {
		return nil, nil
	}
	serviceRoot := filepath.Join(s.repoRoot, "quwoquan_service", "services", service)
	if service == "platform-ops-service" {
		serviceRoot = filepath.Join(s.repoRoot, "quwoquan_service", "control-plane", "platform-ops")
	}
	path := filepath.Join(serviceRoot, "environments", environment, "config.yaml")
	file, err := readSnapshotFile(path, "environment-override")
	if err != nil {
		return nil, err
	}
	if file == nil {
		return nil, os.ErrNotExist
	}
	return []SnapshotFile{*file}, nil
}

// ReleaseFiles 返回服务包中唯一的有效配置；仓库模式不存在派生 release 真相源。
func (s *SnapshotSource) ReleaseFiles(environment, service string) ([]SnapshotFile, error) {
	_ = environment
	if s.usingConfigRoot() {
		file, err := readSnapshotFile(
			filepath.Join(s.configRoot, service+".yaml"),
			"effective-config",
		)
		if err != nil {
			return nil, err
		}
		if file == nil {
			return nil, nil
		}
		return []SnapshotFile{*file}, nil
	}
	return nil, nil
}

// AppConfigFiles 返回端侧 App 在指定环境的发布配置文件。
func (s *SnapshotSource) AppConfigFiles(environment string) ([]SnapshotFile, error) {
	var dir string
	if s.usingConfigRoot() {
		dir = filepath.Join(s.configRoot, "configs", "app", environment)
	} else {
		dir = filepath.Join(s.repoRoot, "quwoquan_app", "configs", environment)
	}
	return readSnapshotDir(dir, "app-config")
}

// DataCatalogFiles 返回数据工程共享 catalog 配置文件。
func (s *SnapshotSource) DataCatalogFiles() ([]SnapshotFile, error) {
	var dir string
	if s.usingConfigRoot() {
		dir = filepath.Join(s.configRoot, "data-catalogs")
	} else {
		dir = filepath.Join(s.repoRoot, "quwoquan_data", "control_plane", "_shared", "catalogs")
	}
	return readSnapshotDir(dir, "data-catalog")
}

// SysOverrides 解析服务自治 overrides；生产从唯一有效配置快照还原 sys.* 键。
func (s *SnapshotSource) SysOverrides(environment, service string) (map[string]any, []SnapshotFile, error) {
	files, err := s.ServiceConfigFiles(environment, service)
	if err != nil {
		return nil, nil, err
	}
	if s.usingConfigRoot() {
		files, err = s.ReleaseFiles(environment, service)
		if err != nil {
			return nil, nil, err
		}
		if len(files) == 0 {
			return nil, nil, os.ErrNotExist
		}
		var doc map[string]any
		if err := yaml.Unmarshal([]byte(files[len(files)-1].Content), &doc); err != nil {
			return nil, nil, fmt.Errorf("parse %s: %w", files[len(files)-1].Path, err)
		}
		overrides := map[string]any{}
		flattenConfig(overrides, "sys."+service, doc)
		return overrides, []SnapshotFile{files[len(files)-1]}, nil
	}
	overrides := map[string]any{}
	for _, file := range files {
		var doc map[string]any
		if err := yaml.Unmarshal([]byte(file.Content), &doc); err != nil {
			return nil, nil, fmt.Errorf("parse %s: %w", file.Path, err)
		}
		values, ok := doc["overrides"].(map[string]any)
		if !ok && doc["overrides"] != nil {
			return nil, nil, fmt.Errorf("parse %s: overrides must be a mapping", file.Path)
		}
		for key, value := range values {
			if strings.HasPrefix(key, "sys."+service+".") {
				overrides[key] = value
			}
		}
	}
	return overrides, files, nil
}

func flattenConfig(target map[string]any, prefix string, value map[string]any) {
	for key, item := range value {
		path := prefix + "." + key
		if nested, ok := item.(map[string]any); ok {
			flattenConfig(target, path, nested)
			continue
		}
		target[path] = item
	}
}

func readSnapshotFile(path, role string) (*SnapshotFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("read config file %s: %w", path, err)
	}
	digest := sha256.Sum256(data)
	return &SnapshotFile{
		Path:    path,
		Role:    role,
		SHA256:  hex.EncodeToString(digest[:]),
		Content: string(data),
	}, nil
}

func readSnapshotDir(dir, role string) ([]SnapshotFile, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("list config dir %s: %w", dir, err)
	}
	files := make([]SnapshotFile, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if !strings.HasSuffix(name, ".yaml") && !strings.HasSuffix(name, ".yml") && !strings.HasSuffix(name, ".json") {
			continue
		}
		file, err := readSnapshotFile(filepath.Join(dir, name), role)
		if err != nil {
			return nil, err
		}
		if file != nil {
			files = append(files, *file)
		}
	}
	sort.Slice(files, func(i, j int) bool { return files[i].Path < files[j].Path })
	return files, nil
}
