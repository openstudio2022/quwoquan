// Package recintersectionmeta 是交集 kind 注册表
// (services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml)
// 的唯一解析/校验层，供端侧 Dart codegen (tools/codegen_app_metadata) 与
// 服务端 Go codegen (tools/codegen_rec_intersection) 共用同一份解析器，
// 避免「两个生成器各写一份 registry struct」的第二真相源。
package recintersectionmeta

import (
	"fmt"
	"strings"

	"gopkg.in/yaml.v3"
)

// Registry 镜像 intersection_kind_registry.yaml 中驱动端云 codegen 的部分。
// registry 是 kind→(iconKey/objectKind/countObjectKind/dimensions/evidenceRank/
// actionHints/tone/lifecycleApplicable/vertical) 与四闭集 + objectKinds + actionLabelByKey
// 的唯一真相源；本包是契约到端(Dart)与云(Go)的唯一桥，禁止手写 kind switch 第二份。
type Registry struct {
	Dimensions         []string                 `yaml:"dimensions"`
	LifecycleStates    []string                 `yaml:"lifecycleStates"`
	Verticals          []string                 `yaml:"verticals"`
	Moments            []string                 `yaml:"moments"`
	GateKeys           []string                 `yaml:"gateKeys"`
	FeedbackKinds      []string                 `yaml:"feedbackKinds"`
	ActionDispatch     []string                 `yaml:"actionDispatch"`
	ObjectKinds        []ObjectKindDef          `yaml:"objectKinds"`
	VisualToneByIcon   map[string]string        `yaml:"visualToneByIconKey"`
	IconKeyLegend      map[string]string        `yaml:"iconKeyLegend"`
	IconKeyByDimension map[string]string        `yaml:"iconKeyByDimension"`
	ActionHintLegend   map[string]string        `yaml:"actionHintLegend"`
	ActionLabelByKey   map[string]string        `yaml:"actionLabelByKey"`
	ActionKeyMeta      map[string]ActionKeyMeta `yaml:"actionKeyMeta"`
	ActionHintsByKind  map[string][]string      `yaml:"actionHintsByKind"`
	Kinds              []KindDef                `yaml:"kinds"`
}

// ActionKeyMeta 是单个 actionKey 的行动阶梯元数据（§24 M0.1/M0.3/M0.7）：
//
//	Tier               light（轻查看/关注）| heavy（重社交，需破冰阶梯/请求）。
//	RequiredGates      重行动前置安全门（⊆ registry.gateKeys）；空=无门（轻查看类）。
//	TargetAvailability available（有真实承接页）| deferred（承接页/数据源未就绪，端不得伪造成行）。
//	Dispatch           ∈ registry.actionDispatch（assistant|navigate|message|companion|connect|commerce）：
//	                   端交互 handler 路由维度，与 Tier 权限成本维度正交；端 navigator/徽标/助手分发读此字段，
//	                   禁止端手写「哪些 actionKey 属助手/约伴」第二份枚举（M0.7）。
type ActionKeyMeta struct {
	Tier               string   `yaml:"tier"`
	RequiredGates      []string `yaml:"requiredGates"`
	TargetAvailability string   `yaml:"targetAvailability"`
	Dispatch           string   `yaml:"dispatch"`
}

// DefaultMoment 是 kind 未显式声明 moment 时的缺省意图时态（§24 M0.2：大多数交集是当下事实）。
const DefaultMoment = "current"

// ObjectKindDef 统一对象类型闭集项（objectKind + countObjectKind 合并，靠 roles 标注）。
type ObjectKindDef struct {
	Kind      string   `yaml:"kind"`
	Roles     []string `yaml:"roles"`
	RouteID   string   `yaml:"routeId"`
	AssetKind string   `yaml:"assetKind"`
}

// HasRole 判断该对象类型是否承担指定角色（object 主对象品牌角标 / count 被计数对象）。
func (d ObjectKindDef) HasRole(role string) bool {
	for _, r := range d.Roles {
		if r == role {
			return true
		}
	}
	return false
}

// KindDef 单条交集 kind 的注册项（仅取端云 codegen 消费字段，余字段由门禁脚本校验）。
type KindDef struct {
	Kind                string   `yaml:"kind"`
	Vertical            string   `yaml:"vertical"`
	Dimensions          []string `yaml:"dimensions"`
	ObjectKind          string   `yaml:"objectKind"`
	CountObjectKind     string   `yaml:"countObjectKind"`
	IconKey             string   `yaml:"iconKey"`
	EvidenceRank        int      `yaml:"evidenceRank"`
	LifecycleApplicable bool     `yaml:"lifecycleApplicable"`
	Moment              string   `yaml:"moment"`
	Status              string   `yaml:"status"`
}

// MomentOrDefault 返回 kind 的意图时态，未显式声明时回退 DefaultMoment（current）。
func (d KindDef) MomentOrDefault() string {
	if strings.TrimSpace(d.Moment) == "" {
		return DefaultMoment
	}
	return d.Moment
}

