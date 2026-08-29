// Package searchbackend assembles the single production recall backend for
// search-service from the autonomous Elasticsearch/OpenSearch configuration.
package searchbackend

import (
	"context"
	"fmt"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
)

// ESConfig consumes the effective config rendered from the search-service autonomous package.
//
// SEARCH_ES_* 是 content-service / entity-service / circle-service 与本服务共享
// 同一 Elasticsearch 集群的部署契约键，用 envAbsolute 逐字保留：它不是本服务
// 可以单方面改名的前缀派生键。索引形状与分片策略只来自配置快照，不接受 env
// 覆盖——它们决定物理索引的可兼容性，必须随发布包一起被 CONFIG_VERSION 钉住。
type ESConfig struct {
	Enabled          bool     `yaml:"enabled" envAbsolute:"SEARCH_ES_ENABLED"`
	Endpoints        []string `yaml:"endpoints" envAbsolute:"SEARCH_ES_ENDPOINTS"`
	Username         string   `yaml:"username" envAbsolute:"SEARCH_ES_USERNAME"`
	Password         string   `yaml:"password" envAbsolute:"SEARCH_ES_PASSWORD"`
	APIKey           string   `yaml:"apiKey" envAbsolute:"SEARCH_ES_API_KEY"`
	Index            string   `yaml:"index"`
	RequestTimeoutMs int      `yaml:"requestTimeoutMs"`
	InsecureTLS      bool     `yaml:"insecureTls"`
	Shards           int      `yaml:"shards"`
	Replicas         int      `yaml:"replicas"`
	Synonyms         []string `yaml:"synonyms"`
	EmbeddingDims    int      `yaml:"embeddingDims"`
}

// Built holds the assembled backend plus the optional ES client (nil when ES is
// configured) so the caller can EnsureIndex and register a health ping.
type Built struct {
	Backend rtsearch.RecallBackend
	Client  *es.Client
}

// Build assembles the only production recall backend. Disabled or incomplete ES
// configuration is rejected instead of selecting another source of truth.
func Build(cfg ESConfig) (Built, error) {
	if !cfg.Enabled {
		return Built{}, fmt.Errorf(
			"search Elasticsearch recall backend is disabled",
		)
	}
	if len(cfg.Endpoints) == 0 {
		return Built{}, fmt.Errorf(
			"search Elasticsearch is enabled without endpoints",
		)
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

	backend := es.NewBackend(client, client.IndexName())
	return Built{Backend: backend, Client: client}, nil
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
