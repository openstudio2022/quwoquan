package bootstrap

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/runtime/servicekit"
	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
	chatconfig "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/runtimeconfig"
)

// serviceName 是本模块在 composition.yaml、compose service name 与 specs 中
// 共用的同一字面值，也是 env 前缀 CHAT 的派生输入。
const serviceName = "chat-service"

const (
	minAccountSecurityAuthorityTimeout = 50 * time.Millisecond
	maxAccountSecurityAuthorityTimeout = 5 * time.Second
)

// config 是 chat-service 的声明式配置：通用段内嵌 servicekit.BaseConfig，
// 三个 Redis scene 的 env 键由服务前缀 CHAT 与 envPrefix 链派生，与部署面
// 注入点逐字对齐。MongoDB 与 reliable-task/sync 段沿用环境装配（secretRefs、
// compose、prod plane、gamma mirror）已固定的无前缀契约键，用 envAbsolute
// 逐字保留。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	MongoDB struct {
		URI      string `yaml:"uri" env:"MONGO_URI" required:"true"`
		Database string `yaml:"database" env:"MONGO_DATABASE" required:"true"`
	} `yaml:"mongodb"`

	// realtime 承载实时扇出与 resume，general 承载持久化事实流与缓存，
	// reliable_task 承载可靠任务 ready index。
	Redis struct {
		Realtime     servicekit.RedisSceneConfig `yaml:"realtime" envPrefix:"REDIS_REALTIME"`
		General      servicekit.RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
		ReliableTask servicekit.RedisSceneConfig `yaml:"reliable_task" envPrefix:"REDIS_RELIABLE_TASK"`
	} `yaml:"redis"`

	// Dependencies 是纯部署面契约：这些无前缀键由环境装配注入，不进入
	// 配置快照，因此不声明 yaml 路径——否则会凭空多出一份 schema 真相源。
	Dependencies struct {
		UserServiceBaseURL    string `yaml:"-" envAbsolute:"USER_SERVICE_BASE_URL"`
		CircleServiceBaseURL  string `yaml:"-" envAbsolute:"CIRCLE_SERVICE_BASE_URL"`
		GatewayBaseURL        string `yaml:"-" envAbsolute:"GATEWAY_BASE_URL"`
		ContentServiceBaseURL string `yaml:"-" envAbsolute:"CONTENT_SERVICE_BASE_URL"`
	} `yaml:"-"`

	Runtime struct {
		Media struct {
			GroupAvatarCDNBaseURL     string `yaml:"group_avatar_cdn_base_url" env:"GROUP_AVATAR_CDN_BASE_URL"`
			GroupAvatarLocalMediaRoot string `yaml:"group_avatar_local_media_root" env:"GROUP_AVATAR_LOCAL_MEDIA_ROOT"`
		} `yaml:"media"`
		Sync struct {
			PatchTTLHours int `yaml:"patch_ttl_hours" envAbsolute:"RUNTIME_SYNC_PATCH_TTL_HOURS"`
		} `yaml:"sync"`
		ReliableTask struct {
			ReadyIndex struct {
				Enabled bool   `yaml:"enabled" envAbsolute:"RELIABLE_TASK_READY_INDEX_ENABLED"`
				Stream  string `yaml:"stream" envAbsolute:"RELIABLE_TASK_READY_INDEX_STREAM"`
				Group   string `yaml:"group" envAbsolute:"RELIABLE_TASK_READY_INDEX_GROUP"`
				Queue   string `yaml:"queue" envAbsolute:"RELIABLE_TASK_READY_INDEX_QUEUE"`
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

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集
// 不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

// snapshotGuard 拒收仍带退役配置段的渲染快照：账号安全 authority 的配置面
// 已上收到通用段 user_account_security_authority，形状过时的快照会让通用段
// 全部落到零值，而零值超时会被后续边界校验当成一次「配置缺失」而不是「快照
// 形状过时」，掩盖真正的根因。
func snapshotGuard(raw []byte) error {
	var document struct {
		Runtime struct {
			Auth map[string]any `yaml:"auth"`
		} `yaml:"runtime"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		return fmt.Errorf("parse config snapshot for retired section validation: %w", err)
	}
	if document.Runtime.Auth != nil {
		return fmt.Errorf(
			"runtime.auth is retired; declare user_account_security_authority instead",
		)
	}
	return nil
}

// validateChatConfig 承接迁移前散落在 main.go 与 chatconfig 里的 fail-closed
// 校验：账号安全 authority 的 origin 与超时边界、三个跨服务依赖的 origin
// 形态。它在骨架 required 校验之后、任何观测栈与基础设施连接之前执行，
// 所以非法配置不产生外部副作用。
func validateChatConfig(cfg *config) error {
	authority := cfg.UserAccountSecurityAuthority
	if _, err := chatconfig.RequireInternalServiceBaseURL(
		"user_account_security_authority.base_url",
		authority.BaseURL,
	); err != nil {
		return fmt.Errorf("account security authority user-service URL: %w", err)
	}
	timeout := time.Duration(authority.TimeoutMs) * time.Millisecond
	if timeout < minAccountSecurityAuthorityTimeout ||
		timeout > maxAccountSecurityAuthorityTimeout {
		return fmt.Errorf(
			"account security authority timeout must be between %s and %s, got %dms",
			minAccountSecurityAuthorityTimeout,
			maxAccountSecurityAuthorityTimeout,
			authority.TimeoutMs,
		)
	}

	if _, err := cfg.resolveUserServiceBaseURL(); err != nil {
		return fmt.Errorf("user dependency invalid: %w", err)
	}
	if _, err := cfg.resolveCircleServiceBaseURL(); err != nil {
		return fmt.Errorf("circle dependency invalid: %w", err)
	}
	if _, err := cfg.resolveContentServiceBaseURL(); err != nil {
		return fmt.Errorf("content dependency invalid: %w", err)
	}
	return nil
}

func (cfg *config) resolveUserServiceBaseURL() (string, error) {
	return chatconfig.RequireInternalServiceBaseURL(
		"USER_SERVICE_BASE_URL", cfg.Dependencies.UserServiceBaseURL,
	)
}

// resolveCircleServiceBaseURL 保留 GATEWAY_BASE_URL 兜底：两个键都是既有的
// 部署面注入点，取决于该环境把圈子读路径挂在服务本体还是网关后面。
func (cfg *config) resolveCircleServiceBaseURL() (string, error) {
	value := strings.TrimSpace(cfg.Dependencies.CircleServiceBaseURL)
	if value == "" {
		value = strings.TrimSpace(cfg.Dependencies.GatewayBaseURL)
	}
	return chatconfig.RequireInternalServiceBaseURL(
		"CIRCLE_SERVICE_BASE_URL or GATEWAY_BASE_URL", value,
	)
}

func (cfg *config) resolveContentServiceBaseURL() (string, error) {
	return chatconfig.RequireInternalServiceBaseURL(
		"CONTENT_SERVICE_BASE_URL", cfg.Dependencies.ContentServiceBaseURL,
	)
}

// resolveRedisScenes 把三份 scene 配置装配成四个 codegen scene 名：rec 复用
// general；reliable_task 整段缺席时同样复用 general，让只接一套 Redis 的环境
// 不必重复声明第三份地址。复用的是完整一段，缺席判据由 servicekit 统一持有。
func resolveRedisScenes(cfg *config) map[string]servicekit.RedisSceneConfig {
	reliableTask := cfg.Redis.ReliableTask
	if reliableTask.IsUndeclared() {
		reliableTask = cfg.Redis.General
	}
	return map[string]servicekit.RedisSceneConfig{
		"realtime":     cfg.Redis.Realtime,
		"general":      cfg.Redis.General,
		"rec":          cfg.Redis.General,
		"reliabletask": reliableTask,
	}
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
	appError := generated.AppErrorFromMessageMediaInvalid(debugMessage)
	if status == http.StatusNotFound {
		appError = generated.AppErrorFromMessageMediaUnavailable(debugMessage)
	}
	rterr.WriteHTTPError(
		w,
		appError.WithLocation(rterr.RuntimeErrorLocation{
			BusinessObject: "chat_media",
			FunctionModule: "derived_media_file_server",
		}),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
