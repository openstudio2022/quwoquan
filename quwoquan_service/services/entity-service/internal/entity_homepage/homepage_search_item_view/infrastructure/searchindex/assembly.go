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
	return Built{Client: client, Indexer: es.NewIndexer(client, client.WriteIndexName())}, nil
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
	// endpoints 只覆盖地址，不改写 Enabled：启用与否只由 SEARCH_ES_ENABLED 声明。
	// 让地址在场顺带打开开关会让 Enabled 不再是它自己的真相源，注入顺序一变，
	// 一个显式的 false 就被地址静默翻成 true。
	if value := strings.TrimSpace(os.Getenv("SEARCH_ES_ENDPOINTS")); value != "" {
		parts := strings.Split(value, ",")
		endpoints := make([]string, 0, len(parts))
		for _, endpoint := range parts {
			if endpoint = strings.TrimSpace(endpoint); endpoint != "" {
				endpoints = append(endpoints, endpoint)
			}
		}
		cfg.Endpoints = endpoints
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
