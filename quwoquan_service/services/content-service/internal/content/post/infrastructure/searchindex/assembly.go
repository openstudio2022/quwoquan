package searchindex

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	"quwoquan_service/runtime/search/es"
)

// ESConfig consumes the effective config rendered from the content-service autonomous package. It is the same
// shape search-service uses; both write into and read from the one shared
// ES/OpenSearch cluster + index, so endpoints/credentials are injected via the
// shared SEARCH_ES_* env (deploy secrets), never hardcoded.
type ESConfig struct {
	Enabled                 bool     `yaml:"enabled"`
	Endpoints               []string `yaml:"endpoints"`
	Username                string   `yaml:"username"`
	Password                string   `yaml:"password"`
	APIKey                  string   `yaml:"apiKey"`
	Index                   string   `yaml:"index"`
	RequestTimeoutMs        int      `yaml:"requestTimeoutMs"`
	StartupTimeoutMs        int      `yaml:"startupTimeoutMs"`
	StartupInitialBackoffMs int      `yaml:"startupInitialBackoffMs"`
	StartupMaxBackoffMs     int      `yaml:"startupMaxBackoffMs"`
	InsecureTLS             bool     `yaml:"insecureTls"`
	Shards                  int      `yaml:"shards"`
	Replicas                int      `yaml:"replicas"`
	Synonyms                []string `yaml:"synonyms"`
	EmbeddingDims           int      `yaml:"embeddingDims"`
}

// Built holds the assembled write-side index components. When ES is disabled all
// fields are nil and every helper is a no-op, so the primary write path is
// unaffected.
type Built struct {
	Client    *es.Client
	Indexer   *es.Indexer
	Projector *Projector
	startup   startupRetryPolicy
}

var ErrSearchIndexStartupTimeout = errors.New("search index startup timed out")

const (
	defaultStartupTimeout        = 60 * time.Second
	defaultStartupInitialBackoff = 100 * time.Millisecond
	defaultStartupMaxBackoff     = 2 * time.Second
)

type startupRetryPolicy struct {
	timeout        time.Duration
	initialBackoff time.Duration
	maxBackoff     time.Duration
}

// Build assembles the write-time search index from config. An explicitly
// disabled projection returns an empty Built; an enabled but incomplete
// configuration fails fast.
func Build(cfg ESConfig, reader PostReader, opts ...Option) (Built, error) {
	if !cfg.Enabled {
		return Built{}, nil
	}
	if len(cfg.Endpoints) == 0 || reader == nil {
		return Built{}, fmt.Errorf(
			"Post search projection requires endpoints and reader",
		)
	}
	startup, err := startupPolicy(cfg)
	if err != nil {
		return Built{}, err
	}
	client, err := es.NewClient(es.Config{
		Endpoints:      cfg.Endpoints,
		Username:       cfg.Username,
		Password:       cfg.Password,
		APIKey:         cfg.APIKey,
		Index:          cfg.Index,
		RequestTimeout: time.Duration(cfg.RequestTimeoutMs) * time.Millisecond,
		InsecureTLS:    cfg.InsecureTLS,
		Schema: es.IndexSchemaConfig{
			NumberOfShards:   cfg.Shards,
			NumberOfReplicas: cfg.Replicas,
			Synonyms:         cfg.Synonyms,
			EmbeddingDims:    cfg.EmbeddingDims,
		},
	})
	if err != nil {
		return Built{}, err
	}
	indexer := es.NewIndexer(client, client.WriteIndexName())
	return Built{
		Client:    client,
		Indexer:   indexer,
		Projector: NewProjector(indexer, reader, opts...),
		startup:   startup,
	}, nil
}

// EnsureIndex creates the unified index when ES is enabled. Recoverable remote
// startup failures are retried within the configured bounded policy.
func (b Built) EnsureIndex(ctx context.Context) error {
	return b.EnsureIndexReady(ctx)
}

