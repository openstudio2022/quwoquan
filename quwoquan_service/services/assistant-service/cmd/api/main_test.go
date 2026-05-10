package main

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestAlphaRuntimeIdentityAndConfigLoadsSameNamedOverlay(t *testing.T) {
	t.Setenv("SERVICE_NAME", "assistant-service")
	t.Setenv("APP_ENV", "alpha")
	t.Setenv("CONFIG_VERSION", "")
	t.Setenv("IMAGE_VERSION", "")

	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		t.Fatalf("resolveRuntimeIdentity() error = %v", err)
	}
	if serviceName != "assistant-service" || appEnv != "alpha" || configRoot != "" || configVersion != "" || imageVersion != "" {
		t.Fatalf("runtime identity = %q %q %q %q %q", serviceName, appEnv, configRoot, configVersion, imageVersion)
	}

	root := t.TempDir()
	writeConfig(t, root, "default", `service:
  http:
    addr: ":18080"
`)
	writeConfig(t, root, "alpha", `service:
  http:
    addr: ":18087"
`)
	writeConfig(t, root, "beta", `service:
  http:
    addr: ":18088"
`)

	cfg, err := loadRuntimeConfig(serviceName, appEnv, root, "")
	if err != nil {
		t.Fatalf("loadRuntimeConfig() error = %v", err)
	}
	if cfg.Service.HTTP.Addr != ":18087" {
		t.Fatalf("addr=%q, want alpha overlay :18087", cfg.Service.HTTP.Addr)
	}
}

func TestCurrentRuntimeEnvIsRejected(t *testing.T) {
	t.Setenv("APP_ENV", "local")
	if _, _, _, _, _, err := resolveRuntimeIdentity(); err == nil {
		t.Fatal("resolveRuntimeIdentity() should reject APP_ENV=local")
	}

	t.Setenv("APP_ENV", "integration")
	if _, _, _, _, _, err := resolveRuntimeIdentity(); err == nil {
		t.Fatal("resolveRuntimeIdentity() should reject APP_ENV=integration")
	}
}

func TestAssistantHTTPWriteTimeoutDefaultsForStreaming(t *testing.T) {
	t.Setenv("ASSISTANT_HTTP_WRITE_TIMEOUT_SECONDS", "")
	if got := assistantHTTPWriteTimeout(); got != 180*time.Second {
		t.Fatalf("write timeout=%s, want 180s", got)
	}
}

func TestGammaAllowsDeterministicModelProviderWhenGateFlagEnabled(t *testing.T) {
	t.Setenv("ALLOW_DETERMINISTIC_BETA", "")
	if _, err := buildModelProvider(providerCfg{Provider: "deterministic"}, "gamma"); err == nil {
		t.Fatal("gamma deterministic provider should require explicit gate flag")
	}
	t.Setenv("ALLOW_DETERMINISTIC_BETA", "1")
	if _, err := buildModelProvider(providerCfg{Provider: "deterministic"}, "gamma"); err != nil {
		t.Fatalf("gamma deterministic provider should be allowed by gate flag: %v", err)
	}
}

func TestSearchProviderTimeoutKeepsRealtimeBudget(t *testing.T) {
	if got := searchProviderTimeout(0); got != 8*time.Second {
		t.Fatalf("default search timeout=%s, want 8s", got)
	}
	client := searchHTTPClient(10_000)
	if client.Timeout != 10*time.Second {
		t.Fatalf("client timeout=%s, want 10s", client.Timeout)
	}
	transport, ok := client.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("transport type=%T, want *http.Transport", client.Transport)
	}
	if transport.TLSHandshakeTimeout != 10*time.Second {
		t.Fatalf("tls handshake timeout=%s, want 10s", transport.TLSHandshakeTimeout)
	}
	if got := searchProviderTimeout(45_000); got != 10*time.Second {
		t.Fatalf("capped search timeout=%s, want 10s", got)
	}
}

func TestShouldTryWeatherLookupUsesModelLocationAndSearchQueries(t *testing.T) {
	if !shouldTryWeatherLookup("", "Shenzhen weather", "", "Shenzhen", nil) {
		t.Fatal("weather intent with locationSearchName should route to weather lookup")
	}
	if !shouldTryWeatherLookup("", "outdoor plan", "", "", map[string]any{
		"searchQueries": []any{
			map[string]any{"dimension": "weather", "query": "Shenzhen forecast"},
		},
	}) {
		t.Fatal("weather searchQueries should route to weather lookup")
	}
}

