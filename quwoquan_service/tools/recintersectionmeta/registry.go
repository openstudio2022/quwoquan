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
	ObjectTypeBindings []ObjectTypeBinding      `yaml:"objectTypeBindings"`
	VisualToneByIcon   map[string]string        `yaml:"visualToneByIconKey"`
	IconAssetByIconKey map[string]string        `yaml:"iconAssetByIconKey"`
	IconKeyLegend      map[string]string        `yaml:"iconKeyLegend"`
	IconKeyByDimension map[string]string        `yaml:"iconKeyByDimension"`
	ActionHintLegend   map[string]string        `yaml:"actionHintLegend"`
	ActionLabelPrefix  string                   `yaml:"actionLabelL10nKeyPrefix"`
	ActionLabelByKey   map[string]string        `yaml:"actionLabelByKey"`
	ActionKeyMeta      map[string]ActionKeyMeta `yaml:"actionKeyMeta"`
	ActionHintsByKind  map[string][]string      `yaml:"actionHintsByKind"`
	ColdStartSupply    ColdStartSupply          `yaml:"coldStartSupply"`
	StatementTemplates StatementTemplates       `yaml:"statementTemplates"`
	PresentationText   PresentationText         `yaml:"presentationText"`
	Kinds              []KindDef                `yaml:"kinds"`
}

// PresentationText 是 §17.2 结论句谓语之外的全部用户可见词汇
// （registry.presentationText）。statementTemplates 管谓语，本结构管主语称谓、
// 计数语法、互动动词、维度名、类别名、对象名装饰与概率通道话术；两者合起来
// 使服务端渲染层不再持有任何中文字面量。
type PresentationText struct {
	RelationLabels            LabelTable          `yaml:"relationLabels"`
	AnonymousActorLabels      LabelTable          `yaml:"anonymousActorLabels"`
	SubjectPatterns           PatternTable        `yaml:"subjectPatterns"`
	ViewerSubjects            ViewerSubjects      `yaml:"viewerSubjects"`
	InteractionVerbs          InteractionVerbs    `yaml:"interactionVerbs"`
	DimensionLabels           DimensionLabelTable `yaml:"dimensionLabels"`
	PointClassLabels          PointClassLabels    `yaml:"pointClassLabels"`
	ObjectNameDecorations     ObjectNameDecor     `yaml:"objectNameDecorations"`
	AffinityStatements        AffinityStatements  `yaml:"affinityStatements"`
	ConnectionSummary         SingleTemplate      `yaml:"connectionSummary"`
	SecondaryText             SecondaryText       `yaml:"secondaryText"`
	ListSeparator             SingleText          `yaml:"listSeparator"`
	PlaceholderObjectNames    []string            `yaml:"placeholderObjectNames"`
	PlaceholderRelationLabels []string            `yaml:"placeholderRelationLabels"`
	PointTemplates            LabelTable          `yaml:"pointTemplates"`
	ActorActionSummaries      LabelTable          `yaml:"actorActionSummaries"`
	KindLabels                LabelTable          `yaml:"kindLabels"`
}

// LabelTable 是 kind → 文案的查表，未登记 kind 回落 Default。
type LabelTable struct {
	L10nKeyPrefix string            `yaml:"l10nKeyPrefix"`
	Default       string            `yaml:"default"`
	ByKind        map[string]string `yaml:"byKind"`
}

// PatternTable 是带 {slot} 的文案模板集合（主语计数语法等）。
type PatternTable struct {
	L10nKeyPrefix string            `yaml:"l10nKeyPrefix"`
	Patterns      map[string]string `yaml:"patterns"`
}

// ViewerSubjects 是宿主对象即观察者自身时的主语。
type ViewerSubjects struct {
	L10nKeyPrefix string            `yaml:"l10nKeyPrefix"`
	SelfOnly      string            `yaml:"selfOnly"`
	ByObjectType  map[string]string `yaml:"byObjectType"`
}

// InteractionVerbs 是实测互动动词短语与其连接词。
type InteractionVerbs struct {
	L10nKeyPrefix string            `yaml:"l10nKeyPrefix"`
	ByAction      map[string]string `yaml:"byAction"`
	Joiners       VerbJoiners       `yaml:"joiners"`
}

