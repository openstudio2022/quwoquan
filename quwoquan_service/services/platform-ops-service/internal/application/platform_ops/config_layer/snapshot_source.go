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
// 生产模式（configRoot 非空）：读部署渲染出的 config-root 树
//
//	configs/<service>/{default,<env>}/config.yaml
//	configs/app/<env>/*.{yaml,json}
//	releases/config/<service>/<version>.yaml
//	data-catalogs/*.yaml
//
// 开发/测试模式（repoRoot）：直接读仓库内各领域的同一真相源文件。
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
	if s.configRoot == "" {
		return false
	}
	info, err := os.Stat(filepath.Join(s.configRoot, "configs"))
	return err == nil && info.IsDir()
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
	var root string
	if s.usingConfigRoot() {
		root = filepath.Join(s.configRoot, "configs")
	} else {
		root = filepath.Join(s.repoRoot, "quwoquan_service", "services")
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, fmt.Errorf("list cloud services: %w", err)
	}
	services := make([]string, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() || entry.Name() == "app" {
			continue
		}
		if s.usingConfigRoot() {
			services = append(services, entry.Name())
			continue
		}
		if _, err := os.Stat(filepath.Join(root, entry.Name(), "configs", "default", "config.yaml")); err == nil {
			services = append(services, entry.Name())
		}
	}
	sort.Strings(services)
	return services, nil
}

// ServiceConfigFiles 返回云侧服务在指定环境的 default/env 配置文件。
func (s *SnapshotSource) ServiceConfigFiles(environment, service string) ([]SnapshotFile, error) {
	var defaultPath, envPath string
	if s.usingConfigRoot() {
		defaultPath = filepath.Join(s.configRoot, "configs", service, "default", "config.yaml")
		envPath = filepath.Join(s.configRoot, "configs", service, environment, "config.yaml")
	} else {
		base := filepath.Join(s.repoRoot, "quwoquan_service", "services", service, "configs")
		defaultPath = filepath.Join(base, "default", "config.yaml")
		envPath = filepath.Join(base, environment, "config.yaml")
	}
	files := make([]SnapshotFile, 0, 2)
	defaultFile, err := readSnapshotFile(defaultPath, "default")
	if err != nil {
		return nil, err
	}
	if defaultFile != nil {
		files = append(files, *defaultFile)
	}
	envFile, err := readSnapshotFile(envPath, "environment")
	if err != nil {
		return nil, err
	}
	if envFile != nil {
		files = append(files, *envFile)
	}
	if len(files) == 0 {
		return nil, os.ErrNotExist
	}
	return files, nil
}

// ReleaseFiles 返回服务的 release 配置文件（双版本保留：当前灰度与上一版本）。
func (s *SnapshotSource) ReleaseFiles(service string) ([]SnapshotFile, error) {
	var dir string
	if s.usingConfigRoot() {
		dir = filepath.Join(s.configRoot, "releases", "config", service)
	} else {
		dir = filepath.Join(s.repoRoot, "quwoquan_service", "services", service, "configs", "releases")
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("list release configs: %w", err)
	}
	files := make([]SnapshotFile, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".yaml") {
			continue
		}
		file, err := readSnapshotFile(filepath.Join(dir, entry.Name()), "release")
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

// SysOverrides 解析服务 default+env 配置文件顶层平铺的 sys.* 键覆盖。
// 环境层覆盖 default 层；返回 map[key]value。
func (s *SnapshotSource) SysOverrides(environment, service string) (map[string]any, []SnapshotFile, error) {
	files, err := s.ServiceConfigFiles(environment, service)
	if err != nil {
		return nil, nil, err
	}
	overrides := map[string]any{}
	for _, file := range files {
		var doc map[string]any
		if err := yaml.Unmarshal([]byte(file.Content), &doc); err != nil {
			return nil, nil, fmt.Errorf("parse %s: %w", file.Path, err)
		}
		for key, value := range doc {
			if strings.HasPrefix(key, "sys.") {
				overrides[key] = value
			}
		}
	}
	return overrides, files, nil
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
