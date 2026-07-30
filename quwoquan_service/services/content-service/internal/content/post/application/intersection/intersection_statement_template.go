package intersection

import (
	"strconv"
	"strings"

	generated "quwoquan_service/services/content-service/generated/content/post"
)

// templateSegment 是模板切分后的一段：literal 与 slot 恰有一个非空。
type templateSegment struct {
	literal string
	slot    string
}

// splitTemplate 把 "{subject}都去过{object}" 切成字面量与槽位段（渲染与校验共用）。
func splitTemplate(template string) []templateSegment {
	out := make([]templateSegment, 0, 5)
	rest := template
	for {
		start := strings.Index(rest, "{")
		if start < 0 {
			break
		}
		end := strings.Index(rest[start:], "}")
		if end < 0 {
			break
		}
		if literal := rest[:start]; literal != "" {
			out = append(out, templateSegment{literal: literal})
		}
		out = append(out, templateSegment{slot: rest[start+1 : start+end]})
		rest = rest[start+end+1:]
	}
	if rest != "" {
		out = append(out, templateSegment{literal: rest})
	}
	return out
}

// statementSlots 是渲染时可填的槽位值。空值槽位使模板整体不可渲染（不造句）。
//
// 每个槽位除文本外还带渲染角色：subject/countedSubject 展开为可点击的代表人 spans，
// object 是唯一带 target 的对象 span，其余槽位是纯文本。文本与 spans 由同一份模板与
// 同一份槽位值产出，因此 join(spans.text) == primaryText 是结构性结果。
type statementSlots struct {
	subject        []IntersectionTextSpanView
	countedSubject []IntersectionTextSpanView
	object         *IntersectionTextSpanView
	count          int
	occupation     string
	place          string
	action         string
}

// statementRender 是一次模板渲染的结果：文本 + spans + 命中的 l10nKey。
//
// usesObject 表示命中的模板含 {object} 槽位：这类句子的 spans 必须带可导航 target，
// 否则「句中对象可点击」的展示合同不成立，spans 侧要整条放弃（文本侧不受影响）。
type statementRender struct {
	text       string
	spans      []IntersectionTextSpanView
	l10nKey    string
	usesObject bool
}

func (s statementRender) ok() bool { return strings.TrimSpace(s.text) != "" }

// renderStatement 用 form 的某个模板与槽位值渲染结论句。
//
// 任一被模板引用的槽位没有值时返回零值，由调用方走降级链（计数句 → 隐藏），
// 绝不用空串拼出半句话或用邻近语义补位。
func renderStatement(
	template string,
	l10nKey string,
	slots statementSlots,
) statementRender {
	if strings.TrimSpace(template) == "" {
		return statementRender{}
	}
	// 运营态覆盖先试：改一句结论句不发服务。覆盖模板引用了本次没有值的槽位时
	// 回落契约基线，而不是让整条交集因一次文案配置错误消失（fail-safe）。
	if override, ok := overrideText(l10nKey); ok && override != template {
		if render := renderStatementTemplate(override, l10nKey, slots); render.ok() {
			return render
		}
	}
	return renderStatementTemplate(template, l10nKey, slots)
}

func renderStatementTemplate(
	template string,
	l10nKey string,
	slots statementSlots,
) statementRender {
	segments := splitTemplate(template)
	spans := make([]IntersectionTextSpanView, 0, len(segments)+2)
	for _, segment := range segments {
		if segment.slot == "" {
			spans = append(spans, plainSpan(segment.literal))
			continue
		}
		filled, ok := fillSlot(segment.slot, slots)
		if !ok {
			return statementRender{}
		}
		spans = append(spans, filled...)
	}
	if len(spans) == 0 {
		return statementRender{}
	}
	usesObject := false
	for _, segment := range segments {
		if segment.slot == "object" {
			usesObject = true
			break
		}
	}
	return statementRender{
		text:       JoinedSpanText(spans),
		spans:      spans,
		l10nKey:    strings.TrimSpace(l10nKey),
		usesObject: usesObject,
	}
}

