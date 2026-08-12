package application

import (
	"crypto/sha256"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"

	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"

	"gopkg.in/yaml.v3"
)

var sha256ReferencePattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type RuntimeConfig struct {
	Enabled                 bool
	PolicyFile              string
	PolicySHA256            string
	Policy                  domain.Policy
	CandidateUpstreams      map[string]string
	NetworkAttributeCatalog NetworkAttributeCatalogConfig
}

type NetworkAttributeCatalogConfig struct {
	Enabled bool   `yaml:"enabled"`
	File    string `yaml:"file"`
	SHA256  string `yaml:"sha256"`
}

func ValidateAndLoadRuntimeConfig(
	config *RuntimeConfig,
	environment string,
	runtimeConfigPath string,
	requiredUpstreams []string,
) error {
	if config == nil {
		return errors.New("runtime config is required")
	}
	if strings.TrimSpace(environment) == "prod" && !config.Enabled {
		return errors.New("rollout must be explicitly enabled in prod")
	}
	if !config.Enabled {
		if len(config.CandidateUpstreams) != 0 {
			return errors.New("disabled rollout must not declare candidate upstreams")
		}
		if config.NetworkAttributeCatalog.Enabled ||
			strings.TrimSpace(config.NetworkAttributeCatalog.File) != "" ||
			strings.TrimSpace(config.NetworkAttributeCatalog.SHA256) != "" {
			return errors.New("disabled rollout must not declare a network attribute catalog")
		}
		return nil
	}
	config.PolicyFile = strings.TrimSpace(config.PolicyFile)
	config.PolicySHA256 = strings.ToLower(strings.TrimSpace(config.PolicySHA256))
	if !sha256ReferencePattern.MatchString(config.PolicySHA256) {
		return errors.New("rollout policy SHA-256 reference is invalid")
	}
	if config.PolicyFile == "" {
		return errors.New("rollout policy file is required")
	}
	if !filepath.IsAbs(config.PolicyFile) {
		config.PolicyFile = filepath.Join(
			filepath.Dir(runtimeConfigPath),
			config.PolicyFile,
		)
	}
	policy, err := loadRolloutPolicy(config.PolicyFile, config.PolicySHA256)
	if err != nil {
		return err
	}
	if !policy.Enabled {
		return errors.New("enabled rollout requires an enabled policy")
	}
	config.Policy = policy
	if err := ValidateAndResolveNetworkAttributeCatalogConfig(
		&config.NetworkAttributeCatalog,
		policy,
		runtimeConfigPath,
	); err != nil {
		return err
	}
	for _, name := range requiredUpstreams {
		origin := strings.TrimSpace(config.CandidateUpstreams[name])
		if _, err := parseOrigin(origin); err != nil {
			return fmt.Errorf("candidate upstream %s: %w", name, err)
		}
		config.CandidateUpstreams[name] = origin
	}
	return nil
}

func ValidateAndResolveNetworkAttributeCatalogConfig(
	config *NetworkAttributeCatalogConfig,
	policy domain.Policy,
	runtimeConfigPath string,
) error {
	if config == nil {
		return errors.New("network attribute catalog config is required")
	}
	config.File = strings.TrimSpace(config.File)
	config.SHA256 = strings.ToLower(strings.TrimSpace(config.SHA256))
	if !config.Enabled {
		if config.File != "" || config.SHA256 != "" {
			return errors.New("disabled network attribute catalog must not declare file or digest")
		}
		if policy.RequiresNetworkAttributeCatalog() {
			return errors.New("directed region or carrier rollout requires the network attribute catalog")
		}
		return nil
	}
	if config.File == "" || !sha256ReferencePattern.MatchString(config.SHA256) {
		return errors.New("enabled network attribute catalog requires a file and canonical SHA-256")
	}
	if !filepath.IsAbs(config.File) {
		config.File = filepath.Join(filepath.Dir(runtimeConfigPath), config.File)
	}
	return nil
}

func AllocationKey(
	enabled bool,
	lookup func(string) (string, bool),
) ([]byte, error) {
	if !enabled {
		return nil, nil
	}
	if lookup == nil {
		return nil, errors.New("rollout allocation key secret lookup is required")
	}
	value, exists := lookup("API_EDGE_ROLLOUT_ALLOCATION_KEY")
	value = strings.TrimSpace(value)
	if !exists || len(value) < 32 {
		return nil, errors.New(
			"API_EDGE_ROLLOUT_ALLOCATION_KEY must contain at least 32 secret bytes",
		)
	}
	return []byte(value), nil
}

func NormalizeMetricValue(value, fallback string) string {
	if value = strings.ToLower(strings.TrimSpace(value)); value != "" && len(value) <= 32 {
		return value
	}
	return fallback
}

func NormalizeBuildMetricValue(value string) string {
	value = strings.TrimSpace(value)
	if _, err := strconv.ParseUint(value, 10, 64); err != nil || len(value) > 20 {
		if value == "" {
			return "missing"
		}
		return "invalid"
	}
	return value
}

type rolloutPolicyDocument struct {
	Policy domain.Policy `yaml:"policy"`
}

func loadRolloutPolicy(path, expectedDigest string) (domain.Policy, error) {
	raw, err := os.ReadFile(strings.TrimSpace(path))
	if err != nil {
		return domain.Policy{}, fmt.Errorf("read rollout policy: %w", err)
	}
	actualDigest := fmt.Sprintf("sha256:%x", sha256.Sum256(raw))
	if actualDigest != strings.ToLower(strings.TrimSpace(expectedDigest)) {
		return domain.Policy{}, fmt.Errorf(
			"rollout policy digest mismatch: got %s",
			actualDigest,
		)
	}
	var document rolloutPolicyDocument
	if err := yaml.Unmarshal(raw, &document); err != nil {
		return domain.Policy{}, fmt.Errorf("parse rollout policy: %w", err)
	}
	if err := document.Policy.Validate(); err != nil {
		return domain.Policy{}, fmt.Errorf("validate rollout policy: %w", err)
	}
	return document.Policy, nil
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
