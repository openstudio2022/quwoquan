package bootstrap

import (
	"fmt"
	"strings"

	"quwoquan_service/runtime/servicekit"
	"quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/searchbackend"
)

// config 是 search-service 的声明式配置：通用段内嵌 servicekit.BaseConfig，
// Mongo 与 Redis scene 按「声明即装配」交给骨架（DEC-028），env 覆盖键由服务名
// 派生前缀 SEARCH 拼出。
//
// contentService.baseUrl 用 envAbsolute 逐字保留 CONTENT_SERVICE_BASE_URL：
// 它是跨服务调用地址的统一注入键（servicekit.ServiceBaseURLKey 规约），不属于
// 本服务可单方面加前缀的键。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	ES searchbackend.ESConfig `yaml:"es"`

	// Mongo 是 query log、feedback、搜索词热力读模型、RecentSearchState 与账号
	// 处置投影的权威存储；四环境使用同一套完整生产组合，缺 uri/database 由
	// 骨架的 required 校验 fail-closed。
	Mongo servicekit.MongoConfig `yaml:"mongo"`

	Redis struct {
		General servicekit.RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
		Rec     servicekit.RedisSceneConfig `yaml:"rec" envPrefix:"REDIS_REC"`
	} `yaml:"redis"`

	// Ranking 只拥有搜索专属的分数变换；实验策略从 Product Ops 投影而来，
	// 不在服务配置里产生。
	Ranking struct {
		TermHeatBoost float64 `yaml:"termHeatBoost"`
	} `yaml:"ranking"`

	ContentService struct {
		BaseURL string `yaml:"baseUrl" envAbsolute:"CONTENT_SERVICE_BASE_URL"`
	} `yaml:"contentService"`

	// Serving 是检索链路的背压与热点缓存上界。迁移前它们只有启动期 env 兜底
	// 默认值，非正值会被静默替换成默认值；现在由配置快照声明，非正值即失败。
	Serving struct {
		MaxInflight            int `yaml:"max_inflight" env:"MAX_INFLIGHT"`
		RelatedTermsCacheTTLMs int `yaml:"related_terms_cache_ttl_ms" env:"RELATED_TERMS_CACHE_TTL_MS"`
		RelatedTermsCacheMax   int `yaml:"related_terms_cache_max" env:"RELATED_TERMS_CACHE_MAX"`
	} `yaml:"serving"`
}

// retiredSnapshotSections 是已被 BaseConfig 标准段取代的配置顶层键。CONFIG_VERSION
// 钉住的是配置包，一个仍带旧段的快照被挂进来时，新代码只会读到零值；显式拒收
// 才能让「注入的快照 = 代码读取的形状」保持单轨。
var retiredSnapshotSections = []string{"accountSecurityAuthority"}

func rejectRetiredSearchSnapshotSections(raw []byte) error {
	for _, line := range strings.Split(string(raw), "\n") {
		key, _, found := strings.Cut(line, ":")
		if !found || key != strings.TrimLeft(key, " \t") {
			continue
		}
		for _, retired := range retiredSnapshotSections {
			if key == retired {
				return fmt.Errorf(
					"%s is retired; use user_account_security_authority", retired,
				)
			}
		}
	}
	return nil
}

// validateSearchConfig 施加搜索领域的配置下界。它在骨架的 required 校验之后、
// 任何观测栈与基础设施连接之前执行，因此非法配置不会产生外部副作用。
func validateSearchConfig(cfg *config) error {
	// 索引名迁移前由启动期默认值兜底，那会让「快照没渲染出索引名」这种注入
	// 缺口伪装成一次正常启动，并把文档写进一个没人查询的别名。
	if strings.TrimSpace(cfg.ES.Index) == "" {
		return fmt.Errorf("es.index is required")
	}
	for _, bound := range []struct {
		name  string
		value int
	}{
		{"serving.max_inflight", cfg.Serving.MaxInflight},
		{"serving.related_terms_cache_ttl_ms", cfg.Serving.RelatedTermsCacheTTLMs},
		{"serving.related_terms_cache_max", cfg.Serving.RelatedTermsCacheMax},
		{
			"user_account_security_authority.timeout_ms",
			cfg.UserAccountSecurityAuthority.TimeoutMs,
		},
	} {
		if bound.value <= 0 {
			return fmt.Errorf(
				"%s must be a positive integer, got %d", bound.name, bound.value,
			)
		}
	}
	return nil
}
