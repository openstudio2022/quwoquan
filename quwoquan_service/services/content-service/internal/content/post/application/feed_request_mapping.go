package post

import (
	"strings"
)

// normalizeRequestType 只承认频道 token 与 canonical ContentType 闭集。频道 token
// 表达路由而不是内容类型过滤，归一为空；其余取值原样交给 ContentType 校验，
// 未知值 fail-closed，不在读侧翻译 photo/note 之类的展示别名。
func normalizeRequestType(t string) string {
	switch strings.TrimSpace(strings.ToLower(t)) {
	case "", "recommended", "following", "travel", "travel_photography", "premium", "similar", "featured", "immersive", "精品", "旅行", "旅游":
		return ""
	default:
		return strings.TrimSpace(strings.ToLower(t))
	}
}
