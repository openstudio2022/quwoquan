// Package iplocation 提供评论 IP 属地的生产离线库适配器。
package iplocation

import (
	"net"
	"strings"
	"time"

	"github.com/lionsoul2014/ip2region/binding/golang/service"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var lookupTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "content_comment_ip_location_lookup_total",
		Help: "Comment IP location lookups split by terminal outcome.",
	},
	[]string{"outcome"},
)

var dataAgeDays = promauto.NewGauge(
	prometheus.GaugeOpts{
		Name: "content_comment_ip_location_data_age_days",
		Help: "Age in days of the loaded comment IP location database.",
	},
)

// IP2RegionResolver 使用并发安全的 IPv4/IPv6 xdb 离线服务解析属地。
// 原始 IP 不会被保存或写入日志，调用方只接收省级或国家级展示串。
type IP2RegionResolver struct {
	service *service.Ip2Region
}

// NewIP2RegionResolver 在启动阶段把两个 xdb 数据库装配为查询服务。
// 数据库缺失或损坏时直接返回错误，禁止生产环境静默降级。
func NewIP2RegionResolver(
	ipv4DatabasePath string,
	ipv6DatabasePath string,
) (*IP2RegionResolver, error) {
	resolverService, err := service.NewIp2RegionWithPath(
		strings.TrimSpace(ipv4DatabasePath),
		strings.TrimSpace(ipv6DatabasePath),
	)
	if err != nil {
		return nil, err
	}
	return &IP2RegionResolver{service: resolverService}, nil
}

// Close 释放离线库查询资源。
func (r *IP2RegionResolver) Close() {
	if r == nil || r.service == nil {
		return
	}
	r.service.CloseTimeout(5 * time.Second)
}

// ObserveDataVersion 发布离线库数据新鲜度，供告警在强制过期前提前预警。
func ObserveDataVersion(versionDate time.Time, now time.Time) {
	age := now.UTC().Sub(versionDate.UTC()).Hours() / 24
	if age < 0 {
		age = 0
	}
	dataAgeDays.Set(age)
}

// Resolve 返回境内省级、境外国家级属地；无效、私网或无法解析时返回空串。
func (r *IP2RegionResolver) Resolve(ip string) string {
	if r == nil || r.service == nil {
		lookupTotal.WithLabelValues("unavailable").Inc()
		return ""
	}
	ip = strings.TrimSpace(ip)
	parsedIP := net.ParseIP(ip)
	if parsedIP == nil || isPrivateOrLocal(parsedIP) {
		lookupTotal.WithLabelValues("invalid").Inc()
		return ""
	}
	region, err := r.service.Search(parsedIP.String())
	if err != nil {
		lookupTotal.WithLabelValues("error").Inc()
		return ""
	}
	location := DisplayLocation(region)
	if location == "" {
		lookupTotal.WithLabelValues("not_found").Inc()
		return ""
	}
	lookupTotal.WithLabelValues("ok").Inc()
	return location
}

func isPrivateOrLocal(ip net.IP) bool {
	return ip.IsPrivate() ||
		ip.IsLoopback() ||
		ip.IsUnspecified() ||
		ip.IsLinkLocalUnicast() ||
		ip.IsLinkLocalMulticast() ||
		ip.IsMulticast()
}

// ip2region 数据格式为 Country|Province|City|ISP|ISO-Alpha2。
func DisplayLocation(region string) string {
	parts := strings.Split(region, "|")
	if len(parts) < 5 {
		return ""
	}
	country := cleanRegionPart(parts[0])
	province := cleanRegionPart(parts[1])
	isoCode := strings.ToUpper(cleanRegionPart(parts[4]))
	if isoCode == "CN" || country == "中国" || strings.EqualFold(country, "China") {
		return normalizeChineseProvince(province)
	}
	return country
}

func cleanRegionPart(value string) string {
	value = strings.TrimSpace(value)
	if value == "" || value == "0" {
		return ""
	}
	return value
}

func normalizeChineseProvince(province string) string {
	province = cleanRegionPart(province)
	for _, suffix := range []string{
		"维吾尔自治区",
		"壮族自治区",
		"回族自治区",
		"特别行政区",
		"自治区",
		"省",
		"市",
	} {
		if strings.HasSuffix(province, suffix) {
			return strings.TrimSpace(strings.TrimSuffix(province, suffix))
		}
	}
	return province
}