// statementRenderForReason 选模板并渲染结论句：
//
//	personPlace 变体  对象位是对方本人、地点在点级证据里（对象页宿主是人）时优先命名地点
//	主模板           有可证的具名对象
//	counted 变体     容器对象名缺失时的纯计数降级句（§20.4 降级链第二级）
//	noObject 变体    没有第三方对象名但句子本身仍成立（commonContact）
//
// 全部落空返回零值：宁可不出句，也不用邻近语义借壳（§24.10 诚实红线）。
func statementRenderForReason(
	r IntersectionReasonView,
	anchor IntersectionPointView,
	target *IntersectionTargetView,
) statementRender {
	kind := strings.TrimSpace(anchor.SourceRef)
	form := statementFormForKind(kind)
	if strings.TrimSpace(form.Template) == "" {
		return statementRender{}
	}
	n := anchorAggregateCount(r, anchor)
	subjectSpans := representativeSubjectSpans(r, anchor)
	countedSpans := splitCountSpan(
		countedRepresentativeSubject(r, anchor, n),
		n,
		countTargetForReason(r, anchor),
	)
	// 兴趣标签样本的主语是「你」/「你和这里」/「你和这个圈子」这类视角短语，
	// 宾语是标签样本原名（不加书名号/引号），与代表人句式不同源。
	if kind == "sharedTagSample" {
		if subject := sharedTagSampleSubject(r, anchor, n); subject != "" {
			subjectSpans = []IntersectionTextSpanView{plainSpan(subject)}
		} else {
			subjectSpans = nil
		}
	}

	// 人级地点交集：宾语是对方本人（人名合法），地名来自点级证据样本。
	if variant := statementVariantForKind(kind, "personPlace"); strings.TrimSpace(variant.Template) != "" &&
		strings.TrimSpace(r.ObjectKind) == "person" {
		personName := renderedObjectNameForReason(r, "commonFollower")
		render := renderStatement(variant.Template, variant.L10nKey, statementSlots{
			subject:        subjectSpans,
			countedSubject: countedSpans,
			object:         objectSpan(personName, target),
			place:          placeSampleName(anchor),
		})
		if render.ok() {
			return render
		}
	}

	objectName := renderedObjectNameForReason(r, kind)
	switch kind {
	case "commonContact":
		// 共同联系人的宾语是「你和 X」里的 X 本人，人名合法。
		objectName = concreteObjectNameForReason(r)
	case "sharedTagSample":
		objectName = sharedTagSampleObjectName(r, anchor)
	}
	// 圈子标签样本换视角句式：「你在圈子里常看 X」而不是「你都关注 X」。
	template, l10nKey := form.Template, form.L10nKey
	if kind == "sharedTagSample" && strings.TrimSpace(r.Source) == "circleTag" {
		if variant := statementVariantForKind(kind, "circleTag"); strings.TrimSpace(variant.Template) != "" {
			template, l10nKey = variant.Template, variant.L10nKey
		}
	}
	if objectName != "" {
		action := interactionActionPhraseForReason(r)
		if action == "" {
			action = form.ActionFallback
		}
		render := renderStatement(template, l10nKey, statementSlots{
			subject:        subjectSpans,
			countedSubject: countedSpans,
			object:         objectSpan(objectName, target),
			count:          anchor.Count,
			occupation:     sharedOccupationName(anchor),
			place:          placeSampleName(anchor),
			action:         action,
		})
		if render.ok() {
			return render
		}
	}

	// 计数降级：count 用锚点真实计数（可证），不足 1 视为不可降级。
	if strings.TrimSpace(form.Counted.Template) != "" {
		render := renderStatement(form.Counted.Template, form.Counted.L10nKey, statementSlots{
			subject:        subjectSpans,
			countedSubject: countedSpans,
			count:          anchor.Count,
		})
		if render.ok() {
			return render
		}
	}

	if variant := statementVariantForKind(kind, "noObject"); strings.TrimSpace(variant.Template) != "" {
		render := renderStatement(variant.Template, variant.L10nKey, statementSlots{
			subject:        subjectSpans,
			countedSubject: countedSpans,
		})
		if render.ok() {
			return render
		}
	}
	return statementRender{}
}

// objectSpan 构造对象槽位 span；target 为 nil 时仍产出文本（供纯文本渲染路径使用），
// spans 侧由调用方按 usesObject 判定是否放弃。
func objectSpan(name string, target *IntersectionTargetView) *IntersectionTextSpanView {
	if strings.TrimSpace(name) == "" {
		return nil
	}
	return &IntersectionTextSpanView{Text: name, Role: "object", Target: target}
}

// fillSlot 把单个槽位展开为 spans；槽位无值时返回 ok=false。
func fillSlot(slot string, slots statementSlots) ([]IntersectionTextSpanView, bool) {
	switch slot {
	case "subject":
		if len(slots.subject) == 0 {
			return nil, false
		}
		return slots.subject, true
	case "countedSubject":
		if len(slots.countedSubject) == 0 {
			return nil, false
		}
		return slots.countedSubject, true
	case "object":
		if slots.object == nil || strings.TrimSpace(slots.object.Text) == "" {
			return nil, false
		}
		return []IntersectionTextSpanView{*slots.object}, true
	case "count":
		if slots.count <= 0 {
			return nil, false
		}
		return []IntersectionTextSpanView{plainSpan(strconv.Itoa(slots.count))}, true
	case "occupation":
		return plainSlot(slots.occupation)
	case "place":
		return plainSlot(slots.place)
	case "action":
		return plainSlot(slots.action)
	default:
		// 未登记槽位：注册表校验（recintersectionmeta.validateStatementTemplates）已拦，
		// 运行时仍按不可渲染处理，避免把 "{foo}" 当字面量播给用户。
		return nil, false
	}
}

func plainSlot(value string) ([]IntersectionTextSpanView, bool) {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return nil, false
	}
	return []IntersectionTextSpanView{plainSpan(trimmed)}, true
}

// statementFormForKind 取 kind 的模板族（registry.statementTemplates.byKind）。
// 未登记 kind 返回零值：消费方据此不产出结论句。
func statementFormForKind(kind string) generated.IntersectionStatementForm {
	return generated.IntersectionStatementFormByKind[strings.TrimSpace(kind)]
}

// statementVariantForKind 取 kind 的形态变体（personPlace / noObject / circleTag）。
func statementVariantForKind(kind, variant string) generated.IntersectionStatementVariant {
	form := statementFormForKind(kind)
	if form.Variants == nil {
		return generated.IntersectionStatementVariant{}
	}
	return form.Variants[variant]
}

// StatementTemplateSlots 暴露模板槽位扫描，供契约测试断言注册表模板只用闭集槽位。
func StatementTemplateSlots(template string) []string {
	out := make([]string, 0, 4)
	for _, segment := range splitTemplate(template) {
		if segment.slot != "" {
			out = append(out, segment.slot)
		}
	}
	return out
}
