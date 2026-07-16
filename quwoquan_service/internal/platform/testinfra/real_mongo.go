package testinfra

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/testcontainers/testcontainers-go"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	mongoContainerImage = "mongo:7-jammy"
	mongoReplicaSetName = "qwq_test_rs"
	mongoStartupTimeout = 90 * time.Second
)

type RealMongo struct {
	Client       *mongo.Client
	Database     *mongo.Database
	Source       DependencySource
	Endpoint     string
	DatabaseName string
	ReplicaSet   string

	container testcontainers.Container
	process   *managedProcess
}

func StartRealMongo(ctx context.Context, databaseName string) (*RealMongo, error) {
	databaseName = strings.TrimSpace(databaseName)
	if databaseName == "" {
		return nil, errors.New("real Mongo database name is required")
	}

	if mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI")); mongoURI != "" {
		return connectRealMongo(ctx, mongoURI, databaseName, DependencySourceExternal, nil, nil, false)
	}
	if mongoURI := strings.TrimSpace(os.Getenv("QWQ_TEST_MONGO_URI")); mongoURI != "" {
		return connectRealMongo(ctx, mongoURI, databaseName, DependencySourceExternal, nil, nil, false)
	}

	var containerErr error
	if err := containerRuntimeAvailable(); err == nil {
		containerCtx, cancel := context.WithTimeout(ctx, mongoStartupTimeout)
		container, err := startMongoContainer(containerCtx)
		cancel()
		if err == nil {
			mongoURI, uriErr := container.ConnectionString(ctx)
			if uriErr == nil {
				runtime, connectErr := connectRealMongo(
					ctx,
					mongoURI,
					databaseName,
					DependencySourceContainer,
					container,
					nil,
					true,
				)
				if connectErr == nil {
					return runtime, nil
				}
				containerErr = connectErr
			} else {
				containerErr = fmt.Errorf("Mongo testcontainer connection string: %w", uriErr)
			}
			_ = container.Terminate(context.Background())
		} else {
			containerErr = err
		}
	} else {
		containerErr = err
	}

	runtime, nativeErr := startNativeMongo(ctx, databaseName)
	if nativeErr == nil {
		return runtime, nil
	}
	return nil, fmt.Errorf(
		"real MongoDB unavailable; testcontainer failed: %v; native mongod failed: %w",
		containerErr,
		nativeErr,
	)
}

func startMongoContainer(ctx context.Context) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("Mongo testcontainer panic: %v", recovered)
		}
	}()
	return mongomod.Run(
		ctx,
		mongoContainerImage,
		mongomod.WithReplicaSet(mongoReplicaSetName),
	)
}

func startNativeMongo(ctx context.Context, databaseName string) (*RealMongo, error) {
	binary, err := findExecutable(
		"TEST_MONGOD_BIN",
		"mongod",
		"/opt/homebrew/bin/mongod",
		"/usr/local/bin/mongod",
	)
	if err != nil {
		return nil, err
	}
	tempDir, err := os.MkdirTemp("", "quwoquan-test-mongo-*")
	if err != nil {
		return nil, fmt.Errorf("create mongod temp directory: %w", err)
	}
	dataDir := filepath.Join(tempDir, "data")
	if err := os.Mkdir(dataDir, 0o700); err != nil {
		_ = os.RemoveAll(tempDir)
		return nil, fmt.Errorf("create mongod data directory: %w", err)
	}
	port, err := reserveLoopbackPort()
	if err != nil {
		_ = os.RemoveAll(tempDir)
		return nil, err
	}
	endpoint := fmt.Sprintf("127.0.0.1:%d", port)
	process, err := startManagedProcess(
		"mongod",
		binary,
		[]string{
			"--dbpath", dataDir,
			"--port", fmt.Sprintf("%d", port),
			"--bind_ip", "127.0.0.1",
			"--replSet", mongoReplicaSetName,
			"--oplogSize", "128",
			"--nounixsocket",
		},
		tempDir,
		filepath.Join(tempDir, "mongod.log"),
	)
	if err != nil {
		_ = os.RemoveAll(tempDir)
		return nil, err
	}

	if err := initializeNativeReplicaSet(ctx, endpoint, process); err != nil {
		_ = process.close(context.Background())
		return nil, err
	}
	mongoURI := fmt.Sprintf(
		"mongodb://%s/?replicaSet=%s&directConnection=true",
		endpoint,
		mongoReplicaSetName,
	)
	runtime, err := connectRealMongo(
		ctx,
		mongoURI,
		databaseName,
		DependencySourceNative,
		nil,
		process,
		false,
	)
	if err != nil {
		_ = process.close(context.Background())
		return nil, err
	}
	return runtime, nil
}