func Parse(raw []byte) (*Registry, error) {
	var out Registry
	if err := yaml.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Validate 校验注册表结构完整与闭集自洽（codegen 前置守卫；与 Python 门禁互补）。
func Validate(r *Registry) error {
	if len(r.Dimensions) == 0 {
		return fmt.Errorf("dimensions closed set is empty")
	}
	if len(r.LifecycleStates) == 0 {
		return fmt.Errorf("lifecycleStates closed set is empty")
	}
	if len(r.Verticals) == 0 {
		return fmt.Errorf("verticals closed set is empty")
	}
	if len(r.ObjectKinds) == 0 {
		return fmt.Errorf("objectKinds closed set is empty")
	}
	if len(r.Moments) == 0 {
		return fmt.Errorf("moments closed set is empty")
	}
	if len(r.GateKeys) == 0 {
		return fmt.Errorf("gateKeys closed set is empty")
	}
	if len(r.FeedbackKinds) == 0 {
		return fmt.Errorf("feedbackKinds closed set is empty")
	}
	if len(r.ActionDispatch) == 0 {
		return fmt.Errorf("actionDispatch closed set is empty")
	}
	if len(r.Kinds) == 0 {
		return fmt.Errorf("kinds is empty")
	}
	if len(r.IconKeyByDimension) == 0 {
		return fmt.Errorf("iconKeyByDimension fallback map is empty")
	}
	dims := toStringSet(r.Dimensions)
	for dim, iconKey := range r.IconKeyByDimension {
		if _, ok := dims[dim]; !ok {
			return fmt.Errorf("iconKeyByDimension key %q not in dimensions closed set", dim)
		}
		if _, ok := r.IconKeyLegend[iconKey]; !ok {
			return fmt.Errorf("iconKeyByDimension[%q] value %q not in iconKeyLegend closed set", dim, iconKey)
		}
	}
	for _, dim := range r.Dimensions {
		if _, ok := r.IconKeyByDimension[dim]; !ok {
			return fmt.Errorf("dimension %q missing iconKeyByDimension fallback", dim)
		}
	}
	// actionLabelByKey 与 actionHintLegend 必须键集一致（终端 UI 短标签 vs 词典描述同闭集）。
	if len(r.ActionLabelByKey) > 0 || len(r.ActionHintLegend) > 0 {
		for key := range r.ActionHintLegend {
			if strings.TrimSpace(r.ActionLabelByKey[key]) == "" {
				return fmt.Errorf("actionLabelByKey missing label for action key %q", key)
			}
		}
		for key := range r.ActionLabelByKey {
			if _, ok := r.ActionHintLegend[key]; !ok {
				return fmt.Errorf("actionLabelByKey key %q not in actionHintLegend closed set", key)
			}
		}
	}
	// §24 M0.1/M0.3：actionKeyMeta 键集必须 == actionHintLegend，
	// 且 tier / requiredGates / targetAvailability 取值受闭集约束（gateKeys / {light,heavy} / {available,deferred}）。
	if len(r.ActionKeyMeta) > 0 || len(r.ActionHintLegend) > 0 {
		gates := toStringSet(r.GateKeys)
		dispatches := toStringSet(r.ActionDispatch)
		for key := range r.ActionHintLegend {
			if _, ok := r.ActionKeyMeta[key]; !ok {
				return fmt.Errorf("actionKeyMeta missing entry for action key %q", key)
			}
		}
		for key, meta := range r.ActionKeyMeta {
			if _, ok := r.ActionHintLegend[key]; !ok {
				return fmt.Errorf("actionKeyMeta key %q not in actionHintLegend closed set", key)
			}
			if meta.Tier != "light" && meta.Tier != "heavy" {
				return fmt.Errorf("actionKeyMeta[%q] tier %q must be light|heavy", key, meta.Tier)
			}
			if meta.TargetAvailability != "available" && meta.TargetAvailability != "deferred" {
				return fmt.Errorf("actionKeyMeta[%q] targetAvailability %q must be available|deferred", key, meta.TargetAvailability)
			}
			if _, ok := dispatches[meta.Dispatch]; !ok {
				return fmt.Errorf("actionKeyMeta[%q] dispatch %q not in actionDispatch closed set", key, meta.Dispatch)
			}
			for _, gate := range meta.RequiredGates {
				if _, ok := gates[gate]; !ok {
					return fmt.Errorf("actionKeyMeta[%q] requiredGate %q not in gateKeys closed set", key, gate)
				}
			}
		}
	}
	moments := toStringSet(r.Moments)
	verts := toStringSet(r.Verticals)
	objectKinds := map[string]struct{}{}
	for _, ok := range r.ObjectKinds {
		objectKinds[ok.Kind] = struct{}{}
	}
	for _, k := range r.Kinds {
		if strings.TrimSpace(k.Vertical) == "" {
			return fmt.Errorf("kind %q missing vertical", k.Kind)
		}
		if _, ok := verts[k.Vertical]; !ok {
			return fmt.Errorf("kind %q vertical %q not in verticals closed set", k.Kind, k.Vertical)
		}
		if _, ok := objectKinds[k.ObjectKind]; !ok {
			return fmt.Errorf("kind %q objectKind %q not in objectKinds closed set", k.Kind, k.ObjectKind)
		}
		if k.CountObjectKind != "" {
			if _, ok := objectKinds[k.CountObjectKind]; !ok {
				return fmt.Errorf("kind %q countObjectKind %q not in objectKinds closed set", k.Kind, k.CountObjectKind)
			}
		}
		for _, dim := range k.Dimensions {
			if _, ok := dims[dim]; !ok {
				return fmt.Errorf("kind %q dimension %q not in dimensions closed set", k.Kind, dim)
			}
		}
		if _, ok := moments[k.MomentOrDefault()]; !ok {
			return fmt.Errorf("kind %q moment %q not in moments closed set", k.Kind, k.MomentOrDefault())
		}
	}
	return nil
}

func toStringSet(values []string) map[string]struct{} {
	out := make(map[string]struct{}, len(values))
	for _, v := range values {
		out[v] = struct{}{}
	}
	return out
}