// VerbJoiners 是多个动词短语的连接词：两项用 Pair，三项及以上用 List 与 Last。
type VerbJoiners struct {
	Pair string `yaml:"pair"`
	List string `yaml:"list"`
	Last string `yaml:"last"`
}

// DimensionLabelTable 是 dimension → 展示名词。
type DimensionLabelTable struct {
	L10nKeyPrefix string            `yaml:"l10nKeyPrefix"`
	ByDimension   map[string]string `yaml:"byDimension"`
}

// PointClassLabels 是 pointClass → 展示名词（事实交集 / 推荐交集）。
type PointClassLabels struct {
	L10nKeyPrefix string            `yaml:"l10nKeyPrefix"`
	ByPointClass  map[string]string `yaml:"byPointClass"`
}

// ObjectNameDecor 是对象名的引号装饰：作品类用书名号，其余用直角引号。
type ObjectNameDecor struct {
	L10nKeyPrefix  string    `yaml:"l10nKeyPrefix"`
	Default        NameAffix `yaml:"default"`
	WorkTitle      NameAffix `yaml:"workTitle"`
	WorkTitleKinds []string  `yaml:"workTitleKinds"`
}

// NameAffix 是一对包裹符号。
type NameAffix struct {
	Prefix string `yaml:"prefix"`
	Suffix string `yaml:"suffix"`
}

// AffinityStatements 是概率通道话术（按投放渠道分支）。
type AffinityStatements struct {
	L10nKeyPrefix              string                     `yaml:"l10nKeyPrefix"`
	ByChannel                  map[string]AffinityChannel `yaml:"byChannel"`
	DefaultConfidenceLabel     string                     `yaml:"defaultConfidenceLabel"`
	ConfidenceLabelByDimension map[string]string          `yaml:"confidenceLabelByDimension"`
}

// AffinityChannel 是单个投放渠道的具名 / 无名两种话术。
type AffinityChannel struct {
	Named   string `yaml:"named"`
	Unnamed string `yaml:"unnamed"`
}

// SingleTemplate 是单条带 {slot} 的模板。
type SingleTemplate struct {
	L10nKeyPrefix string `yaml:"l10nKeyPrefix"`
	Template      string `yaml:"template"`
}

// SingleText 是单条无槽位的文案。
type SingleText struct {
	L10nKeyPrefix string `yaml:"l10nKeyPrefix"`
	Text          string `yaml:"text"`
}

// SecondaryText 是列表入口灰色辅助说明的组装文案。
type SecondaryText struct {
	L10nKeyPrefix string `yaml:"l10nKeyPrefix"`
	ItemWithCount string `yaml:"itemWithCount"`
	Separator     string `yaml:"separator"`
}

// StatementTemplates 是 §17.1 结论句模板集合（文本与 spans 的共同真相源）。
//
//	Slots  槽位闭集；模板里出现的 {slot} 必须 ∈ Slots，否则渲染器会把它当字面量输出。
//	ByKind kind（= anchor.SourceRef）→ 模板项；未登记 kind 不产出结论句（不造句）。
type StatementTemplates struct {
	Slots  []string                 `yaml:"slots"`
	ByKind map[string]StatementForm `yaml:"byKind"`
}

// StatementForm 单个 kind 的结论句模板族。
//
//	L10nKey        本地化资源键；服务端随 reason 下发，端接入译文后按同名槽位回填。
//	Template       具名对象形态的主模板。
//	ActionFallback {action} 槽位在无实测互动动词时的兜底短语（仅 action 型 kind 需要）。
//	Counted        容器对象名缺失时的计数降级句；缺省表示不可降级（整条隐藏）。
//	Variants       形态变体（personPlace / noObject / circleTag），由渲染上下文选中。
type StatementForm struct {
	L10nKey        string                      `yaml:"l10nKey"`
	Template       string                      `yaml:"template"`
	ActionFallback string                      `yaml:"actionFallback"`
	Counted        *StatementVariant           `yaml:"counted"`
	Variants       map[string]StatementVariant `yaml:"variants"`
}

// StatementVariant 是模板变体（计数降级句与形态变体共用同一结构）。
type StatementVariant struct {
	L10nKey  string `yaml:"l10nKey"`
	Template string `yaml:"template"`
}

