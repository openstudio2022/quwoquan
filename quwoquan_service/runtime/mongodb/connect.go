package mongodb

import (
	"context"
	"fmt"
	"log"
	"time"

	rtmongo "quwoquan_service/runtime/mongo"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"go.mongodb.org/mongo-driver/v2/mongo/readconcern"
	"go.mongodb.org/mongo-driver/v2/mongo/writeconcern"
)

type ConnectConfig struct {
	URI                    string
	Database               string
	MaxPoolSize            uint64
	MinPoolSize            uint64
	ConnectTimeoutSeconds  int
	ServerSelectionSeconds int
}

const (
	defaultMaxPoolSize            = 50
	defaultMinPoolSize            = 5
	defaultConnectTimeoutSeconds  = 5
	defaultServerSelectionSeconds = 5
)

func applyDefaults(cfg *ConnectConfig) {
	if cfg.MaxPoolSize == 0 {
		cfg.MaxPoolSize = defaultMaxPoolSize
	}
	if cfg.MinPoolSize == 0 {
		cfg.MinPoolSize = defaultMinPoolSize
	}
	if cfg.ConnectTimeoutSeconds == 0 {
		cfg.ConnectTimeoutSeconds = defaultConnectTimeoutSeconds
	}
	if cfg.ServerSelectionSeconds == 0 {
		cfg.ServerSelectionSeconds = defaultServerSelectionSeconds
	}
}

// MustConnect connects to MongoDB with pool settings and a Ping check.
// Panics via log.Fatalf on failure.
func MustConnect(ctx context.Context, cfg ConnectConfig, serviceName string) *mongo.Client {
	client, err := Connect(ctx, cfg)
	if err != nil {
		log.Fatalf("%s mongo connect failed: %v", serviceName, err)
	}
	return client
}

// Connect returns a configured mongo.Client with pool parameters and a Ping.
func Connect(ctx context.Context, cfg ConnectConfig) (*mongo.Client, error) {
	if cfg.URI == "" {
		return nil, fmt.Errorf("mongodb: URI is empty")
	}
	applyDefaults(&cfg)

	opts := options.Client().
		ApplyURI(cfg.URI).
		SetMaxPoolSize(cfg.MaxPoolSize).
		SetMinPoolSize(cfg.MinPoolSize).
		SetConnectTimeout(time.Duration(cfg.ConnectTimeoutSeconds) * time.Second).
		SetServerSelectionTimeout(time.Duration(cfg.ServerSelectionSeconds) * time.Second).
		SetReadConcern(readconcern.Majority()).
		SetWriteConcern(writeconcern.Majority()).
		SetMonitor(rtmongo.NewCommandMonitor()).
		SetPoolMonitor(rtmongo.NewPoolMonitor())

	client, err := mongo.Connect(opts)
	if err != nil {
		return nil, fmt.Errorf("mongodb: connect: %w", err)
	}

	pingCtx, cancel := context.WithTimeout(ctx, time.Duration(cfg.ConnectTimeoutSeconds)*time.Second)
	defer cancel()
	if err := client.Ping(pingCtx, nil); err != nil {
		_ = client.Disconnect(ctx)
		return nil, fmt.Errorf("mongodb: ping: %w", err)
	}

	return client, nil
}