func TestShouldNotTryWeatherLookupForNonWeatherQuestionEvenWithLocation(t *testing.T) {
	if shouldTryWeatherLookup(
		"knowledge_general",
		"云服务配置推荐",
		"北京",
		"Beijing",
		map[string]any{
			"searchQueries": []any{
				map[string]any{"dimension": "规格/价格", "query": "云服务器 ECS 实例规格 价格"},
			},
		},
	) {
		t.Fatal("non-weather cloud query should not be hijacked by weather lookup")
	}
}

func TestWeatherAuthorityReferencesPrioritizeNationalAndRegionalSources(t *testing.T) {
	summary := withLocalWeatherAuthoritySummary("Hangzhou tian qi", "杭州，浙江", "MET Norway", "MET Norway 实时天气：杭州。")
	if !strings.Contains(summary, "国家级气象服务入口与可解析的省/自治区/直辖市气象局") {
		t.Fatalf("summary should foreground national and regional authority sources: %s", summary)
	}
	if !strings.Contains(summary, "MET Norway 仅作为") {
		t.Fatalf("summary should demote structured provider to supplement: %s", summary)
	}
	refs := withLocalWeatherAuthorityReferences("Hangzhou tian qi", "杭州，浙江", []map[string]any{
		{
			"title":  "Open-Meteo Forecast API - 杭州，浙江",
			"url":    "https://open-meteo.com/en/docs",
			"source": "open_meteo_forecast",
		},
	})
	if len(refs) < 5 {
		t.Fatalf("refs len=%d, want national/regional authority refs plus API ref", len(refs))
	}
	want := []string{
		"weather_com_cn",
		"national_meteorological_center",
		"china_meteorological_administration",
		"zhejiang_meteorological_bureau",
		"open_meteo_forecast",
	}
	for i, source := range want {
		if refs[i]["source"] != source {
			t.Fatalf("refs[%d].source=%v, want %s; refs=%#v", i, refs[i]["source"], source, refs)
		}
		if refs[i]["rank"] != i+1 {
			t.Fatalf("refs[%d].rank=%v, want %d", i, refs[i]["rank"], i+1)
		}
	}
}

func TestExtractDuckDuckGoResultsIncludesURLAndSourceHost(t *testing.T) {
	raw := `
<div class="result">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fsupport.huaweicloud.com%2Fprice-desc-ecs%2Fecs_01_0001.html">弹性云服务器 ECS 价格详情 - 华为云</a>
  <div class="result__snippet">官方价格详情页，包含按需和包年包月说明。</div>
</div>`
	summary, refs := extractDuckDuckGoResults(raw)
	if !strings.Contains(summary, "官方价格详情页") {
		t.Fatalf("summary=%q should include snippet", summary)
	}
	if len(refs) != 1 {
		t.Fatalf("refs len=%d, want 1", len(refs))
	}
	if refs[0]["url"] != "https://support.huaweicloud.com/price-desc-ecs/ecs_01_0001.html" {
		t.Fatalf("url=%v", refs[0]["url"])
	}
	if refs[0]["source"] != "support.huaweicloud.com" {
		t.Fatalf("source=%v", refs[0]["source"])
	}
}

func TestPreferredSearchQueriesKeepsStructuredAndFallbackQueries(t *testing.T) {
	queries := preferredSearchQueries(
		map[string]any{
			"query": "云桌面 按需计费 关机 还收费吗",
			"searchQueries": []any{
				map[string]any{"dimension": "billing", "query": "云桌面 按需计费 关机 收费"},
				map[string]any{"dimension": "pricing", "query": "云桌面 按需计费 价格"},
			},
		},
		"云桌面 按需计费 关机 还收费吗",
	)
	if len(queries) != 3 {
		t.Fatalf("queries=%v, want 3 unique queries", queries)
	}
	if !containsString(queries, "云桌面 按需计费 关机 收费") {
		t.Fatalf("queries=%v should include structured billing query", queries)
	}
	if !containsString(queries, "云桌面 按需计费 价格") {
		t.Fatalf("queries=%v should include structured pricing query", queries)
	}
	if !containsString(queries, "云桌面 按需计费 关机 还收费吗") {
		t.Fatalf("queries=%v should include fallback query", queries)
	}
}

func containsString(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}

func writeConfig(t *testing.T, root, env, content string) {
	t.Helper()
	dir := filepath.Join(root, "configs", "assistant-service", env)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", dir, err)
	}
	if err := os.WriteFile(filepath.Join(dir, "config.yaml"), []byte(content), 0o644); err != nil {
		t.Fatalf("write config %s: %v", env, err)
	}
}
