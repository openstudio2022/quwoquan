package bootstrap

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	embeddingapp "quwoquan_service/services/content-service/internal/content/post/application/embedding"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	embeddinginfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/embedding"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/objectstorage"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/placeindex"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	postruntimeconfig "quwoquan_service/services/content-service/internal/content/post/infrastructure/runtimeconfig"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/searchindex"
)

func contentSliceWorkload() bool {
	return postruntimeconfig.ContentSliceWorkload()
}

// validateContentConfig 承接迁移前 preflightConfig 的全部领域校验，在骨架完成
// env 覆盖与 required 校验之后、任何基础设施连接之前执行：非法配置不产生外部
// 副作用。分档口径仍按 cfg.Environment（骨架从进程身份写入）。
func validateContentConfig(cfg *config) error {
	appEnv := cfg.Environment
	// SEARCH_ES_* 是 content 与 search 共用同一集群的跨服务注入键，不能声明成
	// 本服务的 env tag（service-core 单进程内会与 search-service 抢同一个键）。
	// 因此这一段保持显式覆盖，并放在校验的最前面：下面的 es.endpoints 在场判定
	// 必须看到覆盖后的值。
	searchindex.ApplyESEnvOverrides(&cfg.ES)
	for _, scene := range []struct {
		name string
		cfg  redisSceneCfg
	}{
		{name: "rec", cfg: cfg.Redis.Rec},
		{name: "general", cfg: cfg.Redis.General},
		{name: "realtime", cfg: cfg.Redis.Realtime},
	} {
		if err := validateRemoteRedisScene(scene.name, scene.cfg); err != nil {
			return fmt.Errorf("%s content runtime: %w", appEnv, err)
		}
	}
	// 凭据与上游地址经 secretRefs/overrides 渲染进快照。渲染缺失时快照里留下
	// 未展开的 `${KEY}` 字面量，它对 required 校验是「在场」，对上游客户端的
	// 「url 为空则不装配」判据也是「在场」——服务于是带着一个假地址起来，
	// 每次调用都失败，且失败表现为无效 URL 而不是配置缺失。迁移前
	// resolveMongoURI/resolveReportDSN 对存储凭据保留了这条判据，此处把同一
	// 强度覆盖到全部渲染型上游地址。
	for _, item := range []struct {
		name  string
		value string
	}{
		{name: "mongo.uri", value: cfg.Mongo.URI},
		{name: "postgres.report_dsn", value: cfg.Postgres.ReportDSN},
		{name: "rec_model_service.url", value: cfg.RecModelService.URL},
		{name: "tag_service.url", value: cfg.TagService.URL},
		{name: "user_account_security_authority.base_url", value: cfg.UserAccountSecurityAuthority.BaseURL},
	} {
		if isUnrenderedConfigPlaceholder(item.value) {
			return fmt.Errorf(
				"%s content runtime %s is an unrendered placeholder %q",
				appEnv, item.name, strings.TrimSpace(item.value),
			)
		}
	}
	if cfg.Feed.ActiveSupplyCacheTTLMS <= 0 ||
		cfg.Feed.ActiveSupplyCacheJitterMS < 0 ||
		cfg.Feed.ActiveSupplyCacheJitterMS >= cfg.Feed.ActiveSupplyCacheTTLMS {
		return fmt.Errorf(
			"%s content runtime requires feed active-supply cache ttl > jitter >= 0",
			appEnv,
		)
	}
	if cfg.Feed.MaxInflight <= 0 ||
		cfg.Feed.MaximumRecallSources <= 0 ||
		cfg.Feed.MaximumUnterminatedCallsPerSource <= 0 {
		return fmt.Errorf(
			"%s content runtime requires positive feed owner inflight, recall source and per-source unterminated-call budgets",
			appEnv,
		)
	}
	if err := validateFeedQuotaPolicies(cfg.Feed); err != nil {
		return fmt.Errorf("%s content runtime requires valid global feed admission: %w", appEnv, err)
	}
	if err := validateAuthorityConfig(cfg, appEnv); err != nil {
		return err
	}
	if err := validateTagServiceConfig(cfg, appEnv); err != nil {
		return err
	}
	if err := validateCommentRateLimitConfig(cfg, appEnv); err != nil {
		return err
	}
	if err := validateIPLocationConfig(cfg, appEnv, time.Now().UTC()); err != nil {
		return err
	}
	// OSS endpoint 与 access key 只有 binding 一条读取轨：这里提前解析一次，
	// 让缺 material 在任何连接之前 fail-closed，而不是等媒体装配阶段。
	if _, err := objectstorage.LoadBinding(
		appEnv, runtimeconfig.EnvRuntimeConfigProvider{},
	); err != nil {
		return fmt.Errorf("%s content runtime object storage binding: %w", appEnv, err)
	}
	if appEnv != "alpha" &&
		strings.TrimSpace(os.Getenv(accountClosureSubjectHMACEnv)) == "" {
		return fmt.Errorf(
			"%s content runtime requires %s",
			appEnv,
			accountClosureSubjectHMACEnv,
		)
	}
	if cfg.ES.Enabled && len(cfg.ES.Endpoints) == 0 {
		return fmt.Errorf("%s content runtime enables search projection but has no es.endpoints/SEARCH_ES_ENDPOINTS", appEnv)
	}
	if appEnv != "alpha" && cfg.Embedding.Enabled && !contentSliceWorkload() {
		if _, err := resolveContentEmbeddingGateway(appEnv); err != nil {
			return fmt.Errorf("%s content runtime embedding binding: %w", appEnv, err)
		}
	}
	return nil
}

