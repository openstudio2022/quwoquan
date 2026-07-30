package intersection

import (
	"strings"
	"sync/atomic"
)

// 运营态文案覆盖接入点。
//
// 基线来自 registry.presentationText 经 codegen 的表（每条带 L10nKey）；
// 本文件让同一条 L10nKey 可被控制面热配置覆盖：改一句文案不发端也不发服务。
// 依赖反转与 runtime/errors 的 UserMessageResolver 同构——本包不认识 control-plane，
// 由进程装配把 controlplane.NewIntersectionTextResolver(hotStore) 注册进来。

// TextResolver 按 l10nKey + locale 返回运营态覆盖文案。
// 返回 ok=false 或空串时回落 codegen 基线（fail-safe）。
type TextResolver func(l10nKey string, locale string) (string, bool)

// DefaultTextLocale 是无请求语言信息时的渲染语言。
const DefaultTextLocale = "zh"

//nolint:gochecknoglobals
var (
	textResolver atomic.Pointer[TextResolver]
	textLocale   atomic.Pointer[string]
)

// SetTextResolver 注册运营态文案覆盖解析器。传 nil 恢复纯基线渲染。
func SetTextResolver(resolver TextResolver) {
	if resolver == nil {
		textResolver.Store(nil)
		return
	}
	textResolver.Store(&resolver)
}

// SetTextLocale 设置当前进程的交集渲染语言。空值回落 DefaultTextLocale。
func SetTextLocale(locale string) {
	value := strings.TrimSpace(locale)
	if value == "" {
		textLocale.Store(nil)
		return
	}
	textLocale.Store(&value)
}

// activeTextLocale 取当前渲染语言。
func activeTextLocale() string {
	if v := textLocale.Load(); v != nil && strings.TrimSpace(*v) != "" {
		return *v
	}
	return DefaultTextLocale
}

// overrideText 查一条 l10nKey 的运营态覆盖文案；未注册解析器或未命中返回 ok=false。
func overrideText(l10nKey string) (string, bool) {
	key := strings.TrimSpace(l10nKey)
	if key == "" {
		return "", false
	}
	holder := textResolver.Load()
	if holder == nil {
		return "", false
	}
	resolver := *holder
	if resolver == nil {
		return "", false
	}
	value, ok := resolver(key, activeTextLocale())
	if !ok {
		return "", false
	}
	value = strings.TrimSpace(value)
	if value == "" {
		return "", false
	}
	return value, true
}
