package elasticsearch

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"quwoquan_service/runtime/search/es"
)

type Config struct {
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
	Index   *Index
}

func Build(config Config) (Built, error) {
	if !config.Enabled {
		return Built{}, nil
	}
	if len(config.Endpoints) == 0 {
		return Built{}, fmt.Errorf("CircleSearchItemView requires Elasticsearch endpoints")
	}
	client, err := es.NewClient(es.Config{
		Endpoints: config.Endpoints, Username: config.Username, Password: config.Password,
		APIKey: config.APIKey, Index: config.Index,
		RequestTimeout: time.Duration(config.RequestTimeoutMs) * time.Millisecond,
		InsecureTLS:    config.InsecureTLS,
		Schema: es.IndexSchemaConfig{
			NumberOfShards: config.Shards, NumberOfReplicas: config.Replicas,
			Synonyms: config.Synonyms, EmbeddingDims: config.EmbeddingDims,
		},
	})
	if err != nil {
		return Built{}, err
	}
	indexer := es.NewIndexer(client, client.WriteIndexName())
	return Built{Client: client, Indexer: indexer, Index: NewIndex(indexer)}, nil
}

func (built Built) EnsureIndex(ctx context.Context) error {
	if built.Client == nil {
		return nil
	}
	return built.Client.EnsureIndex(ctx)
}

func (built Built) HealthPing() func(context.Context) error {
	if built.Client == nil {
		return nil
	}
	return built.Client.Ping
}

func ApplyEnvOverrides(config *Config) {
	if config == nil {
		return
	}
	// endpoints 只覆盖地址，不改写 Enabled：启用与否只由 SEARCH_ES_ENABLED 声明。
	// 让地址在场顺带打开开关会让 Enabled 不再是它自己的真相源，注入顺序一变，
	// 一个显式的 false 就被地址静默翻成 true。
	if value := strings.TrimSpace(os.Getenv("SEARCH_ES_ENDPOINTS")); value != "" {
		config.Endpoints = nil
		for _, endpoint := range strings.Split(value, ",") {
			if endpoint = strings.TrimSpace(endpoint); endpoint != "" {
				config.Endpoints = append(config.Endpoints, endpoint)
			}
		}
	}
	if value := strings.TrimSpace(os.Getenv("SEARCH_ES_USERNAME")); value != "" {
		config.Username = value
	}
	if value := strings.TrimSpace(os.Getenv("SEARCH_ES_PASSWORD")); value != "" {
		config.Password = value
	}
	if value := strings.TrimSpace(os.Getenv("SEARCH_ES_API_KEY")); value != "" {
		config.APIKey = value
	}
	switch strings.ToLower(strings.TrimSpace(os.Getenv("SEARCH_ES_ENABLED"))) {
	case "true", "1":
		config.Enabled = true
	case "false", "0":
		config.Enabled = false
	}
}