// ColdStartSupply 是冷启动稀释闸门配置（P0 横切）。
//
// 语料里可被某 kind 命中的去重对象数低于阈值时，该 kind 的交集对所有用户都成立，
// 信息量为零；服务端三个入口据此整体不展示，而不是展示一句人人相同的话。
//
//	SupplyKeyByKind          kind → 供给计量口径（供给探针按 key 统计去重对象数）。
//	                         未登记的 kind 不受闸门约束。
//	MinDistinctObjectsByKind kind → 最小候选池规模；未登记时回退 DefaultMinDistinctObjects。
type ColdStartSupply struct {
	DefaultMinDistinctObjects int               `yaml:"defaultMinDistinctObjects"`
	SupplyKeyByKind           map[string]string `yaml:"supplyKeyByKind"`
	MinDistinctObjectsByKind  map[string]int    `yaml:"minDistinctObjectsByKind"`
}

// MinDistinctObjectsFor 返回 kind 的最小候选池规模；未登记 supplyKey 的 kind 返回 0（不设闸）。
func (c ColdStartSupply) MinDistinctObjectsFor(kind string) int {
	if _, gated := c.SupplyKeyByKind[kind]; !gated {
		return 0
	}
	if n, ok := c.MinDistinctObjectsByKind[kind]; ok && n > 0 {
		return n
	}
	return c.DefaultMinDistinctObjects
}

// ActionKeyMeta 是单个 actionKey 的行动阶梯元数据（§24 M0.1/M0.3/M0.7）：
//
//	Tier               light（轻查看/关注）| heavy（重社交，需破冰阶梯/请求）。
//	RequiredGates      重行动前置安全门（⊆ registry.gateKeys）；空=无门（轻查看类）。
//	Dispatch           ∈ registry.actionDispatch（assistant|navigate|message|companion|connect|commerce）：
//	                   端交互 handler 路由维度，与 Tier 权限成本维度正交；端 navigator/徽标/助手分发读此字段，
//	                   禁止端手写「哪些 actionKey 属助手/约伴」第二份枚举（M0.7）。
type ActionKeyMeta struct {
	Tier          string   `yaml:"tier"`
	RequiredGates []string `yaml:"requiredGates"`
	Dispatch      string   `yaml:"dispatch"`
}

// DefaultMoment 是 kind 未显式声明 moment 时的缺省意图时态（§24 M0.2：大多数交集是当下事实）。
const DefaultMoment = "current"

// ObjectKindDef 统一对象类型闭集项（objectKind + countObjectKind 合并，靠 roles 标注）。
//
//	Dimension 该对象类型上的共享标签 reason 归入的交集维度。
//	Label     对象展示名缺失时的兜底称谓（同校 / 同游 / 同圈 / 同好）。
//
// 两者挂在 objectKind 而不是 objectType 上：判定「同游」的依据是对象是地点，
// 与它是博物馆还是温泉无关。
type ObjectKindDef struct {
	Kind      string   `yaml:"kind"`
	Roles     []string `yaml:"roles"`
	RouteID   string   `yaml:"routeId"`
	AssetKind string   `yaml:"assetKind"`
	Dimension string   `yaml:"dimension"`
	Label     string   `yaml:"label"`
}

