// Command migrate-taxonomy-snapshots upgrades tag taxonomy storage to immutable,
// release-scoped snapshots. It is safe to run repeatedly and never deletes data.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"gopkg.in/yaml.v3"

	configrelease "quwoquan_service/runtime/configrelease"
	nodepersistence "quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

type runtimeConfig struct {
	Mongo struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`
}

func main() {
	var (
		mongoURI = flag.String("mongo-uri", "", "MongoDB connection URI (defaults to tag-service runtime configuration)")
		database = flag.String("db", "", "MongoDB database name (defaults to tag-service runtime configuration)")
	)
	flag.Parse()

	resolvedURI, resolvedDatabase, err := resolveMongoConfig(*mongoURI, *database)
	if err != nil {
		log.Fatalf("resolve MongoDB configuration: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	client, err := mongo.Connect(options.Client().ApplyURI(resolvedURI))
	if err != nil {
		log.Fatalf("connect MongoDB: %v", err)
	}
	defer client.Disconnect(context.Background())
	if err := client.Ping(ctx, nil); err != nil {
		log.Fatalf("ping MongoDB: %v", err)
	}

	db := client.Database(resolvedDatabase)
	releaseStore := taxonomyreleasestore.NewStore(db)
	if err := releaseStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("ensure taxonomy release indexes: %v", err)
	}
	nodeStore := nodepersistence.NewMongoTagNodeStore(db.Collection("tag_nodes"))
	if err := nodeStore.MigrateSnapshotIdentity(ctx); err != nil {
		log.Fatalf("migrate tag node snapshot identity: %v", err)
	}
	log.Printf("OK: migrated %s.tag_nodes to release-scoped snapshot identity", resolvedDatabase)
}

func resolveMongoConfig(uriFlag, databaseFlag string) (string, string, error) {
	cfg := runtimeConfig{}
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	if configRoot != "" {
		serviceName := envOrDefault("SERVICE_NAME", "tag-service")
		appEnv := envOrDefault("APP_ENV", "alpha")
		path, err := configrelease.File(configRoot, serviceName, appEnv)
		if err != nil {
			return "", "", fmt.Errorf("resolve runtime config path: %w", err)
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return "", "", fmt.Errorf("read runtime config: %w", err)
		}
		if err := yaml.Unmarshal(raw, &cfg); err != nil {
			return "", "", fmt.Errorf("parse runtime config: %w", err)
		}
	}

	uri := strings.TrimSpace(cfg.Mongo.URI)
	database := strings.TrimSpace(cfg.Mongo.Database)
	if value := strings.TrimSpace(os.Getenv("TAG_MONGO_URI")); value != "" {
		uri = value
	}
	if value := strings.TrimSpace(os.Getenv("TAG_MONGO_DATABASE")); value != "" {
		database = value
	}
	if value := strings.TrimSpace(uriFlag); value != "" {
		uri = value
	}
	if value := strings.TrimSpace(databaseFlag); value != "" {
		database = value
	}
	if uri == "" {
		uri = "mongodb://localhost:27017"
	}
	if database == "" {
		database = "quwoquan_tag"
	}
	return uri, database, nil
}

func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
