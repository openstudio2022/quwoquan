// Package searchbackend assembles the single production recall backend for
// search-service from the autonomous Elasticsearch/OpenSearch configuration.
package searchbackend

import (
	"context"
	"fmt"
	"slices"
	"strings"
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

	// Writer* is the Search-owned UserProfile projection credential. It is a
	// second role binding over the same generation, not an alternate provider.
	WriterEnabled   bool     `yaml:"-" envAbsolute:"SEARCH_ES_WRITER_ENABLED"`
	WriterEndpoints []string `yaml:"-" envAbsolute:"SEARCH_ES_WRITER_ENDPOINTS"`
	WriterUsername  string   `yaml:"-" envAbsolute:"SEARCH_ES_WRITER_USERNAME"`
	WriterPassword  string   `yaml:"-" envAbsolute:"SEARCH_ES_WRITER_PASSWORD"`
	WriterAPIKey    string   `yaml:"-" envAbsolute:"SEARCH_ES_WRITER_API_KEY"`
	WriterIndex     string   `yaml:"-" envAbsolute:"SEARCH_ES_WRITER_INDEX"`
}

// Built holds role-scoped clients over one search.objects generation. Reader
// serves recall/PIT/readiness; Writer is used only by the Search-owned profile
// projection. Index lifecycle is deployment-control/admin work and is never
// attempted by either application credential.
type Built struct {
	Backend rtsearch.RecallBackend
	Reader  *es.Client
	Writer  *es.Client
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
			"search Elasticsearch is enabled without reader endpoints",
		)
	}
	if !cfg.WriterEnabled || len(cfg.WriterEndpoints) == 0 {
		return Built{}, fmt.Errorf(
			"search Elasticsearch UserProfile projection writer binding is incomplete",
		)
	}
	if strings.TrimSpace(cfg.WriterIndex) != strings.TrimSpace(cfg.Index) ||
		!sameEndpoints(cfg.Endpoints, cfg.WriterEndpoints) {
		return Built{}, fmt.Errorf(
			"search Elasticsearch reader and writer bindings must share one generation",
		)
	}
	if strings.TrimSpace(cfg.APIKey) != "" && cfg.APIKey == cfg.WriterAPIKey {
		return Built{}, fmt.Errorf(
			"search Elasticsearch reader and writer credentials must be role-separated",
		)
	}

	reader, err := newClient(cfg, cfg.Endpoints, cfg.Username, cfg.Password, cfg.APIKey)
	if err != nil {
		return Built{}, err
	}
	writer, err := newClient(
		cfg,
		cfg.WriterEndpoints,
		cfg.WriterUsername,
		cfg.WriterPassword,
		cfg.WriterAPIKey,
	)
	if err != nil {
		return Built{}, err
	}

	backend := es.NewBackend(reader, reader.IndexName())
	return Built{Backend: backend, Reader: reader, Writer: writer}, nil
}

func newClient(
	cfg ESConfig,
	endpoints []string,
	username string,
	password string,
	apiKey string,
) (*es.Client, error) {
	return es.NewClient(es.Config{
		Endpoints:      endpoints,
		Username:       username,
		Password:       password,
		APIKey:         apiKey,
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
}

func sameEndpoints(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	normalize := func(values []string) []string {
		normalized := make([]string, 0, len(values))
		for _, value := range values {
			normalized = append(
				normalized,
				strings.TrimRight(strings.TrimSpace(value), "/"),
			)
		}
		slices.Sort(normalized)
		return normalized
	}
	return slices.Equal(normalize(left), normalize(right))
}

// ReadinessCheck returns the functional ES query probe required by the search
// serving path when Elasticsearch is enabled, else nil.
func (b Built) ReadinessCheck() func(context.Context) error {
	if b.Reader == nil {
		return nil
	}
	return b.Reader.CheckSearchReady
}
