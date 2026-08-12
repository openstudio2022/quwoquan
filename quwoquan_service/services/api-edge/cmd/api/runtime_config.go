package main

import (
	"errors"
	"fmt"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	configrelease "quwoquan_service/runtime/configrelease"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/domain"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/infrastructure/redisstore"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutdomain "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	graphread "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/adapters/inbound/http"

	"gopkg.in/yaml.v3"
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

type runtimeConfig struct {
	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	Edge struct {
		TrustedNetworkHeader string `yaml:"trusted_network_header"`
	} `yaml:"edge"`
	Redis struct {
		Admission struct {
			Mode           string   `yaml:"mode"`
			Addr           string   `yaml:"addr"`
			Addrs          []string `yaml:"addrs"`
			TLS            bool     `yaml:"tls"`
			PoolSize       int      `yaml:"pool_size"`
			DialTimeoutMS  int      `yaml:"dial_timeout_ms"`
			ReadTimeoutMS  int      `yaml:"read_timeout_ms"`
			WriteTimeoutMS int      `yaml:"write_timeout_ms"`
		} `yaml:"admission"`
	} `yaml:"redis"`
	RateLimit struct {
		Command   policyConfig `yaml:"command"`
		Query     policyConfig `yaml:"query"`
		Session   policyConfig `yaml:"session"`
		Operation struct {
			ContentPostGetFeed policyConfig `yaml:"content_post_get_feed"`
		} `yaml:"operation"`
	} `yaml:"rate_limit"`
	UserService struct {
		AccountSecurity struct {
			BaseURL   string `yaml:"base_url"`
			TimeoutMS int    `yaml:"timeout_ms"`
		} `yaml:"account_security"`
	} `yaml:"user_service"`
	MinimumBuild struct {
		Mode         string   `yaml:"mode"`
		SourceDigest string   `yaml:"source_digest"`
		Android      uint64   `yaml:"android"`
		IOS          uint64   `yaml:"ios"`
		Web          uint64   `yaml:"web"`
		ExemptPaths  []string `yaml:"exempt_paths"`
	} `yaml:"minimum_build"`
	Rollout struct {
		Enabled                 bool                                     `yaml:"enabled"`
		PolicyFile              string                                   `yaml:"policy_file"`
		PolicySHA256            string                                   `yaml:"policy_sha256"`
		NetworkAttributeCatalog rolloutapp.NetworkAttributeCatalogConfig `yaml:"network_attribute_catalog"`
		Policy                  rolloutdomain.Policy                     `yaml:"-"`
	} `yaml:"rollout"`
	GraphQLRead        graphread.Config  `yaml:"graphql_read"`
	Upstreams          map[string]string `yaml:"upstreams"`
	CandidateUpstreams map[string]string `yaml:"candidate_upstreams"`
}

func loadRuntimeConfig(serviceName, environment, configRoot string) (runtimeConfig, error) {
	path, err := configrelease.File(configRoot, serviceName, environment)
	if err != nil {
		return runtimeConfig{}, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return runtimeConfig{}, err
	}
	var config runtimeConfig
	if err := yaml.Unmarshal(raw, &config); err != nil {
		return runtimeConfig{}, fmt.Errorf("parse %s: %w", path, err)
	}
	config.Service.HTTP.Addr = strings.TrimSpace(config.Service.HTTP.Addr)
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
	config.UserService.AccountSecurity.BaseURL = strings.TrimSpace(
		config.UserService.AccountSecurity.BaseURL,
	)
	if config.Service.HTTP.Addr == "" || config.Edge.TrustedNetworkHeader == "" {
		return runtimeConfig{}, errors.New("service HTTP address and trusted network header are required")
	}
	if config.UserService.AccountSecurity.TimeoutMS < 50 ||
		config.UserService.AccountSecurity.TimeoutMS > 5000 {
		return runtimeConfig{}, errors.New("account security timeout must be within 50..5000ms")
	}
	if _, err := parseOrigin(config.UserService.AccountSecurity.BaseURL); err != nil {
		return runtimeConfig{}, fmt.Errorf("account security authority: %w", err)
	}
	minimumBuildPolicy := config.minimumBuildPolicy()
	if err := minimumBuildPolicy.Validate(); err != nil {
		return runtimeConfig{}, fmt.Errorf("minimum build policy: %w", err)
	}
	if !sha256ReferencePattern.MatchString(config.MinimumBuild.SourceDigest) {
		return runtimeConfig{}, errors.New("minimum build source digest is invalid")
	}
	exemptPaths, err := config.minimumBuildExemptPaths()
	if err != nil {
		return runtimeConfig{}, err
	}
	if _, exists := exemptPaths["/ops/app-recovery/version"]; !exists {
		return runtimeConfig{}, errors.New(
			"minimum build exemptions must include /ops/app-recovery/version",
		)
	}
	policies := config.policySet()
	if err := policies.Validate(); err != nil {
		return runtimeConfig{}, err
	}
	for _, name := range requiredUpstreams() {
		origin := strings.TrimSpace(config.Upstreams[name])
		if _, err := parseOrigin(origin); err != nil {
			return runtimeConfig{}, fmt.Errorf("upstream %s: %w", name, err)
		}
		config.Upstreams[name] = origin
	}
	if err := validateAndLoadRolloutConfig(&config, environment, path); err != nil {
		return runtimeConfig{}, err
	}
	if err := graphread.ValidateAndResolveConfig(
		&config.GraphQLRead,
		path,
		config.Rollout.Enabled,
		config.Rollout.Policy.CandidateDigest,
	); err != nil {
		return runtimeConfig{}, err
	}
	redisConfig := config.redisConfig()
	client, err := redisstore.NewClient(redisConfig)
	if err != nil {
		return runtimeConfig{}, fmt.Errorf("admission Redis config: %w", err)
	}
	_ = client.Close()
	return config, nil
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
			"content.post.GetFeed": config.RateLimit.Operation.ContentPostGetFeed.policy(),
		},
	}
}

func (config runtimeConfig) redisConfig() redisstore.Config {
	return redisstore.Config{
		Mode:         config.Redis.Admission.Mode,
		Addr:         config.Redis.Admission.Addr,
		Addrs:        append([]string(nil), config.Redis.Admission.Addrs...),
		Password:     strings.TrimSpace(os.Getenv("API_EDGE_REDIS_PASSWORD")),
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