// EnsureIndexReady waits only for typed recoverable transport, capacity and
// server failures. Authentication, configuration and schema failures return on
// the first attempt; the caller remains fail-closed when the deadline expires.
func (b Built) EnsureIndexReady(ctx context.Context) error {
	if b.Client == nil {
		return nil
	}
	startupCtx, cancel := context.WithTimeout(ctx, b.startup.timeout)
	defer cancel()

	backoff := b.startup.initialBackoff
	var lastErr error
	for {
		err := b.Client.EnsureIndex(startupCtx)
		if err == nil {
			return nil
		}
		lastErr = err
		if startupCtx.Err() != nil {
			return b.startupDeadlineError(ctx, lastErr)
		}
		if !es.IsDependencyUnavailable(err) {
			return err
		}

		timer := time.NewTimer(backoff)
		select {
		case <-startupCtx.Done():
			if !timer.Stop() {
				select {
				case <-timer.C:
				default:
				}
			}
			return b.startupDeadlineError(ctx, lastErr)
		case <-timer.C:
		}
		if backoff < b.startup.maxBackoff {
			backoff *= 2
			if backoff > b.startup.maxBackoff {
				backoff = b.startup.maxBackoff
			}
		}
	}
}

func (b Built) startupDeadlineError(ctx context.Context, lastErr error) error {
	if ctx.Err() != nil {
		return fmt.Errorf("search index startup canceled: %w", ctx.Err())
	}
	return fmt.Errorf(
		"%w after %s: %v",
		ErrSearchIndexStartupTimeout,
		b.startup.timeout,
		lastErr,
	)
}

func startupPolicy(cfg ESConfig) (startupRetryPolicy, error) {
	timeout, err := configuredDuration(
		"startupTimeoutMs",
		cfg.StartupTimeoutMs,
		defaultStartupTimeout,
	)
	if err != nil {
		return startupRetryPolicy{}, err
	}
	initialBackoff, err := configuredDuration(
		"startupInitialBackoffMs",
		cfg.StartupInitialBackoffMs,
		defaultStartupInitialBackoff,
	)
	if err != nil {
		return startupRetryPolicy{}, err
	}
	maxBackoff, err := configuredDuration(
		"startupMaxBackoffMs",
		cfg.StartupMaxBackoffMs,
		defaultStartupMaxBackoff,
	)
	if err != nil {
		return startupRetryPolicy{}, err
	}
	if initialBackoff > maxBackoff {
		return startupRetryPolicy{}, fmt.Errorf(
			"Post search projection requires startupInitialBackoffMs <= startupMaxBackoffMs",
		)
	}
	return startupRetryPolicy{
		timeout:        timeout,
		initialBackoff: initialBackoff,
		maxBackoff:     maxBackoff,
	}, nil
}

func configuredDuration(name string, milliseconds int, fallback time.Duration) (time.Duration, error) {
	if milliseconds < 0 {
		return 0, fmt.Errorf("Post search projection requires non-negative %s", name)
	}
	if milliseconds == 0 {
		return fallback, nil
	}
	return time.Duration(milliseconds) * time.Millisecond, nil
}

// HealthPing returns an ES liveness probe when ES is enabled, else nil.
func (b Built) HealthPing() func(context.Context) error {
	if b.Client == nil {
		return nil
	}
	return b.Client.Ping
}

// ApplyESEnvOverrides lets the deploy layer inject ES endpoints/credentials as
// environment secrets (shared with search-service via the SEARCH_ES_* prefix,
// since both target the one shared cluster), without hardcoding them in committed
// config.
func ApplyESEnvOverrides(cfg *ESConfig) {
	if cfg == nil {
		return
	}
	// endpoints 只覆盖地址，不改写 Enabled：启用与否只由 SEARCH_ES_ENABLED 声明。
	// 让地址在场顺带打开开关会让 Enabled 不再是它自己的真相源，注入顺序一变，
	// 一个显式的 false 就被地址静默翻成 true。
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_ENDPOINTS")); v != "" {
		parts := strings.Split(v, ",")
		eps := make([]string, 0, len(parts))
		for _, p := range parts {
			if p = strings.TrimSpace(p); p != "" {
				eps = append(eps, p)
			}
		}
		cfg.Endpoints = eps
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_USERNAME")); v != "" {
		cfg.Username = v
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_PASSWORD")); v != "" {
		cfg.Password = v
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_API_KEY")); v != "" {
		cfg.APIKey = v
	}
	switch strings.ToLower(strings.TrimSpace(os.Getenv("SEARCH_ES_ENABLED"))) {
	case "true", "1":
		cfg.Enabled = true
	case "false", "0":
		cfg.Enabled = false
	}
}
