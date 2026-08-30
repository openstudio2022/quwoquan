package bootstrap

import (
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/runtime/servicekit"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/domain"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/infrastructure/redisstore"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutdomain "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	graphread "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/adapters/inbound/http"
)

var sha256ReferencePattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type policyConfig struct {
	Limit         int    `yaml:"limit"`
	WindowSeconds int    `yaml:"window_seconds"`
	StateFailure  string `yaml:"state_failure"`
}

func (config policyConfig) policy() domain.Policy {
	return domain.Policy{
		Limit:        int64(config.Limit),
		Window:       time.Duration(config.WindowSeconds) * time.Second,
		StateFailure: domain.FailurePolicy(strings.TrimSpace(config.StateFailure)),
	}
}

// runtimeConfig 是 api-edge 的声明式配置：通用段内嵌 servicekit.BaseConfig
// （HTTP 监听地址、配置快照版本、账号安全 authority），env 覆盖键由服务名
// 派生前缀 API_EDGE 拼出（DEC-028）。
//
// Redis 刻意不声明 servicekit.RedisSceneConfig：admission 与 rollout 必须
// 共用同一个 UniversalClient——那是 prod rollout 的 stable/gray 共享同一个
// 原子准入桶的前提，而 scene 自动装配会给出两个独立 client，且地址缺失时
// 回落到内存实现（对全站唯一对外入口是 fail-open）。客户端在 Assemble 里
// 由 admissionredis.NewClient 构造，见 newModule。
type runtimeConfig struct {
	servicekit.BaseConfig `yaml:",inline"`

	Edge struct {
		TrustedNetworkHeader string `yaml:"trusted_network_header"`
	} `yaml:"edge"`
	Redis struct {
		Admission struct {
			Mode  string   `yaml:"mode"`
			Addr  string   `yaml:"addr"`
			Addrs []string `yaml:"addrs"`
			// Password 的键名与 environments/prod/config.yaml 的 secretRef
			// `sys.api-edge.redis.admission.password: API_EDGE_REDIS_PASSWORD`
			// 同源：快照只留引用，值由部署面按该键注入。
			Password       string `yaml:"password" env:"REDIS_PASSWORD"`
			TLS            bool   `yaml:"tls"`
			PoolSize       int    `yaml:"pool_size"`
			DialTimeoutMS  int    `yaml:"dial_timeout_ms"`
			ReadTimeoutMS  int    `yaml:"read_timeout_ms"`
			WriteTimeoutMS int    `yaml:"write_timeout_ms"`
		} `yaml:"admission"`
	} `yaml:"redis"`
	RateLimit struct {
		Command   policyConfig `yaml:"command"`
		Query     policyConfig `yaml:"query"`
		Session   policyConfig `yaml:"session"`
		Operation struct {
			ContentPostGetFeed policyConfig `yaml:"content_post_get_feed"`
			// 匿名恢复异常上报的权威来源准入（OPEN-008 上收）：
			// 匿名操作的 admission subject 是可信连接层 IP（network kind）。
			OpsRecoveryFailureReport policyConfig `yaml:"ops_recovery_failure_report"`
		} `yaml:"operation"`
	} `yaml:"rate_limit"`
	MinimumBuild struct {
		Mode         string   `yaml:"mode"`
		SourceDigest string   `yaml:"source_digest"`
		Android      uint64   `yaml:"android"`
		IOS          uint64   `yaml:"ios"`
		Web          uint64   `yaml:"web"`
		ExemptPaths  []string `yaml:"exempt_paths"`
	} `yaml:"minimum_build"`
	Rollout struct {
		Enabled      bool   `yaml:"enabled"`
		PolicyFile   string `yaml:"policy_file"`
		PolicySHA256 string `yaml:"policy_sha256"`
		// AllocationKey 的键名与 environments/prod/config.yaml 的 secretRef
		// `sys.api-edge.rollout.allocation_key: API_EDGE_ROLLOUT_ALLOCATION_KEY`
		// 同源。长度判据仍归 rolloutapp.AllocationKey，见 newModule。
		AllocationKey           string                                   `yaml:"allocation_key" env:"ROLLOUT_ALLOCATION_KEY"`
		NetworkAttributeCatalog rolloutapp.NetworkAttributeCatalogConfig `yaml:"network_attribute_catalog"`
		Policy                  rolloutdomain.Policy                     `yaml:"-"`
	} `yaml:"rollout"`
	GraphQLRead        graphread.Config  `yaml:"graphql_read"`
	Upstreams          map[string]string `yaml:"upstreams"`
	CandidateUpstreams map[string]string `yaml:"candidate_upstreams"`
}

