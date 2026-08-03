// Package searchindex assembles the external Elasticsearch dependency owned by
// HomepageSearchItemView. It does not contain projection rules or checkpoints.
package searchindex

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"quwoquan_service/runtime/search/es"
)

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

type Built struct {
	Client  *es.Client
	Indexer *es.Indexer
}

func Build(cfg ESConfig) (Built, error) {
	if !cfg.Enabled {
		return Built{}, nil
	}
	if len(cfg.Endpoints) == 0 {
		return Built{}, fmt.Errorf("HomepageSearchItemView requires Elasticsearch endpoints")
	}
	client, err := es.NewClient(es.Config{
		Endpoints: cfg.Endpoints, Username: cfg.Username, Password: cfg.Password,
		APIKey: cfg.APIKey, Index: cfg.Index,
		RequestTimeout: time.Duration(cfg.RequestTimeoutMs) * time.Millisecond,
		InsecureTLS:    cfg.InsecureTLS,
		Schema: es.IndexSchemaConfig{
			NumberOfShards: cfg.Shards, NumberOfReplicas: cfg.Replicas,
			Synonyms: cfg.Synonyms, EmbeddingDims: cfg.EmbeddingDims,
		},
	})
	if err != nil {
		return Built{}, err
	}
	return Built{Client: client, Indexer: es.NewIndexer(client, client.IndexName())}, nil
}

func (b Built) EnsureIndex(ctx context.Context) error {
	if b.Client == nil {
		return nil
	}
	return b.Client.EnsureIndex(ctx)
}

func (b Built) HealthPing() func(context.Context) error {
	if b.Client == nil {
		return nil
	}
	return b.Client.Ping
}

func ApplyESEnvOverrides(cfg *ESConfig) {
	if cfg == nil {
		return
	}
	if value := strings.TrimSpace(os.Getenv("SEARCH_ES_ENDPOINTS")); value != "" {
		parts := strings.Split(value, ",")
		endpoints := make([]string, 0, len(parts))
		for _, endpoint := range parts {
			if endpoint = strings.TrimSpace(endpoint); endpoint != "" {
				endpoints = append(endpoints, endpoint)
			}
		}
		cfg.Endpoints, cfg.Enabled = endpoints, true
	}
	if value := strings.TrimSpace(os.Getenv("SEARCH_ES_USERNAME")); value != "" {
		cfg.Username = value
	}
	if value := strings.TrimSpace(os.Getenv("SEARCH_ES_PASSWORD")); value != "" {
		cfg.Password = value
	}
	if value := strings.TrimSpace(os.Getenv("SEARCH_ES_API_KEY")); value != "" {
		cfg.APIKey = value
	}
	switch strings.ToLower(strings.TrimSpace(os.Getenv("SEARCH_ES_ENABLED"))) {
	case "true", "1":
		cfg.Enabled = true
	case "false", "0":
		cfg.Enabled = false
	}
}
