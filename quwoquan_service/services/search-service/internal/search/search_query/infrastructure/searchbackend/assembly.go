// Package searchbackend assembles the recall backend for search-service from
// configuration: ES/OpenSearch as primary with an optional native fallback.
package searchbackend

import (
	"context"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
)

// ESConfig consumes the effective config rendered from the search-service autonomous package.
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

// Built holds the assembled backend plus the optional ES client (nil when ES is
// disabled) so the caller can EnsureIndex and register a health ping.
type Built struct {
	Backend rtsearch.RecallBackend
	Client  *es.Client
}

// Build assembles the recall backend. When ES is enabled it is the primary
// backend (with native fallback when provided); otherwise the native fallback is
// used directly. ES failures degrade transparently via rtsearch.Retrieve.
func Build(cfg ESConfig, fallback rtsearch.RecallBackend) (Built, error) {
	if !cfg.Enabled || len(cfg.Endpoints) == 0 {
		if fallback == nil {
			// No ES and no domain sources here: serve an empty native backend so
			// queries return empty + degrade instead of crashing.
			fallback = rtsearch.NewSliceBackend(nil)
		}
		return Built{Backend: fallback}, nil
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

	var backend rtsearch.RecallBackend
	if fallback != nil {
		backend = es.NewRecallBackend(client, fallback)
	} else {
		backend = es.NewBackend(client, client.IndexName())
	}
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
