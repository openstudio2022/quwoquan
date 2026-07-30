package controlplane

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// IntersectionTextOverrideKeyPrefix 是交集展示文案热配置 key 的命名空间前缀。
// 完整 key 形如 sys.intersection_text.intersection.relation.alumni.zh，
// 与 sys.error_message. 同构：由 control-plane 下发，reload 等级 hot。
//
// 基线文案仍是 registry.presentationText 经 codegen 的表；本前缀只做运营态覆盖，
// 未命中一律回落基线，所以改一句文案既不发端也不发服务。
const IntersectionTextOverrideKeyPrefix = "sys.intersection_text."

// intersectionTextOverrideTotal 统计交集文案覆盖的命中/未命中。
// 只按 result+locale 打标签：l10nKey 有数百个，进标签会造成高基数。
//
//nolint:gochecknoglobals
var intersectionTextOverrideTotal = promauto.NewCounterVec(prometheus.CounterOpts{
	Namespace: "controlplane",
	Subsystem: "intersection_text_override",
	Name:      "total",
	Help:      "Intersection presentation-text hot-config override outcomes by result and locale.",
}, []string{"result", "locale"})

// IntersectionTextOverrideKey 拼装 l10nKey + locale 对应的热配置 key。
func IntersectionTextOverrideKey(l10nKey string, locale string) string {
	loc := strings.TrimSpace(locale)
	if loc == "" {
		loc = "zh"
	}
	return IntersectionTextOverrideKeyPrefix + strings.TrimSpace(l10nKey) + "." + loc
}

// NewIntersectionTextResolver 返回按 l10nKey+locale 查 HotConfigStore 的解析器。
// 命中非空则覆盖 codegen 基线；未命中、空串或无 store 时返回 ok=false，
// 由调用方回落基线（fail-safe：控制面不可用不得让交集文案消失）。
func NewIntersectionTextResolver(store *HotConfigStore) func(l10nKey string, locale string) (string, bool) {
	return func(l10nKey string, locale string) (string, bool) {
		loc := strings.TrimSpace(locale)
		if loc == "" {
			loc = "zh"
		}
		if store == nil || strings.TrimSpace(l10nKey) == "" {
			intersectionTextOverrideTotal.WithLabelValues("miss", loc).Inc()
			return "", false
		}
		value := strings.TrimSpace(store.GetString(IntersectionTextOverrideKey(l10nKey, loc), ""))
		if value == "" {
			intersectionTextOverrideTotal.WithLabelValues("miss", loc).Inc()
			return "", false
		}
		intersectionTextOverrideTotal.WithLabelValues("hit", loc).Inc()
		return value, true
	}
}
