// Package recimpactmeta 是影响力 helpType 注册表
// (contracts/metadata/recommendation/rec_model/impact_help_type_registry.yaml)
// 的唯一解析/校验层，供服务端 Go codegen (tools/codegen_impact) 与
// 端侧 Dart codegen (tools/codegen_app_metadata) 共用同一份解析器（§23 去桥接）。
package recimpactmeta

import (
	"fmt"
	"os"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// Action 是影响力行动建议 {key,label}（summaryAction / evidenceAction / default）。
type Action struct {
	Key   string `yaml:"key"`
	Label string `yaml:"label"`
}

// HelpTypeDef 单条 helpType 注册项。
type HelpTypeDef struct {
	HelpType        string   `yaml:"helpType"`
	IconKey         string   `yaml:"iconKey"`
	SummaryAction   Action   `yaml:"summaryAction"`
	EvidenceAction  Action   `yaml:"evidenceAction"`
	BehaviorActions []string `yaml:"behaviorActions"`
	Status          string   `yaml:"status"`
}

// Defaults 未登记 helpType 的防御默认。
type Defaults struct {
	IconKey        string `yaml:"iconKey"`
	Tone           string `yaml:"tone"`
	SummaryAction  Action `yaml:"summaryAction"`
	EvidenceAction Action `yaml:"evidenceAction"`
}

// Registry 镜像 impact_help_type_registry.yaml。
type Registry struct {
	ToneLegend   []string          `yaml:"toneLegend"`
	ToneByIcon   map[string]string `yaml:"toneByIconKey"`
	HelpTypes    []HelpTypeDef     `yaml:"helpTypes"`
	Defaults     Defaults          `yaml:"defaults"`
}

// Read 读取并反序列化注册表 yaml。
func Read(path string) (*Registry, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var out Registry
	if err := yaml.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Validate 校验注册表结构完整与闭集自洽。
func Validate(r *Registry) error {
	if len(r.HelpTypes) == 0 {
		return fmt.Errorf("helpTypes is empty")
	}
	if len(r.ToneByIcon) == 0 {
		return fmt.Errorf("toneByIconKey is empty")
	}
	toneSet := toStringSet(r.ToneLegend)
	if len(toneSet) == 0 {
		return fmt.Errorf("toneLegend is empty")
	}
	for icon, tone := range r.ToneByIcon {
		if _, ok := toneSet[tone]; !ok {
			return fmt.Errorf("toneByIconKey[%q] tone %q not in toneLegend", icon, tone)
		}
	}
	seen := map[string]struct{}{}
	for _, h := range r.HelpTypes {
		if strings.TrimSpace(h.HelpType) == "" {
			return fmt.Errorf("helpType entry missing helpType")
		}
		if _, dup := seen[h.HelpType]; dup {
			return fmt.Errorf("duplicate helpType %q", h.HelpType)
		}
		seen[h.HelpType] = struct{}{}
		if strings.TrimSpace(h.IconKey) == "" {
			return fmt.Errorf("helpType %q missing iconKey", h.HelpType)
		}
		if _, ok := r.ToneByIcon[h.IconKey]; !ok {
			return fmt.Errorf("helpType %q iconKey %q not in toneByIconKey closed set", h.HelpType, h.IconKey)
		}
		if strings.TrimSpace(h.SummaryAction.Key) == "" || strings.TrimSpace(h.SummaryAction.Label) == "" {
			return fmt.Errorf("helpType %q summaryAction must have key+label", h.HelpType)
		}
		if strings.TrimSpace(h.EvidenceAction.Key) == "" || strings.TrimSpace(h.EvidenceAction.Label) == "" {
			return fmt.Errorf("helpType %q evidenceAction must have key+label", h.HelpType)
		}
		if strings.TrimSpace(h.Status) == "" {
			return fmt.Errorf("helpType %q missing status", h.HelpType)
		}
	}
	if strings.TrimSpace(r.Defaults.IconKey) == "" {
		return fmt.Errorf("defaults.iconKey is empty")
	}
	if _, ok := r.ToneByIcon[r.Defaults.IconKey]; !ok {
		return fmt.Errorf("defaults.iconKey %q not in toneByIconKey closed set", r.Defaults.IconKey)
	}
	if _, ok := toneSet[r.Defaults.Tone]; !ok {
		return fmt.Errorf("defaults.tone %q not in toneLegend", r.Defaults.Tone)
	}
	return nil
}

// SortedIconKeys 返回 toneByIconKey 的有序键（确定性 codegen 输出）。
func (r *Registry) SortedIconKeys() []string {
	keys := make([]string, 0, len(r.ToneByIcon))
	for k := range r.ToneByIcon {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func toStringSet(values []string) map[string]struct{} {
	out := make(map[string]struct{}, len(values))
	for _, v := range values {
		out[v] = struct{}{}
	}
	return out
}
