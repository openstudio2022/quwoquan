package main

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"

	platformredis "quwoquan_service/internal/platform/redis"
	configrelease "quwoquan_service/runtime/configrelease"
	rterr "quwoquan_service/runtime/errors"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
)

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "chat-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")

	if !isValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
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
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return config{}, err
	}
	if err := mergeConfigFile(&cfg, path); err != nil {
		return config{}, fmt.Errorf("read generated runtime config: %w", err)
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
			catalog: filepath.Join(configRoot, "quwoquan_service", "runtime", "reliabletask", "resources", "module_catalog.yaml"),
			policy:  filepath.Join(configRoot, "quwoquan_service", "runtime", "reliabletask", "resources", "retention_policy.yaml"),
		})
	}
	pairs = append(pairs, pair{
		catalog: "quwoquan_service/runtime/reliabletask/resources/module_catalog.yaml",
		policy:  "quwoquan_service/runtime/reliabletask/resources/retention_policy.yaml",
	})
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
	case "chat-service", "quwoquan_service", "":
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
	return platformredis.MustNewRouter(routerCfg)
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
		Mode:         mode,
		Addr:         r.Addr,
		Addrs:        r.Addrs,
		Password:     r.Password,
		DB:           r.DB,
		TLS:          r.TLS,
		PoolSize:     r.Pool.Size,
		MinIdleConns: r.Pool.MinIdle,
	}
}
