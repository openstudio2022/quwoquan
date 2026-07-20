// Package iplocation 提供评论等 UGC 写路径的客户端 IP 属地解析。
// 属地是「创建时」捕获并落库的快照（与业界一致）；读取投影只透传，
// 不在读路径二次解析。
package iplocation

import (
	"context"
	"net"
	"strings"
)

// Resolver 把客户端 IP 解析为省级属地展示串（如「浙江」），
// 解析不出时返回空串（前端则不展示属地，绝不臆造）。
//
// 生产实现需注入真实 GeoIP 库（MaxMind/纯真等）；alpha/测试使用
// NewDeterministicProvinceResolver 做确定性映射，保证契约与端云链路可验证。
type Resolver interface {
	// Resolve 返回省级属地展示串；无法解析返回 ""。
	Resolve(ip string) string
}

// clientIPContextKey 承载请求级客户端 IP（由 HTTP 适配层从受信代理头解析后注入）。
type clientIPContextKey struct{}

// WithClientIP 把受信解析出的客户端 IP 注入 context，供写路径（如创建评论）解析属地。
func WithClientIP(ctx context.Context, ip string) context.Context {
	ip = strings.TrimSpace(ip)
	if ip == "" {
		return ctx
	}
	return context.WithValue(ctx, clientIPContextKey{}, ip)
}

// ClientIPFromContext 读取请求级客户端 IP；不存在返回 ""。
func ClientIPFromContext(ctx context.Context) string {
	if ctx == nil {
		return ""
	}
	if v, ok := ctx.Value(clientIPContextKey{}).(string); ok {
		return strings.TrimSpace(v)
	}
	return ""
}

// ParseTrustedClientIP 从受信代理头解析真实客户端 IP。
// 顺序：X-Forwarded-For 首段 -> X-Real-IP -> RemoteAddr。
// 仅在网关/受信代理链路下使用，调用方负责保证头可信。
func ParseTrustedClientIP(forwardedFor, realIP, remoteAddr string) string {
	if forwardedFor = strings.TrimSpace(forwardedFor); forwardedFor != "" {
		// X-Forwarded-For: client, proxy1, proxy2 —— 取首段为最初客户端。
		first := strings.TrimSpace(strings.SplitN(forwardedFor, ",", 2)[0])
		if ip := normalizeIP(first); ip != "" {
			return ip
		}
	}
	if realIP = strings.TrimSpace(realIP); realIP != "" {
		if ip := normalizeIP(realIP); ip != "" {
			return ip
		}
	}
	if remoteAddr = strings.TrimSpace(remoteAddr); remoteAddr != "" {
		if host, _, err := net.SplitHostPort(remoteAddr); err == nil {
			if ip := normalizeIP(host); ip != "" {
				return ip
			}
		}
		if ip := normalizeIP(remoteAddr); ip != "" {
			return ip
		}
	}
	return ""
}

func normalizeIP(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	if parsed := net.ParseIP(raw); parsed != nil {
		return parsed.String()
	}
	return ""
}

// DeterministicProvinceResolver 是 alpha/测试用的确定性属地解析器：
// 对预置的 IP 段返回固定省份，其余返回 ""（绝不臆造属地）。
// 生产环境必须注入真实 GeoIP 实现替换它。
type DeterministicProvinceResolver struct {
	// prefixProvince 以 IP 前缀（如 "1.2."）映射到省份展示串。
	prefixProvince map[string]string
}

func NewDeterministicProvinceResolver() *DeterministicProvinceResolver {
	return &DeterministicProvinceResolver{
		prefixProvince: map[string]string{
			"1.2.":  "浙江",
			"5.6.":  "广东",
			"9.9.":  "北京",
			"10.0.": "上海",
		},
	}
}

func (r *DeterministicProvinceResolver) Resolve(ip string) string {
	ip = normalizeIP(ip)
	if ip == "" {
		return ""
	}
	for prefix, province := range r.prefixProvince {
		if strings.HasPrefix(ip, prefix) {
			return province
		}
	}
	return ""
}
