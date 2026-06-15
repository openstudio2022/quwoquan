package controlplane

import (
	"strings"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	rterr "quwoquan_service/runtime/errors"
)

// ErrorMessageOverrideKeyPrefix 是运营态错误提示语热配置 key 的命名空间前缀。
// 完整 key 形如 sys.error_message.USER.AUTH.otp_mismatch.zh，由 control-plane 下发，
// reload 等级为 hot（见 contracts/metadata 下 control-plane config_schema）。
const ErrorMessageOverrideKeyPrefix = "sys.error_message."

// errorMessageOverrideTotal 统计 userMessage 热配置覆盖的命中/未命中，用于计算
// override 命中率（hit / (hit+miss)）。仅按 result+locale 打标签，避免按 code
// 造成高基数；按 code 的细粒度分析交由日志/采样，不进 metrics。
//
//nolint:gochecknoglobals
var errorMessageOverrideTotal = promauto.NewCounterVec(prometheus.CounterOpts{
	Namespace: "controlplane",
	Subsystem: "error_message_override",
	Name:      "total",
	Help:      "Error user-message hot-config override outcomes by result and locale.",
}, []string{"result", "locale"})

// ErrorMessageOverrideKey 拼装 code + locale 对应的热配置 key。
func ErrorMessageOverrideKey(code string, locale string) string {
	loc := strings.TrimSpace(locale)
	if loc == "" {
		loc = "zh"
	}
	return ErrorMessageOverrideKeyPrefix + strings.TrimSpace(code) + "." + loc
}

// NewErrorMessageResolver 返回一个 rterr.UserMessageResolver：按 code+locale 查 HotConfigStore，
// 命中非空则覆盖 codegen 静态 baseline；未命中或空串回退（返回 ok=false），保证 fail-safe。
func NewErrorMessageResolver(store *HotConfigStore) rterr.UserMessageResolver {
	return func(code string, locale string) (string, bool) {
		loc := strings.TrimSpace(locale)
		if loc == "" {
			loc = "zh"
		}
		if store == nil {
			errorMessageOverrideTotal.WithLabelValues("miss", loc).Inc()
			return "", false
		}
		key := ErrorMessageOverrideKey(code, locale)
		value := strings.TrimSpace(store.GetString(key, ""))
		if value == "" {
			errorMessageOverrideTotal.WithLabelValues("miss", loc).Inc()
			return "", false
		}
		errorMessageOverrideTotal.WithLabelValues("hit", loc).Inc()
		return value, true
	}
}
