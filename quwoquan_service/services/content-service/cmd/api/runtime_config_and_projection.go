package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/services/content-service/internal/application/ports"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	embeddinginfra "quwoquan_service/services/content-service/internal/infrastructure/embedding"
	"quwoquan_service/services/content-service/internal/infrastructure/placeindex"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/infrastructure/searchindex"
)

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

	// External mounted config root mode:
	//   <root>/configs/<service>/default/config.yaml
	//   <root>/configs/<service>/<env>/config.yaml
	//   <root>/releases/config/<service>/<version>.yaml
	if strings.TrimSpace(configRoot) != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")

		if err := mergeConfigFile(&cfg, defaultFile); err != nil {
			return config{}, fmt.Errorf("read default config: %w", err)
		}
		if err := mergeConfigFile(&cfg, envFile); err != nil {
			return config{}, fmt.Errorf("read env config: %w", err)
		}
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join(configRoot, "releases", "config", serviceName, configVersion+".yaml")
			if err := mergeConfigFile(&cfg, versionFile); err != nil {
				return config{}, fmt.Errorf("read version config: %w", err)
			}
		}
		return cfg, nil
	}

	// Workspace local mode (service-relative):
	//   configs/default/config.yaml + configs/<env>/config.yaml (+ optional version under releases/)
	localDefault := filepath.Join("configs", "default", "config.yaml")
	localEnv := filepath.Join("configs", appEnv, "config.yaml")
	if err := mergeConfigFile(&cfg, localDefault); err != nil {
		return config{}, fmt.Errorf("read local default config: %w", err)
	}
	if err := mergeConfigFile(&cfg, localEnv); err != nil {
		return config{}, fmt.Errorf("read local env config: %w", err)
	}
	if strings.TrimSpace(configVersion) != "" {
		versionFile := filepath.Join("configs", "releases", configVersion+".yaml")
		if err := mergeConfigFile(&cfg, versionFile); err != nil {
			return config{}, fmt.Errorf("read local version config: %w", err)
		}
	}
	return cfg, nil
}

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	if strings.TrimSpace(imageVersion) == "" {
		// Allow local dev without image version.
		return nil
	}
	if cfg.Config.MinImageVersion != "" && compareSemver(imageVersion, cfg.Config.MinImageVersion) < 0 {
		return fmt.Errorf("IMAGE_VERSION=%s below min_image_version=%s", imageVersion, cfg.Config.MinImageVersion)
	}
	if cfg.Config.MaxImageVersion != "" && compareSemver(imageVersion, cfg.Config.MaxImageVersion) > 0 {
		return fmt.Errorf("IMAGE_VERSION=%s above max_image_version=%s", imageVersion, cfg.Config.MaxImageVersion)
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
	if appEnv != "alpha" && cfg.Embedding.Enabled {
		if _, err := resolveContentEmbeddingBinding(appEnv); err != nil {
			return fmt.Errorf("%s content runtime embedding binding: %w", appEnv, err)
		}
	}
	return nil
}

func resolveContentEmbeddingBinding(
	appEnv string,
) (embeddinginfra.OpenAICompatibleBinding, error) {
	return embeddinginfra.LoadOpenAICompatibleBinding(
		appEnv,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
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

func compareSemver(a, b string) int {
	parse := func(v string) [3]int {
		var out [3]int
		parts := strings.Split(strings.TrimPrefix(strings.TrimSpace(v), "v"), ".")
		for i := 0; i < len(parts) && i < 3; i++ {
			n, _ := strconv.Atoi(parts[i])
			out[i] = n
		}
		return out
	}
	av := parse(a)
	bv := parse(b)
	for i := 0; i < 3; i++ {
		if av[i] > bv[i] {
			return 1
		}
		if av[i] < bv[i] {
			return -1
		}
	}
	return 0
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
	if v := os.Getenv("REC_MODEL_SERVICE_ENABLED"); v == "true" || v == "1" {
		cfg.RecModelService.Enabled = true
	}
	if v := os.Getenv("REC_MODEL_SERVICE_TIMEOUT_MS"); v != "" {
		if ms, err := strconv.Atoi(v); err == nil && ms > 0 {
			cfg.RecModelService.TimeoutMs = ms
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
	discovery *recinfra.DiscoveryFeedProjector
	recommend *recinfra.RecommendFeatureProjector
	premium   *recinfra.PremiumPoolProjector
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
	if a.discovery != nil {
		if err := a.discovery.Project(ctx, projectorEvent); err != nil {
			return err
		}
	}
	if a.recommend != nil {
		if err := a.recommend.Project(ctx, projectorEvent); err != nil {
			return err
		}
	}
	if a.premium != nil {
		if err := a.premium.Project(ctx, projectorEvent); err != nil {
			return err
		}
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

func premiumPoolSourceRollbackDisabled() bool {
	return parseBoolEnv("QWQ_DISABLE_PREMIUM_POOL_SOURCE", false) ||
		parseBoolEnv("DISABLE_PREMIUM_POOL_SOURCE", false) ||
		parseBoolEnv("disable_premium_pool_source", false)
}

// dailyAffinityDecayCheckInterval is the replica check cadence; the per-day Redis lock makes the
// actual decay run at most once per UTC day across all replicas.
const dailyAffinityDecayCheckInterval = time.Hour