func initializeNativeReplicaSet(
	ctx context.Context,
	endpoint string,
	process *managedProcess,
) error {
	bootstrapClient, err := mongo.Connect(
		options.Client().
			ApplyURI("mongodb://" + endpoint + "/?directConnection=true").
			SetServerSelectionTimeout(2 * time.Second),
	)
	if err != nil {
		return processFailure(process, "connect native mongod bootstrap client", err)
	}
	defer bootstrapClient.Disconnect(context.Background())

	readyCtx, cancel := context.WithTimeout(ctx, mongoStartupTimeout)
	defer cancel()
	if err := pollDependency(readyCtx, process, "wait for native mongod socket", func() error {
		pingCtx, pingCancel := context.WithTimeout(readyCtx, time.Second)
		defer pingCancel()
		return bootstrapClient.Ping(pingCtx, nil)
	}); err != nil {
		return err
	}

	initCommand := bson.D{
		{Key: "replSetInitiate", Value: bson.D{
			{Key: "_id", Value: mongoReplicaSetName},
			{Key: "members", Value: bson.A{
				bson.D{
					{Key: "_id", Value: 0},
					{Key: "host", Value: endpoint},
				},
			}},
		}},
	}
	if err := bootstrapClient.Database("admin").RunCommand(readyCtx, initCommand).Err(); err != nil {
		var commandErr mongo.CommandError
		if !errors.As(err, &commandErr) || commandErr.Code != 23 {
			return processFailure(process, "initialize native mongod replica set", err)
		}
	}
	return pollDependency(readyCtx, process, "wait for native mongod primary", func() error {
		return verifyMongoPrimary(readyCtx, bootstrapClient)
	})
}

func connectRealMongo(
	ctx context.Context,
	mongoURI string,
	databaseName string,
	source DependencySource,
	container testcontainers.Container,
	process *managedProcess,
	directConnection bool,
) (*RealMongo, error) {
	clientOptions := options.Client().
		ApplyURI(mongoURI).
		SetServerSelectionTimeout(10 * time.Second)
	if directConnection {
		clientOptions.SetDirect(true)
	}
	client, err := mongo.Connect(
		clientOptions,
	)
	if err != nil {
		return nil, fmt.Errorf("connect real MongoDB: %w", err)
	}
	readyCtx, cancel := context.WithTimeout(ctx, mongoStartupTimeout)
	defer cancel()
	if err := pollDependency(readyCtx, process, "wait for real MongoDB replica set", func() error {
		return verifyMongoPrimary(readyCtx, client)
	}); err != nil {
		_ = client.Disconnect(context.Background())
		return nil, err
	}
	return &RealMongo{
		Client:       client,
		Database:     client.Database(databaseName),
		Source:       source,
		Endpoint:     mongoEndpoint(mongoURI),
		DatabaseName: databaseName,
		ReplicaSet:   mongoReplicaSetName,
		container:    container,
		process:      process,
	}, nil
}

func verifyMongoPrimary(ctx context.Context, client *mongo.Client) error {
	var hello struct {
		SetName           string `bson:"setName"`
		IsWritablePrimary bool   `bson:"isWritablePrimary"`
	}
	if err := client.Database("admin").RunCommand(
		ctx,
		bson.D{{Key: "hello", Value: 1}},
	).Decode(&hello); err != nil {
		return err
	}
	if strings.TrimSpace(hello.SetName) == "" {
		return errors.New("MongoDB is not configured as a replica set")
	}
	if !hello.IsWritablePrimary {
		return errors.New("MongoDB replica set has no writable primary")
	}
	return nil
}

func pollDependency(
	ctx context.Context,
	process *managedProcess,
	action string,
	check func() error,
) error {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	var lastErr error
	for {
		if err := check(); err == nil {
			return nil
		} else {
			lastErr = err
		}
		if exited, exitErr := process.exited(); exited {
			return processFailure(
				process,
				action,
				fmt.Errorf("process exited: %v (last readiness error: %w)", exitErr, lastErr),
			)
		}
		select {
		case <-ctx.Done():
			return processFailure(process, action, errors.Join(lastErr, ctx.Err()))
		case <-ticker.C:
		}
	}
}

func mongoEndpoint(mongoURI string) string {
	parsed, err := url.Parse(mongoURI)
	if err != nil || parsed.Host == "" {
		return "configured-external"
	}
	return parsed.Host
}

func (m *RealMongo) Close(ctx context.Context) error {
	if m == nil {
		return nil
	}
	var closeErr error
	if m.Database != nil {
		if err := m.Database.Drop(ctx); err != nil {
			closeErr = errors.Join(closeErr, fmt.Errorf("drop Mongo database %s: %w", m.DatabaseName, err))
		}
	}
	if m.Client != nil {
		if err := m.Client.Disconnect(ctx); err != nil {
			closeErr = errors.Join(closeErr, fmt.Errorf("disconnect MongoDB: %w", err))
		}
	}
	if m.container != nil {
		if err := m.container.Terminate(ctx); err != nil {
			closeErr = errors.Join(closeErr, fmt.Errorf("terminate Mongo testcontainer: %w", err))
		}
	}
	if err := m.process.close(ctx); err != nil {
		closeErr = errors.Join(closeErr, err)
	}
	return closeErr
}
