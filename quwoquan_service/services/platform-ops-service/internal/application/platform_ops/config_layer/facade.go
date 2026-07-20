package config_layer

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/controlplane"
)

// ErrScopeInvalid / ErrSnapshotNotFound 是快照查询的稳定错误哨兵，
// HTTP adapter 据此映射 metadata errors.yaml 声明的错误码。
var (
	ErrScopeInvalid     = fmt.Errorf("config snapshot scope invalid")
	ErrSnapshotNotFound = fmt.Errorf("config snapshot not found")
)

// Facade 提供 IaC 配置只读快照查询。配置唯一真相源是版本化发布包；
// 平台不提供任何写路径。
type Facade struct {
	source  *SnapshotSource
	catalog *ConfigKeyCatalog
	now     func() time.Time
}

type ConfigSnapshotView struct {
	Domain          string         `json:"domain"`
	Service         string         `json:"service"`
	Environment     string         `json:"environment"`
	Files           []SnapshotFile `json:"files"`
	ReleaseVersions []string       `json:"releaseVersions"`
	MergedSha256    string         `json:"mergedSha256,omitempty"`
	SnapshotSource  string         `json:"snapshotSource"`
}

type ConfigDomainItem struct {
	Domain      string   `json:"domain"`
	Label       string   `json:"label"`
	Services    []string `json:"services,omitempty"`
	Description string   `json:"description"`
}

type ConfigDomainSlice struct {
	Items []ConfigDomainItem `json:"items"`
}

func NewFacade(source *SnapshotSource, catalog *ConfigKeyCatalog) (*Facade, error) {
	if source == nil || catalog == nil {
		return nil, fmt.Errorf("config snapshot facade requires snapshot source and generated key catalog")
	}
	return &Facade{source: source, catalog: catalog, now: time.Now}, nil
}

func (f *Facade) ListConfigKeys(context.Context) []ConfigKeyDescriptor {
	return f.catalog.List()
}

// Resolve 解析 sys.* 有效配置：codegen 键目录 default 叠加发布包 config.yaml
// 顶层平铺 sys.* 覆盖。响应结构与 runtime/controlplane 客户端 wire 对齐。
func (f *Facade) Resolve(_ context.Context, scope controlplane.ConfigResolutionScope) (controlplane.ConfigResolveResponse, error) {
	environment := strings.TrimSpace(scope.Environment)
	service := strings.TrimSpace(scope.Service)
	if environment == "" {
		return controlplane.ConfigResolveResponse{}, fmt.Errorf("%w: resolve requires environment", ErrScopeInvalid)
	}

	values := make([]controlplane.ResolvedConfigValue, 0, len(f.catalog.List()))
	resolved := map[string]controlplane.ResolvedConfigValue{}
	for _, descriptor := range f.catalog.List() {
		resolved[descriptor.Key] = controlplane.ResolvedConfigValue{
			Key:         descriptor.Key,
			Value:       descriptor.Default,
			ScopeLevel:  "global",
			ScopeID:     "all",
			SourceLayer: "config_schema",
			Metadata: map[string]any{
				"owner":      descriptor.Owner,
				"scope":      descriptor.Scope,
				"reload":     descriptor.Reload,
				"risk_level": descriptor.RiskLevel,
			},
		}
	}
	if service != "" {
		overrides, files, err := f.source.SysOverrides(environment, service)
		if err != nil && !os.IsNotExist(err) {
			return controlplane.ConfigResolveResponse{}, err
		}
		sourceLayer := "release-package"
		if len(files) > 0 {
			sourceLayer = files[len(files)-1].Path
		}
		for key, value := range overrides {
			if _, registered := f.catalog.Get(key); !registered && !f.catalog.InNamespace(key) {
				continue
			}
			resolved[key] = controlplane.ResolvedConfigValue{
				Key:         key,
				Value:       value,
				ScopeLevel:  "service",
				ScopeID:     service,
				SourceLayer: sourceLayer,
			}
		}
	}
	for _, item := range resolved {
		values = append(values, item)
	}
	sort.Slice(values, func(i, j int) bool { return values[i].Key < values[j].Key })
	hash := controlplane.EffectiveConfigHash(values)
	return controlplane.ConfigResolveResponse{
		Scope:         controlplane.ConfigResolutionScope{Environment: environment, Service: service},
		ResolvedAt:    f.now().UTC().Format(time.RFC3339),
		EffectiveHash: hash,
		DesiredHash:   hash,
		Values:        values,
		Source:        "release-package",
	}, nil
}

