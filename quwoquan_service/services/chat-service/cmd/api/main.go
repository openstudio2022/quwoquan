package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"gopkg.in/yaml.v3"

	rterr "quwoquan_service/runtime/errors"
	rthttp "quwoquan_service/runtime/http"
	runtimemedia "quwoquan_service/runtime/media"
	robs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	runtimesync "quwoquan_service/runtime/sync"
	httpadapter "quwoquan_service/services/chat-service/internal/adapters/http"
	"quwoquan_service/services/chat-service/internal/adapters/mq"
	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
}

type config struct {
	Config struct {
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`

	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`

	Redis struct {
		Realtime     redisSceneCfg `yaml:"realtime"`
		General      redisSceneCfg `yaml:"general"`
		ReliableTask redisSceneCfg `yaml:"reliable_task"`
	} `yaml:"redis"`

	Runtime struct {
		Media struct {
			GroupAvatarCDNBaseURL     string `yaml:"group_avatar_cdn_base_url"`
			GroupAvatarLocalMediaRoot string `yaml:"group_avatar_local_media_root"`
		} `yaml:"media"`
		Sync struct {
			PatchTTLHours int `yaml:"patch_ttl_hours"`
		} `yaml:"sync"`
		ReliableTask struct {
			ReadyIndex struct {
				Enabled bool   `yaml:"enabled"`
				Stream  string `yaml:"stream"`
				Group   string `yaml:"group"`
				Queue   string `yaml:"queue"`
			} `yaml:"ready_index"`
		} `yaml:"reliable_task"`
		Observability struct {
			RuntimeMedia struct {
				GroupAvatarRecomputeDurationMsP95 float64 `yaml:"group_avatar_recompute_duration_ms_p95"`
				GroupAvatarFallbackRatio          float64 `yaml:"group_avatar_fallback_ratio"`
				HintToPullDelayMsP95              float64 `yaml:"hint_to_pull_delay_ms_p95"`
				PatchFanoutFailureRatio           float64 `yaml:"patch_fanout_failure_ratio"`
			} `yaml:"runtime_media"`
		} `yaml:"observability"`
	} `yaml:"runtime"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("chat-service runtime identity invalid: %v", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("chat-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("chat-service config compatibility failed: %v", err)
	}

	addr := getenvOrDefault("CHAT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18081"
	}

	logger := slog.Default()
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())
	userServiceBaseURL := strings.TrimSpace(os.Getenv("USER_SERVICE_BASE_URL"))

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, "info", nil)
	if err != nil {
		log.Fatalf("chat-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("chat-service exception logger init failed: %v", err)
	}

	router := buildRedisRouter(cfg)
	defer router.Close()

	ctx := context.Background()
	mongoClient, err := mongo.Connect(options.Client().ApplyURI(cfg.MongoDB.URI))
	if err != nil {
		log.Fatalf("chat-service mongo connect failed: %v", err)
	}
	defer func() { _ = mongoClient.Disconnect(ctx) }()

	mongoDB := mongoClient.Database(cfg.MongoDB.Database)
	chatStore := persistence.NewMongoChatStore(mongoDB)
	convCache := chatcache.NewConversationCache(router.Scene("general"))
	eventPublisher := mq.NewEventPublisher(router.Scene("realtime"))
	localMediaRoot := strings.TrimSpace(cfg.Runtime.Media.GroupAvatarLocalMediaRoot)
	if localMediaRoot == "" {
		localMediaRoot = "./var/chat-media"
	}
	application.ConfigureGroupAvatarCDNBase(cfg.Runtime.Media.GroupAvatarCDNBaseURL)
	if err := runtimemedia.EnsureDefaultGroupAvatarFile(localMediaRoot); err != nil {
		log.Fatalf("chat-service default group avatar init failed: %v", err)
	}
	groupAvatarMedia := runtimemedia.NewGroupAvatarService(
		router.Scene("general"),
		cfg.Runtime.Media.GroupAvatarCDNBaseURL,
		localMediaRoot,
	)
	syncOptions := []runtimesync.Option{}
	if cfg.Runtime.Sync.PatchTTLHours > 0 {
		syncOptions = append(
			syncOptions,
			runtimesync.WithPatchTTL(time.Duration(cfg.Runtime.Sync.PatchTTLHours)*time.Hour),
		)
	}
	userSyncService := runtimesync.NewService(
		router.Scene("general"),
		router.Scene("realtime"),
		syncOptions...,
	)
	reliableTaskCatalog, err := loadReliableTaskCatalog(configRoot)
	if err != nil {
		log.Fatalf("chat-service reliable task catalog load failed: %v", err)
	}
	reliableTaskStore := reliabletask.NewMongoStore(mongoDB)
	if err := reliableTaskStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("chat-service reliable task index init failed: %v", err)
	}
	var reliableTaskReadyIndex reliabletask.ReadyIndex
	if cfg.Runtime.ReliableTask.ReadyIndex.Enabled {
		index, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
			Client: router.Scene("reliabletask"),
			Stream: cfg.Runtime.ReliableTask.ReadyIndex.Stream,
			Group:  cfg.Runtime.ReliableTask.ReadyIndex.Group,
			Queue:  cfg.Runtime.ReliableTask.ReadyIndex.Queue,
		})
		if err != nil {
			log.Fatalf("chat-service reliable task redis ready index init failed: %v", err)
		}
		if err := index.Ensure(ctx); err != nil {
			log.Fatalf("chat-service reliable task redis ready index ensure failed: %v", err)
		}
		reliableTaskReadyIndex = index
	}
	groupAvatarScheduler := application.NewReliableGroupAvatarTaskScheduler(
		reliableTaskStore,
		reliableTaskCatalog,
		chatStore,
		eventPublisher,
		groupAvatarMedia,
		userSyncService,
		logger,
		application.WithReliableGroupAvatarRuntimeIdentity(appEnv, instanceID),
		application.WithReliableGroupAvatarEnabledModules(resolveReliableTaskModules()),
		application.WithReliableGroupAvatarReadyIndex(reliableTaskReadyIndex),
	)
	if err := groupAvatarScheduler.Start(ctx); err != nil {
		log.Fatalf("chat-service reliable group avatar scheduler start failed: %v", err)
	}
	go func() {
		if err := application.BackfillMissingGroupAvatars(
			context.Background(),
			chatStore,
			eventPublisher,
			groupAvatarMedia,
			userSyncService,
			groupAvatarScheduler,
			200,
		); err != nil {
			logger.Error("chat-service group avatar backfill failed", "err", err)
		}
	}()
	profileResolver := httpadapter.NewUserProfileResolver(userServiceBaseURL, nil)

	conversationSvc := application.NewConversationService(
		chatStore,
		convCache,
		eventPublisher,
		profileResolver,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
	)
	messageSvc := application.NewMessageService(chatStore, convCache, eventPublisher)
	memberSvc := application.NewMemberService(
		chatStore,
		convCache,
		eventPublisher,
		profileResolver,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
	)
	inboxSvc := application.NewInboxService(chatStore)
	userAvatarConsumer := mq.NewUserAvatarUpdateConsumer(
		router.Scene("general"),
		chatStore,
		eventPublisher,
		groupAvatarMedia,
		userSyncService,
		groupAvatarScheduler,
		logger,
	)
	if err := userAvatarConsumer.Start(ctx); err != nil {
		log.Fatalf("chat-service user avatar consumer start failed: %v", err)
	}
	if userServiceBaseURL == "" {
		logger.Warn("chat-service user profile resolver base URL is empty; create/add member snapshot hydration will be skipped")
	}

	baseHandler := httpadapter.NewChatHandler(conversationSvc, messageSvc, memberSvc, inboxSvc).Routes()
	rootMux := http.NewServeMux()
	rootMux.Handle("/media/", newDerivedMediaFileServer(localMediaRoot))
	rootMux.Handle("/metrics/runtime-media", application.NewRuntimeMediaMetricsHandler(
		groupAvatarScheduler,
		userSyncService,
		application.RuntimeMediaAlertThresholds{
			GroupAvatarRecomputeDurationMsP95: cfg.Runtime.Observability.RuntimeMedia.GroupAvatarRecomputeDurationMsP95,
			GroupAvatarFallbackRatio:          cfg.Runtime.Observability.RuntimeMedia.GroupAvatarFallbackRatio,
			HintToPullDelayMsP95:              cfg.Runtime.Observability.RuntimeMedia.HintToPullDelayMsP95,
			PatchFanoutFailureRatio:           cfg.Runtime.Observability.RuntimeMedia.PatchFanoutFailureRatio,
		},
	))
	rootMux.Handle("/", baseHandler)
	observedHandler := rthttp.NewHTTPServerMiddleware(rootMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "chat-service",
		ServiceName:       "chat-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "chat-service",
		Src:               "chat-service",
	}, ioLogger, processLogger, exceptionLogger)

	server := &http.Server{
		Addr:              addr,
		Handler:           observedHandler,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	logger.Info("chat-service starting", "addr", addr, "env", appEnv)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("chat-service listen failed: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "chat-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")

	if !isValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod-gray|prod, got %q", appEnv)
	}
	if requiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod-gray", "prod":
		return true
	default:
		return false
	}
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod-gray", "prod":
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

func hostname() string {
	h, err := os.Hostname()
	if err != nil {
		return "unknown"
	}
	return h
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

	localDefault := filepath.Join("configs", "default", "config.yaml")
	localEnv := filepath.Join("configs", appEnv, "config.yaml")
	if _, err := os.Stat(localDefault); err == nil {
		if err := mergeConfigFile(&cfg, localDefault); err != nil {
			return config{}, fmt.Errorf("read local default config: %w", err)
		}
		if err := mergeConfigFile(&cfg, localEnv); err != nil {
			return config{}, fmt.Errorf("read local env config: %w", err)
		}
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join("..", "..", "..", "releases", "config", serviceName, configVersion+".yaml")
			if _, err := os.Stat(versionFile); err == nil {
				if err := mergeConfigFile(&cfg, versionFile); err != nil {
					return config{}, fmt.Errorf("read local version config: %w", err)
				}
			}
		}
		return cfg, nil
	}

	currentPath := filepath.Join("configs", "config.yaml")
	if _, err := os.Stat(currentPath); err == nil {
		if err := mergeConfigFile(&cfg, currentPath); err != nil {
			return config{}, fmt.Errorf("read current config: %w", err)
		}
	}
	return cfg, nil
}

func loadReliableTaskCatalog(configRoot string) (reliabletask.Catalog, error) {
	type pair struct {
		catalog string
		policy  string
	}
	pairs := []pair{}
	if path := strings.TrimSpace(os.Getenv("RELIABLE_TASK_CATALOG_PATH")); path != "" {
		policyPath := strings.TrimSpace(os.Getenv("RELIABLE_TASK_RETENTION_POLICY_PATH"))
		pairs = append(pairs, pair{catalog: path, policy: policyPath})
	}
	if strings.TrimSpace(configRoot) != "" {
		pairs = append(pairs, pair{
			catalog: filepath.Join(configRoot, "deploy", "shared", "reliable_task_module_catalog.yaml"),
			policy:  filepath.Join(configRoot, "deploy", "shared", "reliable_task_retention_policy.yaml"),
		})
	}
	pairs = append(pairs,
		pair{catalog: "deploy/shared/reliable_task_module_catalog.yaml", policy: "deploy/shared/reliable_task_retention_policy.yaml"},
		pair{catalog: "../deploy/shared/reliable_task_module_catalog.yaml", policy: "../deploy/shared/reliable_task_retention_policy.yaml"},
	)
	var lastErr error
	for _, candidate := range pairs {
		var catalog reliabletask.Catalog
		var err error
		if candidate.policy != "" {
			catalog, err = reliabletask.LoadCatalogWithPolicies(candidate.catalog, candidate.policy)
		} else {
			catalog, err = reliabletask.LoadCatalog(candidate.catalog)
		}
		if err == nil {
			return catalog, nil
		}
		lastErr = err
	}
	return reliabletask.Catalog{}, lastErr
}

func resolveReliableTaskModules() []string {
	if raw := strings.TrimSpace(os.Getenv("RELIABLE_TASK_MODULES")); raw != "" {
		return splitCSV(raw)
	}
	switch strings.TrimSpace(os.Getenv("MODULE_PACKAGE")) {
	case "chat-avatar-worker-package":
		return []string{"chat.group_avatar_worker"}
	case "chat-background-package":
		return []string{"chat.task_outbox_dispatcher", "chat.notification_outbox_dispatcher", "notification.fanout_worker"}
	case "seed-box", "chat-service", "quwoquan_service", "":
		return []string{
			"chat.task_outbox_dispatcher",
			"chat.group_avatar_worker",
			"chat.notification_outbox_dispatcher",
			"notification.fanout_worker",
		}
	default:
		return []string{
			"chat.task_outbox_dispatcher",
			"chat.group_avatar_worker",
			"chat.notification_outbox_dispatcher",
			"notification.fanout_worker",
		}
	}
}

func splitCSV(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	if strings.TrimSpace(imageVersion) == "" {
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

func newDerivedMediaFileServer(localRoot string) http.Handler {
	root := filepath.Clean(strings.TrimSpace(localRoot))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			writeDerivedMediaError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		rel := strings.TrimPrefix(r.URL.Path, "/media/")
		rel = strings.Trim(rel, "/")
		if rel == "" || strings.Contains(rel, "..") {
			writeDerivedMediaError(w, r, http.StatusBadRequest, "bad path")
			return
		}
		full := filepath.Join(root, filepath.FromSlash(rel))
		cleanRoot := root
		cleanFull := filepath.Clean(full)
		sep := string(filepath.Separator)
		if cleanFull != cleanRoot && !strings.HasPrefix(cleanFull, cleanRoot+sep) {
			writeDerivedMediaError(w, r, http.StatusBadRequest, "bad path")
			return
		}
		fi, err := os.Stat(cleanFull)
		if err != nil || fi.IsDir() {
			writeDerivedMediaError(w, r, http.StatusNotFound, "media not found")
			return
		}
		http.ServeFile(w, r, cleanFull)
	})
}

func writeDerivedMediaError(w http.ResponseWriter, r *http.Request, status int, debugMessage string) {
	kind := rterr.KindUser
	reason := "invalid_argument"
	userMessage := "媒体资源不可用"
	if status == http.StatusNotFound {
		reason = "not_found"
	}
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, kind, reason),
			userMessage,
			debugMessage,
		).WithLocation(rterr.RuntimeErrorLocation{
			BusinessObject: "chat_media",
			FunctionModule: "derived_media_file_server",
		}),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("MONGO_URI"); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := os.Getenv("MONGO_DATABASE"); v != "" {
		cfg.MongoDB.Database = v
	}

	applyRedisSceneEnv("CHAT_REDIS_REALTIME", &cfg.Redis.Realtime)
	applyRedisSceneEnv("CHAT_REDIS_GENERAL", &cfg.Redis.General)
	applyRedisSceneEnv("CHAT_REDIS_RELIABLE_TASK", &cfg.Redis.ReliableTask)

	if v := os.Getenv("REDIS_ADDR"); v != "" {
		if cfg.Redis.General.Addr == "" {
			cfg.Redis.General.Addr = v
		}
		if cfg.Redis.Realtime.Addr == "" {
			cfg.Redis.Realtime.Addr = v
		}
		if cfg.Redis.ReliableTask.Addr == "" {
			cfg.Redis.ReliableTask.Addr = v
		}
	}
	if v := os.Getenv("RELIABLE_TASK_READY_INDEX_ENABLED"); v == "true" || v == "1" {
		cfg.Runtime.ReliableTask.ReadyIndex.Enabled = true
	}
	if v := os.Getenv("RELIABLE_TASK_READY_INDEX_STREAM"); v != "" {
		cfg.Runtime.ReliableTask.ReadyIndex.Stream = v
	}
	if v := os.Getenv("RELIABLE_TASK_READY_INDEX_GROUP"); v != "" {
		cfg.Runtime.ReliableTask.ReadyIndex.Group = v
	}
	if v := os.Getenv("RELIABLE_TASK_READY_INDEX_QUEUE"); v != "" {
		cfg.Runtime.ReliableTask.ReadyIndex.Queue = v
	}
	if v := os.Getenv("CHAT_GROUP_AVATAR_CDN_BASE_URL"); v != "" {
		cfg.Runtime.Media.GroupAvatarCDNBaseURL = v
	}
	if v := os.Getenv("CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT"); v != "" {
		cfg.Runtime.Media.GroupAvatarLocalMediaRoot = v
	}
	if v := os.Getenv("RUNTIME_SYNC_PATCH_TTL_HOURS"); v != "" {
		if hours, err := strconv.Atoi(v); err == nil {
			cfg.Runtime.Sync.PatchTTLHours = hours
		}
	}
}

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

func buildRedisRouter(cfg config) *rtredis.Router {
	routerCfg := rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"realtime":     toSceneConfig(cfg.Redis.Realtime),
			"general":      toSceneConfig(cfg.Redis.General),
			"rec":          toSceneConfig(cfg.Redis.General),
			"reliabletask": toSceneConfig(resolveReliableTaskRedisScene(cfg)),
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "general",
	}
	return rtredis.MustNewRouter(routerCfg)
}

func resolveReliableTaskRedisScene(cfg config) redisSceneCfg {
	scene := cfg.Redis.ReliableTask
	if strings.TrimSpace(scene.Mode) == "" &&
		strings.TrimSpace(scene.Addr) == "" &&
		len(scene.Addrs) == 0 {
		return cfg.Redis.General
	}
	return scene
}

func toSceneConfig(r redisSceneCfg) rtredis.SceneConfig {
	mode := strings.ToLower(strings.TrimSpace(r.Mode))
	if mode == "" {
		mode = "standalone"
	}
	if mode == "standalone" && r.Addr == "" {
		mode = "memory"
	}
	if mode == "cluster" && len(r.Addrs) == 0 {
		mode = "memory"
	}
	return rtredis.SceneConfig{
		Mode:     mode,
		Addr:     r.Addr,
		Addrs:    r.Addrs,
		Password: r.Password,
		DB:       r.DB,
		TLS:      r.TLS,
	}
}
