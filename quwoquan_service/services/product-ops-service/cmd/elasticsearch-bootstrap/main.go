// Command elasticsearch-bootstrap provisions Product telemetry and Runtime logs
// Elasticsearch lifecycle policies, templates, and first daily indices. It is a
// deployment-only command; the long-running service never receives this key.
package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	persistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

const (
	endpointEnv = "PRODUCT_OPS_ELASTICSEARCH_ADMIN_ENDPOINT"
	apiKeyEnv   = "PRODUCT_OPS_ELASTICSEARCH_ADMIN_API_KEY"
)

func main() {
	if err := run(context.Background(), os.LookupEnv); err != nil {
		fmt.Fprintln(os.Stderr, "product-ops Elasticsearch bootstrap failed:", err)
		os.Exit(1)
	}
}

func run(ctx context.Context, lookupEnv func(string) (string, bool)) error {
	endpoint, err := requiredEnvironment(lookupEnv, endpointEnv)
	if err != nil {
		return err
	}
	apiKey, err := requiredEnvironment(lookupEnv, apiKeyEnv)
	if err != nil {
		return err
	}
	configs := []persistence.ElasticsearchConfig{
		{
			Kind:                   persistence.ElasticsearchTelemetryStoreKind,
			Endpoint:               endpoint,
			APIKey:                 apiKey,
			RawIndex:               requiredIndex(lookupEnv, "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_RAW_INDEX"),
			StartupDiagnosticIndex: requiredIndex(lookupEnv, "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_STARTUP_DIAGNOSTIC_INDEX"),
			AggregateIndex:         requiredIndex(lookupEnv, "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_AGGREGATE_INDEX"),
			Timeout:                30 * time.Second,
		},
		{
			Kind:           persistence.ElasticsearchRuntimeLogStoreKind,
			Endpoint:       endpoint,
			APIKey:         apiKey,
			RawIndex:       requiredIndex(lookupEnv, "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_RAW_INDEX"),
			AggregateIndex: requiredIndex(lookupEnv, "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_AGGREGATE_INDEX"),
			Timeout:        30 * time.Second,
		},
	}
	for _, config := range configs {
		for _, index := range []string{config.RawIndex, config.AggregateIndex} {
			if strings.TrimSpace(index) == "" {
				return fmt.Errorf("required Elasticsearch index environment is missing")
			}
		}
		if config.Kind == persistence.ElasticsearchTelemetryStoreKind && strings.TrimSpace(config.StartupDiagnosticIndex) == "" {
			return fmt.Errorf("required Elasticsearch startup diagnostic index environment is missing")
		}
		store, err := persistence.NewElasticsearchEventLogStore(config)
		if err != nil {
			return err
		}
		if err := store.EnsureIndices(ctx); err != nil {
			return err
		}
	}
	return nil
}

func requiredIndex(lookupEnv func(string) (string, bool), key string) string {
	value, _ := lookupEnv(key)
	return strings.TrimSpace(value)
}

func requiredEnvironment(lookupEnv func(string) (string, bool), key string) (string, error) {
	value, exists := lookupEnv(key)
	value = strings.TrimSpace(value)
	if !exists || value == "" {
		return "", fmt.Errorf("%s is required", key)
	}
	return value, nil
}