// GetSnapshot 返回单个配置域在指定环境的发布包只读快照。
func (f *Facade) GetSnapshot(_ context.Context, environment, service string) (ConfigSnapshotView, error) {
	environment = strings.TrimSpace(environment)
	service = strings.TrimSpace(service)
	if environment == "" || service == "" {
		return ConfigSnapshotView{}, fmt.Errorf("%w: snapshot requires env and service", ErrScopeInvalid)
	}
	view := ConfigSnapshotView{
		Environment:     environment,
		Service:         service,
		ReleaseVersions: []string{},
		SnapshotSource:  f.source.Mode(),
	}
	switch service {
	case "app":
		view.Domain = "app"
		files, err := f.source.AppConfigFiles(environment)
		if err != nil {
			return ConfigSnapshotView{}, err
		}
		if len(files) == 0 {
			return ConfigSnapshotView{}, ErrSnapshotNotFound
		}
		view.Files = files
	case "data":
		view.Domain = "data"
		files, err := f.source.DataCatalogFiles()
		if err != nil {
			return ConfigSnapshotView{}, err
		}
		if len(files) == 0 {
			return ConfigSnapshotView{}, ErrSnapshotNotFound
		}
		view.Files = files
	default:
		view.Domain = "cloud-service"
		files, err := f.source.ServiceConfigFiles(environment, service)
		if err != nil {
			if os.IsNotExist(err) {
				return ConfigSnapshotView{}, ErrSnapshotNotFound
			}
			return ConfigSnapshotView{}, err
		}
		releases, err := f.source.ReleaseFiles(service)
		if err != nil {
			return ConfigSnapshotView{}, err
		}
		view.Files = append(files, releases...)
		for _, release := range releases {
			name := release.Path
			if idx := strings.LastIndex(name, "/"); idx >= 0 {
				name = name[idx+1:]
			}
			view.ReleaseVersions = append(view.ReleaseVersions, strings.TrimSuffix(name, ".yaml"))
		}
	}
	view.MergedSha256 = mergedDigest(view.Files)
	return view, nil
}

// ListDomains 返回可查看的配置域清单。
func (f *Facade) ListDomains(context.Context) (ConfigDomainSlice, error) {
	services, err := f.source.ListCloudServices()
	if err != nil {
		return ConfigDomainSlice{}, err
	}
	return ConfigDomainSlice{Items: []ConfigDomainItem{
		{
			Domain:      "cloud-service",
			Label:       "云侧领域服务",
			Services:    services,
			Description: "服务 configs/default 与 configs/<env> 树，release 双版本保留（当前灰度与上一版本）",
		},
		{
			Domain:      "app",
			Label:       "端侧 App",
			Services:    []string{"app"},
			Description: "quwoquan_app/configs/<env> 构建期发布配置",
		},
		{
			Domain:      "data",
			Label:       "数据工程",
			Services:    []string{"data"},
			Description: "quwoquan_data control_plane 共享 catalog（发布包内容资产的一部分）",
		},
	}}, nil
}

func mergedDigest(files []SnapshotFile) string {
	if len(files) == 0 {
		return ""
	}
	type digestEntry struct {
		Path   string `json:"path"`
		SHA256 string `json:"sha256"`
	}
	entries := make([]digestEntry, 0, len(files))
	for _, file := range files {
		entries = append(entries, digestEntry{Path: file.Path, SHA256: file.SHA256})
	}
	payload, _ := json.Marshal(entries)
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:])
}