// validateEdgeConfig 是骨架的领域配置校验钩子：它在 env 覆盖与 required
// 校验之后、观测栈与任何基础设施连接之前执行，因此非法配置不会产生外部副
// 作用。快照路径与 canonical 环境由骨架写入 BaseConfig，不在此重算选路。
//
// 迁移前 loadRuntimeConfig 的每一条判据都原样落在这里，顺序不变。
func validateEdgeConfig(config *runtimeConfig) error {
	if config == nil {
		return errors.New("runtime config is required")
	}
	path := strings.TrimSpace(config.ConfigPath)
	if path == "" {
		return errors.New("effective config snapshot path is required")
	}
	environment := strings.TrimSpace(config.Environment)
	config.Edge.TrustedNetworkHeader = strings.TrimSpace(config.Edge.TrustedNetworkHeader)
	config.Redis.Admission.Mode = strings.TrimSpace(config.Redis.Admission.Mode)
	config.Redis.Admission.Addr = strings.TrimSpace(config.Redis.Admission.Addr)
	config.MinimumBuild.Mode = strings.TrimSpace(config.MinimumBuild.Mode)
	config.MinimumBuild.SourceDigest = strings.ToLower(strings.TrimSpace(
		config.MinimumBuild.SourceDigest,
	))
	config.Rollout.PolicyFile = strings.TrimSpace(config.Rollout.PolicyFile)
	config.Rollout.PolicySHA256 = strings.ToLower(strings.TrimSpace(
		config.Rollout.PolicySHA256,
	))
	config.UserAccountSecurityAuthority.BaseURL = strings.TrimSpace(
		config.UserAccountSecurityAuthority.BaseURL,
	)
	// Service.HTTP.Addr 的非空由 BaseConfig 的 required tag 承担，此处只保留
	// api-edge 自己的 trusted network header 判据。
	if config.Edge.TrustedNetworkHeader == "" {
		return errors.New("trusted network header is required")
	}
	if config.UserAccountSecurityAuthority.TimeoutMs < 50 ||
		config.UserAccountSecurityAuthority.TimeoutMs > 5000 {
		return errors.New("account security timeout must be within 50..5000ms")
	}
	if _, err := parseOrigin(config.UserAccountSecurityAuthority.BaseURL); err != nil {
		return fmt.Errorf("account security authority: %w", err)
	}
	minimumBuildPolicy := config.minimumBuildPolicy()
	if err := minimumBuildPolicy.Validate(); err != nil {
		return fmt.Errorf("minimum build policy: %w", err)
	}
	if !sha256ReferencePattern.MatchString(config.MinimumBuild.SourceDigest) {
		return errors.New("minimum build source digest is invalid")
	}
	exemptPaths, err := config.minimumBuildExemptPaths()
	if err != nil {
		return err
	}
	if _, exists := exemptPaths["/ops/app-recovery/version"]; !exists {
		return errors.New(
			"minimum build exemptions must include /ops/app-recovery/version",
		)
	}
	policies := config.policySet()
	if err := policies.Validate(); err != nil {
		return err
	}
	for _, name := range requiredUpstreams() {
		origin := strings.TrimSpace(config.Upstreams[name])
		if _, err := parseOrigin(origin); err != nil {
			return fmt.Errorf("upstream %s: %w", name, err)
		}
		config.Upstreams[name] = origin
	}
	if err := validateAndLoadRolloutConfig(config, environment, path); err != nil {
		return err
	}
	if err := graphread.ValidateAndResolveConfig(
		&config.GraphQLRead,
		path,
		config.Rollout.Enabled,
		config.Rollout.Policy.CandidateDigest,
	); err != nil {
		return err
	}
	client, err := redisstore.NewClient(config.redisConfig())
	if err != nil {
		return fmt.Errorf("admission Redis config: %w", err)
	}
	_ = client.Close()
	return nil
}

