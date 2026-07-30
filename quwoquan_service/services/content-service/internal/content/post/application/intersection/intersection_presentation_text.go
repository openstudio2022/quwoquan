package intersection

import (
	"strconv"
	"strings"

	generated "quwoquan_service/services/content-service/generated/content/post"
)

// 展示文案层的唯一读取入口。
//
// 全部用户可见词汇来自 registry.presentationText 经 codegen 的表
// （generated.Intersection*ByKind / *Pattern / *Label...），本文件与其调用方
// 不得出现中文字面量：改一个词只改注册表并 codegen，不发服务。
//
// 每条文案同时带 L10nKey：resolve 先查控制面
// sys.intersection_text.<l10nKey>.<locale>，未命中回落 codegen 基线。
// 调用方无需感知这一层——这是本文件存在的意义。

// resolve 取一条文案的当前生效文本：运营态覆盖 > codegen 基线。
// 未登记条目返回空串，调用方必须据此走降级链（省略该成分或整条不出），
// 不得回退字面量。
func resolve(t generated.IntersectionText) string {
	if override, ok := overrideText(t.L10nKey); ok {
		return override
	}
	return t.Text
}

// renderTextTemplate 用槽位值渲染一条带 {slot} 的文案。
// 任一被引用的槽位没有值时返回空串：宁可不出文案，也不拼出半句话。
func renderTextTemplate(template string, values map[string]string) string {
	if strings.TrimSpace(template) == "" {
		return ""
	}
	var b strings.Builder
	for _, segment := range splitTemplate(template) {
		if segment.slot == "" {
			b.WriteString(segment.literal)
			continue
		}
		value := strings.TrimSpace(values[segment.slot])
		if value == "" {
			return ""
		}
		b.WriteString(value)
	}
	return b.String()
}

// relationLabelText 取 kind 的代表人关系限定词；未登记 kind 回落注册表 default。
func relationLabelText(kind string) string {
	if t, ok := generated.IntersectionRelationLabelByKind[strings.TrimSpace(kind)]; ok {
		return resolve(t)
	}
	return resolve(generated.IntersectionRelationLabelDefault)
}

// anonymousActorText 取无具名代表人时的匿名主语；未登记 kind 回落注册表 default。
func anonymousActorText(kind string) string {
	if t, ok := generated.IntersectionAnonymousActorLabelByKind[strings.TrimSpace(kind)]; ok {
		return resolve(t)
	}
	return resolve(generated.IntersectionAnonymousActorLabelDefault)
}

// subjectPatternText 按主语语法模板渲染，如 countedWithRelation → "3位校友"。
func subjectPatternText(pattern string, values map[string]string) string {
	t, ok := generated.IntersectionSubjectPattern[pattern]
	if !ok {
		return ""
	}
	return renderTextTemplate(resolve(t), values)
}

// viewerSubjectText 取宿主对象即观察者自身时的主语；未登记 objectType 返回空。
func viewerSubjectText(objectType string) string {
	if t, ok := generated.IntersectionViewerSubjectByObjectType[strings.TrimSpace(objectType)]; ok {
		return resolve(t)
	}
	return ""
}

// viewerSelfSubjectText 取仅指代观察者自身的主语。
func viewerSelfSubjectText() string {
	return resolve(generated.IntersectionViewerSubjectSelfOnly)
}

// hasViewerScopedSubject 判断结论句的主语是否只指向宿主对象自身
// （「你和这里」/「你和这个圈子」）。这类句子说不出「和谁」有交集，
// 是空话而非交集事实，必须在下发前整条淘汰。
//
// 词表取自 registry.presentationText.viewerSubjects.byObjectType：与产出这些主语的
// 是同一份数据，改文案不会让判定失效。selfOnly（「你」）不在此列——
// 它是关于观察者自己的陈述，本身成立。
func hasViewerScopedSubject(text string) bool {
	text = strings.TrimSpace(text)
	if text == "" {
		return false
	}
	for objectType := range generated.IntersectionViewerSubjectByObjectType {
		subject := viewerSubjectText(objectType)
		if subject != "" && strings.HasPrefix(text, subject) {
			return true
		}
	}
	return false
}

// interactionVerbText 取单个互动类型的动词短语。
func interactionVerbText(action string) string {
	if t, ok := generated.IntersectionInteractionVerbByAction[strings.TrimSpace(action)]; ok {
		return resolve(t)
	}
	return ""
}

// joinInteractionVerbs 按注册表连接词把多个动词短语连成一句。
func joinInteractionVerbs(parts []string) string {
	switch len(parts) {
	case 0:
		return ""
	case 1:
		return parts[0]
	case 2:
		return parts[0] + resolve(generated.IntersectionVerbJoinerPair) + parts[1]
	default:
		head := strings.Join(parts[:len(parts)-1], resolve(generated.IntersectionVerbJoinerList))
		return head + resolve(generated.IntersectionVerbJoinerLast) + parts[len(parts)-1]
	}
}