// isUnrenderedConfigPlaceholder 判定配置快照里的值是否为未展开的 `${KEY}`
// 占位符。
func isUnrenderedConfigPlaceholder(value string) bool {
	trimmed := strings.TrimSpace(value)
	return strings.HasPrefix(trimmed, "${") && strings.HasSuffix(trimmed, "}")
}

func resolveContentEmbeddingGateway(
	appEnv string,
) (embeddingapp.EmbeddingGateway, error) {
	return embeddinginfra.LoadEmbeddingGateway(
		appEnv,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
}

// validateAuthorityConfig 保留迁移前对账号安全 authority 配置段的强度：骨架
// 的 required 只覆盖 base_url 一类字符串，超时是正整数这条仍归领域校验。
func validateAuthorityConfig(cfg *config, appEnv string) error {
	if strings.TrimSpace(cfg.UserAccountSecurityAuthority.BaseURL) == "" {
		return fmt.Errorf(
			"%s content runtime requires user_account_security_authority.base_url",
			appEnv,
		)
	}
	if cfg.UserAccountSecurityAuthority.TimeoutMs <= 0 {
		return fmt.Errorf(
			"%s content runtime requires positive user_account_security_authority.timeout_ms",
			appEnv,
		)
	}
	return nil
}

func validateTagServiceConfig(cfg *config, appEnv string) error {
	if strings.TrimSpace(cfg.TagService.URL) == "" {
		return fmt.Errorf(
			"%s content runtime requires tag_service.url",
			appEnv,
		)
	}
	if cfg.TagService.TimeoutMs <= 0 {
		return fmt.Errorf(
			"%s content runtime requires positive tag_service.timeout_ms",
			appEnv,
		)
	}
	return nil
}

func validateCommentRateLimitConfig(cfg *config, appEnv string) error {
	rateLimit := cfg.CommentRateLimit
	if rateLimit.BurstWindowSeconds <= 0 ||
		rateLimit.BurstMax <= 0 ||
		rateLimit.DailyWindowSeconds <= 0 ||
		rateLimit.DailyMax <= 0 {
		return fmt.Errorf(
			"%s content runtime requires positive comment_rate_limit windows and maxima",
			appEnv,
		)
	}
	if rateLimit.BurstWindowSeconds >= rateLimit.DailyWindowSeconds {
		return fmt.Errorf(
			"%s content runtime requires comment_rate_limit burst window shorter than daily window",
			appEnv,
		)
	}
	if rateLimit.BurstMax > rateLimit.DailyMax {
		return fmt.Errorf(
			"%s content runtime requires comment_rate_limit burst_max <= daily_max",
			appEnv,
		)
	}
	return nil
}

func validateIPLocationConfig(cfg *config, appEnv string, now time.Time) error {
	provider := strings.ToLower(strings.TrimSpace(cfg.IPLocation.Provider))
	if appEnv == "alpha" {
		if provider != "deterministic" {
			return fmt.Errorf(
				"alpha content runtime requires ip_location.provider=deterministic, got %q",
				cfg.IPLocation.Provider,
			)
		}
		return nil
	}
	if provider != "ip2region" {
		return fmt.Errorf(
			"%s content runtime requires ip_location.provider=ip2region, got %q",
			appEnv,
			cfg.IPLocation.Provider,
		)
	}
	if strings.TrimSpace(cfg.IPLocation.IPv4DatabasePath) == "" {
		return fmt.Errorf(
			"%s content runtime requires ip_location.ipv4_database_path",
			appEnv,
		)
	}
	if strings.TrimSpace(cfg.IPLocation.IPv6DatabasePath) == "" {
		return fmt.Errorf(
			"%s content runtime requires ip_location.ipv6_database_path",
			appEnv,
		)
	}
	dataVersion := strings.TrimSpace(cfg.IPLocation.DataVersion)
	versionDate, err := time.Parse("2006-01-02", dataVersion)
	if err != nil {
		return fmt.Errorf(
			"%s content runtime requires ip_location.data_version in YYYY-MM-DD format: %w",
			appEnv,
			err,
		)
	}
	age := now.Sub(versionDate)
	if age < -48*time.Hour {
		return fmt.Errorf(
			"%s content runtime ip_location.data_version %s is in the future",
			appEnv,
			dataVersion,
		)
	}
	if age > 45*24*time.Hour {
		return fmt.Errorf(
			"%s content runtime ip_location database is stale: version=%s age=%s",
			appEnv,
			dataVersion,
			age.Round(time.Hour),
		)
	}
	return nil
}

func validateRemoteRedisScene(name string, cfg redisSceneCfg) error {
	mode := strings.ToLower(strings.TrimSpace(cfg.Mode))
	if mode == "" {
		mode = "standalone"
	}
	switch mode {
	case "standalone":
		if strings.TrimSpace(cfg.Addr) == "" {
			return fmt.Errorf("redis.%s.mode=standalone requires redis.%s.addr", name, name)
		}
	case "cluster":
		if len(cfg.Addrs) == 0 {
			return fmt.Errorf("redis.%s.mode=cluster requires redis.%s.addrs", name, name)
		}
	case "memory":
		return fmt.Errorf("redis.%s.mode=memory is forbidden in production composition", name)
	default:
		return fmt.Errorf("redis.%s.mode must be standalone|cluster, got %q", name, cfg.Mode)
	}
	return nil
}

func hostname() string {
	h, _ := os.Hostname()
	if h == "" {
		h = "unknown"
	}
	return h
}

// projectorAdapter bridges content read-model projectors to ports.Projector.
type projectorAdapter struct {
	embedding *recinfra.EmbeddingProjector
	search    *searchindex.Projector
	place     *placeindex.PlaceProjector
}

func (a *projectorAdapter) Project(ctx context.Context, event ports.ProjectorEvent) error {
	projectorEvent := recinfra.ProjectorEvent{
		Type:          event.Type,
		AggregateType: event.AggregateType,
		AggregateID:   event.AggregateID,
		Payload:       event.Payload,
		OccurredAt:    event.OccurredAt,
	}
	if a.embedding != nil {
		if err := a.embedding.Project(ctx, projectorEvent); err != nil {
			return err
		}
	}
	// Each projector is driven by its own durable relay. Returning an error keeps
	// that projector's checkpoint replayable without affecting the committed Post.
	if a.search != nil {
		if err := a.search.Project(ctx, event); err != nil {
			return err
		}
	}
	// First-party place index (location.place) shares the same ES client but owns
	// an independent checkpoint.
	if a.place != nil {
		if err := a.place.Project(ctx, event); err != nil {
			return err
		}
	}
	return nil
}

func contentOSSEndpoint(raw string, useSSL bool) string {
	endpoint := strings.TrimRight(strings.TrimSpace(raw), "/")
	if endpoint == "" || strings.Contains(endpoint, "://") {
		return endpoint
	}
	if useSSL {
		return "https://" + endpoint
	}
	return "http://" + endpoint
}

func resolveStoryRuntimeConfig() postapp.StoryRuntimeConfig {
	return postapp.StoryRuntimeConfig{
		FeatureFlags: map[string]bool{
			"enable_create_action_entry": parseBoolEnv(
				"CONTENT_FLAG_ENABLE_CREATE_ACTION_ENTRY",
				false,
			),
			"enable_unified_create_editor": parseBoolEnv(
				"CONTENT_FLAG_ENABLE_UNIFIED_CREATE_EDITOR",
				true,
			),
			"enable_identity_based_surfaces": parseBoolEnv(
				"CONTENT_FLAG_ENABLE_IDENTITY_BASED_SURFACES",
				true,
			),
			"enable_identity_share_template": parseBoolEnv(
				"CONTENT_FLAG_ENABLE_IDENTITY_SHARE_TEMPLATE",
				true,
			),
			"enable_assistant_content_identity_index": parseBoolEnv(
				"CONTENT_FLAG_ENABLE_ASSISTANT_CONTENT_IDENTITY_INDEX",
				true,
			),
		},
		ExperimentBucket: envOrDefault(
			"CONTENT_STORY_EXPERIMENT_BUCKET",
			"local_story_enabled",
		),
		CurrentStage: envOrDefault("CONTENT_STORY_CURRENT_STAGE", "100%"),
		CanaryMatrix: []postapp.StoryCanaryStage{
			{Stage: "5%", RolloutPercent: 5},
			{Stage: "20%", RolloutPercent: 20},
			{Stage: "50%", RolloutPercent: 50},
			{Stage: "100%", RolloutPercent: 100},
		},
	}
}

// envOrDefault 只服务于 story 灰度这类「不进配置快照」的进程级实验开关：
// 它们不是环境装配契约的一部分，因此不走声明式 config struct。
func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func parseBoolEnv(key string, fallback bool) bool {
	switch strings.TrimSpace(strings.ToLower(os.Getenv(key))) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}

func collaborativeRecallRollbackDisabled() bool {
	return parseBoolEnv("QWQ_DISABLE_COLLABORATIVE_RECALL_SOURCES", false) ||
		parseBoolEnv("DISABLE_COLLABORATIVE_RECALL_SOURCES", false) ||
		parseBoolEnv("disable_collaborative_recall_sources", false)
}

// intersectionRecallRollbackDisabled 关闭交集召回通道（装配级回滚）。
// 关闭后交集回到「只解释、不供给」：附着与展示不受影响，排序侧的交集边权特征
// 也仍在（它由 featureStore 注入），只是不再由交集边拉入候选。
func intersectionRecallRollbackDisabled() bool {
	return parseBoolEnv("QWQ_DISABLE_INTERSECTION_RECALL_SOURCE", false) ||
		parseBoolEnv("DISABLE_INTERSECTION_RECALL_SOURCE", false) ||
		parseBoolEnv("disable_intersection_recall_source", false)
}

// dailyAffinityDecayCheckInterval is the replica check cadence; the per-day Redis lock makes the
// actual decay run at most once per UTC day across all replicas.
const dailyAffinityDecayCheckInterval = time.Hour
