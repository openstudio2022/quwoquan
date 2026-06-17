package searchindex

import (
	"context"
	"os"
	"strings"
	"time"

	"quwoquan_service/runtime/search/es"
)

// ESConfig mirrors the configs/<env>/config.yaml `es:` section. It is the same
// shape search-service uses; both write into and read from the one shared
// ES/OpenSearch cluster + index, so endpoints/credentials are injected via the
// shared SEARCH_ES_* env (deploy secrets), never hardcoded.
type ESConfig struct {
	Enabled          bool     `yaml:"enabled"`
	Endpoints        []string `yaml:"endpoints"`
	Username         string   `yaml:"username"`
	Password         string   `yaml:"password"`
	APIKey           string   `yaml:"apiKey"`
	Index            string   `yaml:"index"`
	RequestTimeoutMs int      `yaml:"requestTimeoutMs"`
	InsecureTLS      bool     `yaml:"insecureTls"`
	Shards           int      `yaml:"shards"`
	Replicas         int      `yaml:"replicas"`
	Synonyms         []string `yaml:"synonyms"`
	EmbeddingDims    int      `yaml:"embeddingDims"`
}

// Built holds the assembled write-side index components. When ES is disabled all
// fields are nil and every helper is a no-op, so the primary write path is
// unaffected.
type Built struct {
	Client    *es.Client
	Indexer   *es.Indexer
	Projector *Projector
}

// Build assembles the write-time search index from config. When ES is disabled or
// has no endpoints it returns an empty (no-op) Built so the entity write path is
// unchanged.
func Build(cfg ESConfig, opts ...Option) (Built, error) {
	if !cfg.Enabled || len(cfg.Endpoints) == 0 {
		return Built{}, nil
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
	indexer := es.NewIndexer(client, client.IndexName())
	return Built{
		Client:    client,
		Indexer:   indexer,
		Projector: NewProjector(indexer, opts...),
	}, nil
}

// EnsureIndex creates the unified index when ES is enabled (no-op otherwise).
func (b Built) EnsureIndex(ctx context.Context) error {
	if b.Client == nil {
		return nil
	}
	return b.Client.EnsureIndex(ctx)
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
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_ENDPOINTS")); v != "" {
		parts := strings.Split(v, ",")
		eps := make([]string, 0, len(parts))
		for _, p := range parts {
			if p = strings.TrimSpace(p); p != "" {
				eps = append(eps, p)
			}
		}
		cfg.Endpoints = eps
		cfg.Enabled = true
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