// dimensionLabelText 取维度展示名词。
func dimensionLabelText(dimension string) string {
	if t, ok := generated.IntersectionDimensionLabelByDimension[strings.TrimSpace(dimension)]; ok {
		return resolve(t)
	}
	return ""
}

// pointClassLabelText 取交集类别展示名词（事实交集 / 推荐交集）。
func pointClassLabelText(pointClass string) string {
	if t, ok := generated.IntersectionPointClassLabelByPointClass[strings.TrimSpace(pointClass)]; ok {
		return resolve(t)
	}
	return ""
}

// kindLabelText 取交集点短标签。
func kindLabelText(kind string) string {
	if t, ok := generated.IntersectionKindLabelByKind[strings.TrimSpace(kind)]; ok {
		return resolve(t)
	}
	return ""
}

// pointDisplayTextFor 渲染交集点的计数短句。未登记 kind 返回空（不造句）。
func pointDisplayTextFor(kind string, values map[string]string) string {
	t, ok := generated.IntersectionPointTemplateByKind[strings.TrimSpace(kind)]
	if !ok {
		return ""
	}
	return renderTextTemplate(resolve(t), values)
}

// actorActionSummaryText 取逐人证据的动作摘要（「TA 做了什么」）。
func actorActionSummaryText(kind string) string {
	if t, ok := generated.IntersectionActorActionSummaryByKind[strings.TrimSpace(kind)]; ok {
		return resolve(t)
	}
	return ""
}

// listSeparatorText 取样本名列表分隔符（locale 敏感）。
func listSeparatorText() string {
	return resolve(generated.IntersectionListSeparator)
}

// decorateObjectName 给对象名加引号装饰：作品类用书名号，其余用直角引号。
func decorateObjectName(kind, name string) string {
	if strings.TrimSpace(name) == "" {
		return ""
	}
	affix := generated.IntersectionObjectNameDefaultAffix
	if _, isWork := generated.IntersectionWorkTitleKinds[strings.TrimSpace(kind)]; isWork {
		affix = generated.IntersectionObjectNameWorkTitleAffix
	}
	return affix.Prefix + name + affix.Suffix
}

// isPlaceholderObjectName 判断对象名是否是历史遗留的通用占位词。
// 命中即视为「没有具名对象」并走降级链，禁止进入结论句。
func isPlaceholderObjectName(name string) bool {
	_, hit := generated.IntersectionPlaceholderObjectNames[strings.TrimSpace(name)]
	return hit
}

// isPlaceholderRelationLabel 判断关系称谓是否是历史遗留的通用占位词。
func isPlaceholderRelationLabel(label string) bool {
	_, hit := generated.IntersectionPlaceholderRelationLabels[strings.TrimSpace(label)]
	return hit
}

// affinityStatementText 渲染概率通道话术：有具名对象走 named，否则走 unnamed。
func affinityStatementText(channel, objectName string) string {
	t, ok := generated.IntersectionAffinityStatementByChannel[strings.TrimSpace(channel)]
	if !ok {
		return ""
	}
	if strings.TrimSpace(objectName) != "" {
		if rendered := renderTextTemplate(resolve(t.Named), map[string]string{"object": objectName}); rendered != "" {
			return rendered
		}
	}
	return resolve(t.Unnamed)
}

// affinityConfidenceText 取概率通道置信标注；未登记 dimension 回落 default。
func affinityConfidenceText(dimension string) string {
	if t, ok := generated.IntersectionAffinityConfidenceLabelByDimension[strings.TrimSpace(dimension)]; ok {
		return resolve(t)
	}
	return resolve(generated.IntersectionAffinityConfidenceLabelDefault)
}

// connectionSummaryText 渲染对象页连接说明。
func connectionSummaryText(count int) string {
	return renderTextTemplate(
		resolve(generated.IntersectionConnectionSummaryTemplate),
		map[string]string{"count": strconv.Itoa(count)},
	)
}

// secondaryTextItem 渲染辅助说明的单项：计数 > 1 时带上计数。
func secondaryTextItem(label string, count int) string {
	if strings.TrimSpace(label) == "" {
		return ""
	}
	if count <= 1 {
		return label
	}
	return renderTextTemplate(
		resolve(generated.IntersectionSecondaryTextItemWithCount),
		map[string]string{"label": label, "count": strconv.Itoa(count)},
	)
}

// secondaryTextSeparatorText 取辅助说明各项之间的分隔符。
func secondaryTextSeparatorText() string {
	return resolve(generated.IntersectionSecondaryTextSeparator)
}