// ObjectTypeBinding 把开放的 objectType 词汇收口到 objectKind 闭集。
// 服务端只查这张表，禁止手写 objectType switch 或从 objectId 子串反推类型。
type ObjectTypeBinding struct {
	ObjectType string `yaml:"objectType"`
	ObjectKind string `yaml:"objectKind"`
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

// L10nKeyFor 按 presentationText 的约定推导条目的本地化资源键：
// prefix + "." + snake(条目键)。逐条手写 key 会引入近百行只能靠人眼保持一致的
// 样板，故统一推导；唯一性由 verify_intersection_kind_registry.py 校验。
// 无条目键的单条文案（如 listSeparator）直接用前缀本身。
func L10nKeyFor(prefix, entryKey string) string {
	prefix = strings.TrimSpace(prefix)
	if prefix == "" {
		return ""
	}
	entryKey = strings.TrimSpace(entryKey)
	if entryKey == "" {
		return prefix
	}
	return prefix + "." + SnakeCase(entryKey)
}

// SnakeCase 把 registry 里的 lowerCamelCase 条目键转成 l10n 惯用的 snake_case。
func SnakeCase(s string) string {
	var b strings.Builder
	for i, r := range s {
		if r >= 'A' && r <= 'Z' {
			if i > 0 {
				b.WriteByte('_')
			}
			b.WriteRune(r - 'A' + 'a')
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
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
	// iconAssetByIconKey 是可选的远程图标资源引用表（零发版新增图标的落点）。
	// 为空表示所有图标仍走端侧 glyph 兜底；一旦登记，键必须是已知 iconKey，值必须是
	// 数据发布 media 根下的相对路径，禁止写死绝对 CDN 域名（域名属环境配置）。
	for iconKey, asset := range r.IconAssetByIconKey {
		if _, ok := r.IconKeyLegend[iconKey]; !ok {
			return fmt.Errorf("iconAssetByIconKey key %q not in iconKeyLegend closed set", iconKey)
		}
		trimmed := strings.TrimSpace(asset)
		if trimmed == "" {
			return fmt.Errorf("iconAssetByIconKey[%q] is empty", iconKey)
		}
		if strings.Contains(trimmed, "://") || strings.HasPrefix(trimmed, "/") {
			return fmt.Errorf("iconAssetByIconKey[%q] must be a release-relative path, got %q", iconKey, asset)
		}
	}
	// actionLabelByKey 与 actionHintLegend 必须键集一致（终端 UI 短标签 vs 词典描述同闭集）。
	if len(r.ActionLabelByKey) > 0 && strings.TrimSpace(r.ActionLabelPrefix) == "" {
		return fmt.Errorf("actionLabelL10nKeyPrefix is required（无前缀则行动短标签无法被运营态覆盖）")
	}
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
	// 且 tier / requiredGates / dispatch 取值受闭集约束。
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
		if _, has := dims[ok.Dimension]; !has {
			return fmt.Errorf(
				"objectKind %q dimension %q not in dimensions closed set",
				ok.Kind, ok.Dimension,
			)
		}
		if strings.TrimSpace(ok.Label) == "" {
			return fmt.Errorf("objectKind %q missing label", ok.Kind)
		}
	}
	if err := validateObjectTypeBindings(r, objectKinds); err != nil {
		return err
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
	if err := validateStatementTemplates(r); err != nil {
		return err
	}
	if err := validatePresentationText(r, dims); err != nil {
		return err
	}
	return nil
}

// validatePresentationText 保证展示文案层可直接生成查表：必备表非空、每张表都有
// l10nKeyPrefix、推导出的 l10nKey 全局唯一，且 dimensionLabels 覆盖 dimensions 闭集。
// 唯一性是硬要求：两条文案共用一个 key 会让运营态覆盖改一处影响两处。
func validatePresentationText(r *Registry, dims map[string]struct{}) error {
	p := r.PresentationText
	if len(p.RelationLabels.ByKind) == 0 {
		return fmt.Errorf("presentationText.relationLabels.byKind is empty")
	}
	if len(p.SubjectPatterns.Patterns) == 0 {
		return fmt.Errorf("presentationText.subjectPatterns.patterns is empty")
	}
	if len(p.InteractionVerbs.ByAction) == 0 {
		return fmt.Errorf("presentationText.interactionVerbs.byAction is empty")
	}
	if len(p.KindLabels.ByKind) == 0 {
		return fmt.Errorf("presentationText.kindLabels.byKind is empty")
	}
	if len(p.PointTemplates.ByKind) == 0 {
		return fmt.Errorf("presentationText.pointTemplates.byKind is empty")
	}
	for dim := range dims {
		if strings.TrimSpace(p.DimensionLabels.ByDimension[dim]) == "" {
			return fmt.Errorf("presentationText.dimensionLabels missing label for dimension %q", dim)
		}
	}
	for dim := range p.DimensionLabels.ByDimension {
		if _, ok := dims[dim]; !ok {
			return fmt.Errorf("presentationText.dimensionLabels key %q not in dimensions closed set", dim)
		}
	}
	if strings.TrimSpace(p.ListSeparator.Text) == "" {
		return fmt.Errorf("presentationText.listSeparator.text is empty")
	}
	if strings.TrimSpace(p.ObjectNameDecorations.Default.Prefix) == "" ||
		strings.TrimSpace(p.ObjectNameDecorations.Default.Suffix) == "" {
		return fmt.Errorf("presentationText.objectNameDecorations.default must define prefix and suffix")
	}
	if len(p.AffinityStatements.ByChannel) == 0 {
		return fmt.Errorf("presentationText.affinityStatements.byChannel is empty")
	}
	for name, channel := range p.AffinityStatements.ByChannel {
		if strings.TrimSpace(channel.Named) == "" || strings.TrimSpace(channel.Unnamed) == "" {
			return fmt.Errorf("presentationText.affinityStatements.byChannel[%q] must define named and unnamed", name)
		}
	}
	seen := map[string]string{}
	claim := func(table, entry, prefix string) error {
		if strings.TrimSpace(prefix) == "" {
			return fmt.Errorf("presentationText.%s missing l10nKeyPrefix", table)
		}
		key := L10nKeyFor(prefix, entry)
		if owner, dup := seen[key]; dup {
			return fmt.Errorf("presentationText l10nKey %q derived twice (%s and %s.%s)", key, owner, table, entry)
		}
		seen[key] = table + "." + entry
		return nil
	}
	for entry := range p.RelationLabels.ByKind {
		if err := claim("relationLabels", entry, p.RelationLabels.L10nKeyPrefix); err != nil {
			return err
		}
	}
	for entry := range p.AnonymousActorLabels.ByKind {
		if err := claim("anonymousActorLabels", entry, p.AnonymousActorLabels.L10nKeyPrefix); err != nil {
			return err
		}
	}
	for entry := range p.SubjectPatterns.Patterns {
		if err := claim("subjectPatterns", entry, p.SubjectPatterns.L10nKeyPrefix); err != nil {
			return err
		}
	}
	for entry := range p.ViewerSubjects.ByObjectType {
		if err := claim("viewerSubjects", entry, p.ViewerSubjects.L10nKeyPrefix); err != nil {
			return err
		}
	}
	if err := claim("viewerSubjects", "selfOnly", p.ViewerSubjects.L10nKeyPrefix); err != nil {
		return err
	}
	for entry := range p.InteractionVerbs.ByAction {
		if err := claim("interactionVerbs", entry, p.InteractionVerbs.L10nKeyPrefix); err != nil {
			return err
		}
	}
	for entry := range p.DimensionLabels.ByDimension {
		if err := claim("dimensionLabels", entry, p.DimensionLabels.L10nKeyPrefix); err != nil {
			return err
		}
	}
	for entry := range p.PointClassLabels.ByPointClass {
		if err := claim("pointClassLabels", entry, p.PointClassLabels.L10nKeyPrefix); err != nil {
			return err
		}
	}
	for entry := range p.AffinityStatements.ByChannel {
		if err := claim("affinityStatements", entry, p.AffinityStatements.L10nKeyPrefix); err != nil {
			return err
		}
	}
	for entry := range p.KindLabels.ByKind {
		if err := claim("kindLabels", entry, p.KindLabels.L10nKeyPrefix); err != nil {
			return err
		}
	}
	for entry := range p.PointTemplates.ByKind {
		if err := claim("pointTemplates", entry, p.PointTemplates.L10nKeyPrefix); err != nil {
			return err
		}
	}
	for entry := range p.ActorActionSummaries.ByKind {
		if err := claim("actorActionSummaries", entry, p.ActorActionSummaries.L10nKeyPrefix); err != nil {
			return err
		}
	}
	if err := claim("connectionSummary", "", p.ConnectionSummary.L10nKeyPrefix); err != nil {
		return err
	}
	if err := claim("listSeparator", "", p.ListSeparator.L10nKeyPrefix); err != nil {
		return err
	}
	if err := claim("secondaryText", "itemWithCount", p.SecondaryText.L10nKeyPrefix); err != nil {
		return err
	}
	return nil
}

// validateObjectTypeBindings 保证 objectType→objectKind 收口表可直接生成查表：
// 取值非空、不重复、落在闭集内。是否覆盖 HomepageType 全集由 Python 门禁校验，
// 因为本包读不到 _shared/types.yaml。
func validateObjectTypeBindings(r *Registry, objectKinds map[string]struct{}) error {
	if len(r.ObjectTypeBindings) == 0 {
		return fmt.Errorf("objectTypeBindings is empty")
	}
	seen := map[string]struct{}{}
	for _, b := range r.ObjectTypeBindings {
		objectType := strings.TrimSpace(b.ObjectType)
		if objectType == "" {
			return fmt.Errorf("objectTypeBindings entry missing objectType")
		}
		if _, dup := seen[objectType]; dup {
			return fmt.Errorf("objectType %q bound more than once", objectType)
		}
		seen[objectType] = struct{}{}
		if _, ok := objectKinds[b.ObjectKind]; !ok {
			return fmt.Errorf(
				"objectType %q objectKind %q not in objectKinds closed set",
				objectType, b.ObjectKind,
			)
		}
	}
	return nil
}

// 结论句模板变体名闭集：渲染器按名字选形态，注册表不得自造第三种变体名。
var statementVariantNames = map[string]struct{}{
	"personPlace": {},
	"noObject":    {},
	"circleTag":   {},
}

// validateStatementTemplates 校验结论句模板自洽：
// 槽位 ⊆ slots 闭集、模板非空、l10nKey 非空且全局唯一、变体名 ∈ 闭集。
// 模板缺 l10nKey 就等于文案又回到「只能改代码」，因此 key 缺失按错误处理。
func validateStatementTemplates(r *Registry) error {
	st := r.StatementTemplates
	if len(st.ByKind) == 0 {
		return nil
	}
	if len(st.Slots) == 0 {
		return fmt.Errorf("statementTemplates.slots closed set is empty")
	}
	slots := toStringSet(st.Slots)
	seenKeys := map[string]string{}
	checkOne := func(owner, template, l10nKey string) error {
		if strings.TrimSpace(template) == "" {
			return fmt.Errorf("statementTemplates %s missing template", owner)
		}
		if strings.TrimSpace(l10nKey) == "" {
			return fmt.Errorf("statementTemplates %s missing l10nKey", owner)
		}
		if prev, dup := seenKeys[l10nKey]; dup {
			return fmt.Errorf("statementTemplates %s l10nKey %q already used by %s", owner, l10nKey, prev)
		}
		seenKeys[l10nKey] = owner
		for _, slot := range TemplateSlots(template) {
			if _, ok := slots[slot]; !ok {
				return fmt.Errorf("statementTemplates %s slot %q not in slots closed set", owner, slot)
			}
		}
		return nil
	}
	for kind, form := range st.ByKind {
		if err := checkOne(kind, form.Template, form.L10nKey); err != nil {
			return err
		}
		if strings.Contains(form.Template, "{action}") && strings.TrimSpace(form.ActionFallback) == "" {
			return fmt.Errorf("statementTemplates %s uses {action} but has no actionFallback", kind)
		}
		if form.Counted != nil {
			if err := checkOne(kind+".counted", form.Counted.Template, form.Counted.L10nKey); err != nil {
				return err
			}
		}
		for name, variant := range form.Variants {
			if _, ok := statementVariantNames[name]; !ok {
				return fmt.Errorf("statementTemplates %s variant %q not in variant closed set", kind, name)
			}
			if err := checkOne(kind+"."+name, variant.Template, variant.L10nKey); err != nil {
				return err
			}
		}
	}
	return nil
}

// TemplateSlots 取模板里出现的槽位名（按出现顺序，含重复）。
// 与渲染器共用同一段扫描逻辑，避免「校验认的槽位」和「渲染认的槽位」不是一套。
func TemplateSlots(template string) []string {
	out := make([]string, 0, 4)
	rest := template
	for {
		start := strings.Index(rest, "{")
		if start < 0 {
			return out
		}
		end := strings.Index(rest[start:], "}")
		if end < 0 {
			return out
		}
		out = append(out, rest[start+1:start+end])
		rest = rest[start+end+1:]
	}
}

func toStringSet(values []string) map[string]struct{} {
	out := make(map[string]struct{}, len(values))
	for _, v := range values {
		out[v] = struct{}{}
	}
	return out
}
