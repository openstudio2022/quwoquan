package main

import (
	"context"
	"fmt"
	"os"
	configrelease "quwoquan_service/runtime/configrelease"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	runtimeconfig "quwoquan_service/runtime/config"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	embeddingapp "quwoquan_service/services/content-service/internal/content/post/application/embedding"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	embeddinginfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/embedding"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/placeindex"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/searchindex"
)

func contentSliceWorkload() bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("QWQ_WORKLOAD"))) {
	case "content-release", "content-commercial":
		return true
	default:
		return false
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "content-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")

	if !isValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	// Enforce explicit config version in prod so rollout always binds image+config.
	if requiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod":
		return true
	default:
		return false
	}
}

func getenvOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func mergeConfigFile(cfg *config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err := yaml.Unmarshal(raw, cfg); err != nil {
		return fmt.Errorf("parse %s: %w", path, err)
	}
	return nil
}

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return config{}, err
	}
	if err := mergeConfigFile(&cfg, path); err != nil {
		return config{}, fmt.Errorf("read generated runtime config: %w", err)
	}
	return cfg, nil
}

func validateRuntimeConfigurationIdentity(cfg config, configVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	return nil
}

func preflightConfig(cfg config, appEnv string) error {
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
	if resolveMongoURI(cfg) == "" {
		return fmt.Errorf("%s content runtime requires mongo.uri/MONGO_URI", appEnv)
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
	if err := validateAccountSecurityAuthorityConfig(cfg, appEnv); err != nil {
		return err
	}
	if err := validateTagServiceConfig(cfg, appEnv); err != nil {
		return err
	}
	if resolveReportDSN(cfg) == "" {
		return fmt.Errorf("%s content runtime requires postgres.report_dsn/REPORT_DATABASE_URL", appEnv)
	}
	if err := validateCommentRateLimitConfig(cfg, appEnv); err != nil {
		return err
	}
	if err := validateIPLocationConfig(cfg, appEnv, time.Now().UTC()); err != nil {
		return err
	}
	requiredOSS := []struct {
		name  string
		value string
	}{
		{name: "oss.endpoint/CONTENT_OSS_ENDPOINT", value: getenvOrDefault("CONTENT_OSS_ENDPOINT", cfg.OSS.Endpoint)},
		{name: "oss.bucket/CONTENT_OSS_BUCKET", value: getenvOrDefault("CONTENT_OSS_BUCKET", cfg.OSS.Bucket)},
		{name: "oss.region/CONTENT_OSS_REGION", value: getenvOrDefault("CONTENT_OSS_REGION", cfg.OSS.Region)},
		{name: "oss.access_key_id/CONTENT_OSS_ACCESS_KEY_ID", value: getenvOrDefault("CONTENT_OSS_ACCESS_KEY_ID", cfg.OSS.AccessKeyID)},
		{name: "oss.access_key_secret/CONTENT_OSS_ACCESS_KEY_SECRET", value: getenvOrDefault("CONTENT_OSS_ACCESS_KEY_SECRET", cfg.OSS.AccessKeySecret)},
	}
	for _, item := range requiredOSS {
		if strings.TrimSpace(item.value) == "" {
			return fmt.Errorf("%s content runtime requires %s", appEnv, item.name)
		}
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

func resolveContentEmbeddingGateway(
	appEnv string,
) (embeddingapp.EmbeddingGateway, error) {
	return embeddinginfra.LoadEmbeddingGateway(
		appEnv,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
}

func validateAccountSecurityAuthorityConfig(cfg config, appEnv string) error {
	if strings.TrimSpace(cfg.AccountSecurityAuthority.BaseURL) == "" {
		return fmt.Errorf(
			"%s content runtime requires accountSecurityAuthority.baseUrl",
			appEnv,
		)
	}
	if cfg.AccountSecurityAuthority.TimeoutMS <= 0 {
		return fmt.Errorf(
			"%s content runtime requires positive accountSecurityAuthority.timeoutMs",
			appEnv,
		)
	}
	return nil
}

func validateTagServiceConfig(cfg config, appEnv string) error {
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

func validateCommentRateLimitConfig(cfg config, appEnv string) error {
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

func validateIPLocationConfig(cfg config, appEnv string, now time.Time) error {
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

// applyEnvOverrides applies environment variable overrides to all config sections.
// Env vars take precedence over config.yaml values — intended for CI/CD injection.
//
// Rec Redis overrides:
//
//	CONTENT_REDIS_REC_MODE         standalone | cluster
//	CONTENT_REDIS_REC_ADDR         host:port  (standalone)
//	CONTENT_REDIS_REC_ADDRS        host1:port,host2:port,...  (cluster)
//	CONTENT_REDIS_REC_PASSWORD     password
//	CONTENT_REDIS_REC_TLS          true | 1
//
// General Redis overrides:
//
//	CONTENT_REDIS_GENERAL_MODE, _ADDR, _ADDRS, _PASSWORD, _TLS  (same pattern)
//
// RecModelService overrides:
//
//	REC_MODEL_SERVICE_URL, REC_MODEL_SERVICE_ENABLED, REC_MODEL_SERVICE_TIMEOUT_MS
//
// Tag taxonomy endpoint material:
//
//	TAG_SERVICE_URL, TAG_SERVICE_TIMEOUT_MS
//
// IP location overrides:
//
//	CONTENT_IP_LOCATION_PROVIDER, CONTENT_IP_LOCATION_IPV4_DATABASE_PATH,
//	CONTENT_IP_LOCATION_IPV6_DATABASE_PATH, CONTENT_IP_LOCATION_DATA_VERSION
func applyEnvOverrides(cfg *config) {
	applyRedisSceneEnv("CONTENT_REDIS_REC", &cfg.Redis.Rec)
	applyRedisSceneEnv("CONTENT_REDIS_GENERAL", &cfg.Redis.General)
	applyRedisSceneEnv("CONTENT_REDIS_REALTIME", &cfg.Redis.Realtime)
	searchindex.ApplyESEnvOverrides(&cfg.ES)

	// MongoDB
	if v := os.Getenv("MONGO_URI"); v != "" {
		cfg.Mongo.URI = v
	}

	// Comment IP location offline database.
	if v := os.Getenv("CONTENT_IP_LOCATION_PROVIDER"); v != "" {
		cfg.IPLocation.Provider = v
	}
	if v := os.Getenv("CONTENT_IP_LOCATION_IPV4_DATABASE_PATH"); v != "" {
		cfg.IPLocation.IPv4DatabasePath = v
	}
	if v := os.Getenv("CONTENT_IP_LOCATION_IPV6_DATABASE_PATH"); v != "" {
		cfg.IPLocation.IPv6DatabasePath = v
	}
	if v := os.Getenv("CONTENT_IP_LOCATION_DATA_VERSION"); v != "" {
		cfg.IPLocation.DataVersion = v
	}

	// RecModelService
	if v := os.Getenv("REC_MODEL_SERVICE_URL"); v != "" {
		cfg.RecModelService.URL = v
	}
	if v := os.Getenv("REC_MODEL_SERVICE_ENABLED"); v != "" {
		if enabled, err := strconv.ParseBool(v); err == nil {
			cfg.RecModelService.Enabled = enabled
		}
	}
	if v := os.Getenv("REC_MODEL_SERVICE_TIMEOUT_MS"); v != "" {
		if ms, err := strconv.Atoi(v); err == nil && ms > 0 {
			cfg.RecModelService.TimeoutMs = ms
		}
	}
	if v := os.Getenv("TAG_SERVICE_URL"); v != "" {
		cfg.TagService.URL = v
	}
	if v := os.Getenv("TAG_SERVICE_TIMEOUT_MS"); v != "" {
		if ms, err := strconv.Atoi(v); err == nil && ms > 0 {
			cfg.TagService.TimeoutMs = ms
		}
	}

}

// applyRedisSceneEnv reads env vars with the given prefix and writes them into cfg.
// prefix example: "CONTENT_REDIS_REC" → reads CONTENT_REDIS_REC_MODE, _ADDR, etc.
func applyRedisSceneEnv(prefix string, cfg *redisSceneCfg) {
	if v := os.Getenv(prefix + "_MODE"); v != "" {
		cfg.Mode = v
	}
	if v := os.Getenv(prefix + "_ADDR"); v != "" {
		cfg.Addr = v
	}
	if v := os.Getenv(prefix + "_ADDRS"); v != "" {
		cfg.Addrs = strings.Split(v, ",")
	}
	if v := os.Getenv(prefix + "_PASSWORD"); v != "" {
		cfg.Password = v
	}
	if v := os.Getenv(prefix + "_TLS"); v == "true" || v == "1" {
		cfg.TLS = true
	}
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

func resolveMongoURI(cfg config) string {
	uri := strings.TrimSpace(cfg.Mongo.URI)
	if uri == "" || uri == "${MONGO_URI}" {
		return ""
	}
	return uri
}

func resolveReportDSN(cfg config) string {
	if v := strings.TrimSpace(os.Getenv("REPORT_DATABASE_URL")); v != "" {
		return v
	}
	dsn := strings.TrimSpace(cfg.Postgres.ReportDSN)
	if dsn == "" || dsn == "${REPORT_DATABASE_URL}" {
		return ""
	}
	return dsn
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
		ExperimentBucket: getenvOrDefault(
			"CONTENT_STORY_EXPERIMENT_BUCKET",
			"local_story_enabled",
		),
		CurrentStage: getenvOrDefault("CONTENT_STORY_CURRENT_STAGE", "100%"),
		CanaryMatrix: []postapp.StoryCanaryStage{
			{Stage: "5%", RolloutPercent: 5},
			{Stage: "20%", RolloutPercent: 20},
			{Stage: "50%", RolloutPercent: 50},
			{Stage: "100%", RolloutPercent: 100},
		},
	}
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
