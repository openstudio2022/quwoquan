package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"
	"gopkg.in/yaml.v3"

	httpadapter "quwoquan_service/services/circle-service/internal/adapters/http"
	"quwoquan_service/services/circle-service/internal/application"
	"quwoquan_service/services/circle-service/internal/infrastructure/cache"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

type redisCfg struct {
	Addr     string `yaml:"addr"`
	Password string `yaml:"password"`
	DB       int    `yaml:"db"`
}

type config struct {
	Config struct {
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`

	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	Mongo struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`

	Redis redisCfg `yaml:"redis"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("circle-service runtime identity invalid: %v", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("circle-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("circle-service config compatibility failed: %v", err)
	}

	addr := getenvOrDefault("CIRCLE_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18082"
	}

	ctx := context.Background()

	// MongoDB
	mongoURI := getenvOrDefault("CIRCLE_MONGO_URI", cfg.Mongo.URI)
	if mongoURI == "" {
		mongoURI = "mongodb://localhost:27017"
	}
	mongoDBName := getenvOrDefault("CIRCLE_MONGO_DATABASE", cfg.Mongo.Database)
	if mongoDBName == "" {
		mongoDBName = "quwoquan_circle"
	}

	mongoClient, err := mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		log.Fatalf("circle-service mongo connect failed: %v", err)
	}
	defer mongoClient.Disconnect(ctx)

	db := mongoClient.Database(mongoDBName)
	circleStore := persistence.NewMongoCircleStore(db.Collection("circles"))
	memberStore := persistence.NewMongoMemberStore(db.Collection("circle_members"))
	fileStore := persistence.NewMongoFileStore(db.Collection("circle_files"))

	// Redis cache (optional)
	var store persistence.CircleStore = circleStore
	redisAddr := getenvOrDefault("CIRCLE_REDIS_ADDR", cfg.Redis.Addr)
	if redisAddr != "" {
		rdb := redis.NewClient(&redis.Options{
			Addr:     redisAddr,
			Password: cfg.Redis.Password,
			DB:       cfg.Redis.DB,
		})
		store = cache.NewCachedCircleStore(circleStore, rdb)
		log.Printf("circle-service redis cache enabled addr=%s", redisAddr)
	}

	feedStore := persistence.NewMongoFeedStore(db.Collection("posts"))

	// Application services
	circleService := application.NewCircleService(store, memberStore, fileStore,
		application.WithFeedStore(feedStore),
	)
	fileService := application.NewFileService(fileStore, store)

	handler := httpadapter.NewCircleHandler(circleService, fileService).Routes()

	server := &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}
	log.Printf("circle-service listening on %s (env=%s)", addr, appEnv)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("listen and serve: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "circle-service")
	appEnv = getenvOrDefault("APP_ENV", "local")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")

	if appEnv != "local" && appEnv != "integration" && appEnv != "prod" {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of local|integration|prod, got %q", appEnv)
	}
	if appEnv == "prod" && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=prod")
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func getenvOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}
	if strings.TrimSpace(configRoot) != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")
		mergeConfigFile(&cfg, defaultFile)
		mergeConfigFile(&cfg, envFile)
		if strings.TrimSpace(configVersion) != "" {
			versionFile := filepath.Join(configRoot, "releases", "config", serviceName, configVersion+".yaml")
			mergeConfigFile(&cfg, versionFile)
		}
		return cfg, nil
	}
	localDefault := filepath.Join("configs", "default", "config.yaml")
	localEnv := filepath.Join("configs", appEnv, "config.yaml")
	if _, err := os.Stat(localDefault); err == nil {
		mergeConfigFile(&cfg, localDefault)
		mergeConfigFile(&cfg, localEnv)
		return cfg, nil
	}
	return loadConfig(filepath.Join("configs", "config.yaml")), nil
}

func loadConfig(path string) config {
	cfg := config{}
	raw, err := os.ReadFile(path)
	if err != nil {
		return cfg
	}
	yaml.Unmarshal(raw, &cfg)
	return cfg
}

func mergeConfigFile(cfg *config, path string) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return
	}
	yaml.Unmarshal(raw, cfg)
}

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("CIRCLE_MONGO_URI"); v != "" {
		cfg.Mongo.URI = v
	}
	if v := os.Getenv("CIRCLE_MONGO_DATABASE"); v != "" {
		cfg.Mongo.Database = v
	}
	if v := os.Getenv("CIRCLE_REDIS_ADDR"); v != "" {
		cfg.Redis.Addr = v
	}
	if v := os.Getenv("CIRCLE_REDIS_PASSWORD"); v != "" {
		cfg.Redis.Password = v
	}
	if v := os.Getenv("CIRCLE_REDIS_DB"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			cfg.Redis.DB = n
		}
	}
}

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	return nil
}