func validateAndLoadRolloutConfig(
	config *runtimeConfig,
	environment string,
	runtimeConfigPath string,
) error {
	if config == nil {
		return errors.New("runtime config is required")
	}
	rolloutConfig := rolloutapp.RuntimeConfig{
		Enabled:                 config.Rollout.Enabled,
		PolicyFile:              config.Rollout.PolicyFile,
		PolicySHA256:            config.Rollout.PolicySHA256,
		Policy:                  config.Rollout.Policy,
		CandidateUpstreams:      config.CandidateUpstreams,
		NetworkAttributeCatalog: config.Rollout.NetworkAttributeCatalog,
	}
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&rolloutConfig,
		environment,
		runtimeConfigPath,
		requiredUpstreams(),
	); err != nil {
		return err
	}
	config.Rollout.PolicyFile = rolloutConfig.PolicyFile
	config.Rollout.PolicySHA256 = rolloutConfig.PolicySHA256
	config.Rollout.Policy = rolloutConfig.Policy
	config.Rollout.NetworkAttributeCatalog = rolloutConfig.NetworkAttributeCatalog
	config.CandidateUpstreams = rolloutConfig.CandidateUpstreams
	return nil
}

func (config runtimeConfig) minimumBuildPolicy() rolloutapp.MinimumBuildPolicy {
	return rolloutapp.MinimumBuildPolicy{
		SourceDigest: config.MinimumBuild.SourceDigest,
		Mode:         config.MinimumBuild.Mode,
		Platforms: map[string]uint64{
			"android": config.MinimumBuild.Android,
			"ios":     config.MinimumBuild.IOS,
			"web":     config.MinimumBuild.Web,
		},
	}
}

func (config runtimeConfig) minimumBuildExemptPaths() (map[string]struct{}, error) {
	result := make(map[string]struct{}, len(config.MinimumBuild.ExemptPaths))
	for _, rawPath := range config.MinimumBuild.ExemptPaths {
		path := strings.TrimSpace(rawPath)
		if path == "" || !strings.HasPrefix(path, "/") {
			return nil, errors.New("minimum build exemption must be an absolute HTTP path")
		}
		if _, exists := result[path]; exists {
			return nil, fmt.Errorf("duplicate minimum build exemption %s", strconv.Quote(path))
		}
		result[path] = struct{}{}
	}
	return result, nil
}

func (config runtimeConfig) policySet() application.PolicySet {
	return application.PolicySet{
		ByOperationKind: map[string]domain.Policy{
			"command": config.RateLimit.Command.policy(),
			"query":   config.RateLimit.Query.policy(),
			"session": config.RateLimit.Session.policy(),
		},
		ByOperationID: map[string]domain.Policy{
			"content.post.GetFeed":                       config.RateLimit.Operation.ContentPostGetFeed.policy(),
			"ops.recovery_failure.ReportRecoveryFailure": config.RateLimit.Operation.OpsRecoveryFailureReport.policy(),
		},
	}
}

func (config runtimeConfig) redisConfig() redisstore.Config {
	return redisstore.Config{
		Mode:         config.Redis.Admission.Mode,
		Addr:         config.Redis.Admission.Addr,
		Addrs:        append([]string(nil), config.Redis.Admission.Addrs...),
		Password:     strings.TrimSpace(config.Redis.Admission.Password),
		TLS:          config.Redis.Admission.TLS,
		PoolSize:     config.Redis.Admission.PoolSize,
		DialTimeout:  time.Duration(config.Redis.Admission.DialTimeoutMS) * time.Millisecond,
		ReadTimeout:  time.Duration(config.Redis.Admission.ReadTimeoutMS) * time.Millisecond,
		WriteTimeout: time.Duration(config.Redis.Admission.WriteTimeoutMS) * time.Millisecond,
	}
}

func requiredUpstreams() []string {
	return application.RequiredUpstreams()
}

func parseOrigin(raw string) (*url.URL, error) {
	origin, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || origin.Scheme == "" || origin.Host == "" || origin.User != nil ||
		origin.RawQuery != "" || origin.Fragment != "" ||
		(origin.Path != "" && origin.Path != "/") {
		return nil, fmt.Errorf("absolute origin URL is required")
	}
	if origin.Scheme != "http" && origin.Scheme != "https" {
		return nil, fmt.Errorf("origin scheme must be http or https")
	}
	return origin, nil
}
