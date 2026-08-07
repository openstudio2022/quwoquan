package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/signal"
	"syscall"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	runtimeconfig "quwoquan_service/runtime/config"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/content-service/internal/content/post/application/importer"
)

// observeExecutionState composes the existing execution-scoped Mongo reader
// and Redis stream into a single canonical JSON observation. It deliberately
// does not call EnsureIndexes, Ready.Ensure, Claim, ACK, dispatch, or cleanup.
func observeExecutionState(
	executionID string,
	carrier string,
	requestBindingDigest string,
	executionEnvelopeDigest string,
	rawCampaignBinding string,
) error {
	var campaignBinding reliabletask.DataContentCampaignBinding
	decoder := json.NewDecoder(bytes.NewBufferString(rawCampaignBinding))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&campaignBinding); err != nil {
		return fmt.Errorf("decode ReliableTask observer campaign binding: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err == nil {
		return fmt.Errorf("ReliableTask observer campaign binding contains multiple JSON values")
	} else if err != io.EOF {
		return fmt.Errorf("decode ReliableTask observer campaign binding trailing data: %w", err)
	}
	request := reliabletask.DataContentExecutionObservationRequest{
		ExecutionID:             executionID,
		Carrier:                 carrier,
		RequestBindingDigest:    requestBindingDigest,
		ExecutionEnvelopeDigest: executionEnvelopeDigest,
		Campaign:                campaignBinding,
	}
	cfg, err := importer.LoadFleetStoreConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(
		context.Background(),
		syscall.SIGINT,
		syscall.SIGTERM,
	)
	defer stop()
	client, err := mongo.Connect(options.Client().ApplyURI(cfg.MongoURI))
	if err != nil {
		return fmt.Errorf("connect ReliableTask Mongo observer: %w", err)
	}
	defer client.Disconnect(context.Background())
	store := reliabletaskmongo.NewDataContentImport(
		client.Database(cfg.MongoDatabase),
	)
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {
				Mode:     "standalone",
				Addr:     cfg.RedisAddr,
				Password: cfg.RedisPassword,
			},
		},
		DefaultScene: "reliabletask",
	})
	defer router.Close()
	executionHash := sha256.Sum256([]byte(executionID))
	streamSuffix := hex.EncodeToString(executionHash[:])
	ready, err := reliabletask.NewRedisReadyIndex(
		reliabletask.RedisReadyIndexConfig{
			Client: router.Scene("reliabletask"),
			Stream: "reliabletask:data:content:" + streamSuffix,
			Group:  "data.content_supply." + streamSuffix,
			Queue:  reliabletask.DataContentQueue,
		},
	)
	if err != nil {
		return fmt.Errorf("create ReliableTask observer ready index: %w", err)
	}
	observer := reliabletask.DataContentExecutionObserver{
		Store: store,
		Ready: ready,
	}
	observation, err := observer.ObserveExecution(ctx, request)
	if err != nil {
		return fmt.Errorf("observe ReliableTask execution: %w", err)
	}
	payload, err := reliabletask.MarshalDataContentExecutionObservation(observation)
	if err != nil {
		return fmt.Errorf("marshal ReliableTask execution observation: %w", err)
	}
	if _, err := os.Stdout.Write(append(payload, '\n')); err != nil {
		return fmt.Errorf("write ReliableTask execution observation: %w", err)
	}
	return nil
}
