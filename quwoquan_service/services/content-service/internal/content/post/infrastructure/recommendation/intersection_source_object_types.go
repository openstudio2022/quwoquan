package recommendation

import (
	"strings"

	"quwoquan_service/services/content-service/generated/content/post"
)

// 本文件把调用方给的开放 objectType 词汇翻译成交集侧的闭集语义。
// 唯一真相源是 intersection_kind_registry.yaml：objectTypeBindings 声明
// objectType → objectKind，objectKinds[].dimension / .label 声明该 kind 的
// 交集维度与兜底称谓，两者经 codegen 落成 generated.Intersection* 查表。
//
// 这里不得再出现按具体垂类或具体标签展开的 switch，也不得从 objectId 子串
// 反推类型：新增一个 HomepageType 应当只改注册表并重跑 codegen，而不是发 Go 版本。

// objectKindForObjectType 将开放 objectType 收口到闭集 objectKind（人/圈/校/地/企角标真相源）。
// 未登记 objectType 返回空串；覆盖完整性由 verify_intersection_kind_registry.py 阻断，
// 使「静默落进 default 再被下游当成人物」不可能发生。
func objectKindForObjectType(objectType string) string {
	return generated.IntersectionObjectKindByObjectType[strings.TrimSpace(objectType)]
}

// objectDimension 返回该对象上共享标签 reason 归属的交集维度。
func objectDimension(objectType string) string {
	return generated.IntersectionDimensionByObjectKind[objectKindForObjectType(objectType)]
}

// objectLabel 返回对象展示名缺失时的兜底称谓（同校 / 同游 / 同圈 / 同好）。
func objectLabel(objectType string) string {
	return generated.IntersectionLabelByObjectKind[objectKindForObjectType(objectType)]
}

func concreteObjectDisplayName(objectID, objectType string) string {
	raw := strings.TrimSpace(objectID)
	if raw == "" {
		return ""
	}
	parts := strings.FieldsFunc(raw, func(r rune) bool {
		return r == '/' || r == ':' || r == '|'
	})
	candidate := raw
	if len(parts) > 0 {
		candidate = strings.TrimSpace(parts[len(parts)-1])
	}
	// 兜底称谓与注册表登记的通用占位词都不是具名对象
	// （registry.presentationText.placeholderObjectNames）。
	if _, placeholder := generated.IntersectionPlaceholderObjectNames[candidate]; placeholder {
		return ""
	}
	if candidate == "" || candidate == objectLabel(objectType) {
		return ""
	}
	if strings.Contains(candidate, "_") {
		return ""
	}
	return candidate
}

// relationActionType 决定点击落点语义：只有人物开个人主页，其余一律查看对象。
func relationActionType(objectType string) string {
	if objectKindForObjectType(objectType) == "person" {
		return "open_profile"
	}
	return "view_object"
}
