package testinfra

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	goredis "github.com/redis/go-redis/v9"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"
)

const (
	redisContainerImage = "redis:7-alpine"
	redisStartupTimeout = 60 * time.Second
)

type RealRedis struct {
	Addr     string
	Password string
	TLS      bool
	Source   DependencySource

	probe     *goredis.Client
	container testcontainers.Container
	process   *managedProcess
}

func StartRealRedis(ctx context.Context) (*RealRedis, error) {
	if configured := strings.TrimSpace(os.Getenv("TEST_REDIS_ADDR")); configured != "" {
		return connectRealRedis(
			ctx,
			configured,
			strings.TrimSpace(os.Getenv("TEST_REDIS_PASSWORD")),
			DependencySourceExternal,
			nil,
			nil,
		)
	}
	if configured := strings.TrimSpace(os.Getenv("QWQ_TEST_REDIS_ADDR")); configured != "" {
		return connectRealRedis(
			ctx,
			configured,
			strings.TrimSpace(os.Getenv("QWQ_TEST_REDIS_PASSWORD")),
			DependencySourceExternal,
			nil,
			nil,
		)
	}

	var containerErr error
	if err := containerRuntimeAvailable(); err == nil {
		containerCtx, cancel := context.WithTimeout(ctx, redisStartupTimeout)
		container, err := startRedisContainer(containerCtx)
		cancel()
		if err == nil {
			endpoint, endpointErr := container.Endpoint(ctx, "")
			if endpointErr == nil {
				runtime, connectErr := connectRealRedis(
					ctx,
					endpoint,
					"",
					DependencySourceContainer,
					container,
					nil,
				)
				if connectErr == nil {
					return runtime, nil
				}
				containerErr = connectErr
			} else {
				containerErr = fmt.Errorf("Redis testcontainer endpoint: %w", endpointErr)
			}
			_ = container.Terminate(context.Background())
		} else {
			containerErr = err
		}
	} else {
		containerErr = err
	}

	runtime, nativeErr := startNativeRedis(ctx)
	if nativeErr == nil {
		return runtime, nil
	}
	return nil, fmt.Errorf(
		"real Redis unavailable; testcontainer failed: %v; native redis-server failed: %w",
		containerErr,
		nativeErr,
	)
}

func startRedisContainer(ctx context.Context) (container testcontainers.Container, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("Redis testcontainer panic: %v", recovered)
		}
	}()
	return testcontainers.Run(
		ctx,
		redisContainerImage,
		testcontainers.WithExposedPorts("6379/tcp"),
		testcontainers.WithWaitStrategy(
			wait.ForListeningPort("6379/tcp").WithStartupTimeout(redisStartupTimeout),
		),
	)
}

func startNativeRedis(ctx context.Context) (*RealRedis, error) {
	binary, err := findExecutable(
		"TEST_REDIS_SERVER_BIN",
		"redis-server",
		"/opt/homebrew/bin/redis-server",
		"/usr/local/bin/redis-server",
	)
	if err != nil {
		return nil, err
	}
	tempDir, err := os.MkdirTemp("", "quwoquan-test-redis-*")
	if err != nil {
		return nil, fmt.Errorf("create redis-server temp directory: %w", err)
	}
	port, err := reserveLoopbackPort()
	if err != nil {
		_ = os.RemoveAll(tempDir)
		return nil, err
	}
	endpoint := fmt.Sprintf("127.0.0.1:%d", port)
	process, err := startManagedProcess(
		"redis-server",
		binary,
		[]string{
			"--bind", "127.0.0.1",
			"--port", strconv.Itoa(port),
			"--protected-mode", "yes",
			"--appendonly", "no",
			"--save", "",
			"--dir", tempDir,
			"--dbfilename", "dump.rdb",
			"--databases", "16",
		},
		tempDir,
		filepath.Join(tempDir, "redis-server.log"),
	)
	if err != nil {
		_ = os.RemoveAll(tempDir)
		return nil, err
	}
	runtime, err := connectRealRedis(
		ctx,
		endpoint,
		"",
		DependencySourceNative,
		nil,
		process,
	)
	if err != nil {
		_ = process.close(context.Background())
		return nil, err
	}
	return runtime, nil
}

func connectRealRedis(
	ctx context.Context,
	configuredAddr string,
	configuredPassword string,
	source DependencySource,
	container testcontainers.Container,
	process *managedProcess,
) (*RealRedis, error) {
	options, tlsEnabled, err := realRedisOptions(configuredAddr, configuredPassword, 0)
	if err != nil {
		return nil, err
	}
	probe := goredis.NewClient(options)
	readyCtx, cancel := context.WithTimeout(ctx, redisStartupTimeout)
	defer cancel()
	if err := pollDependency(readyCtx, process, "wait for real Redis", func() error {
		pingCtx, pingCancel := context.WithTimeout(readyCtx, time.Second)
		defer pingCancel()
		return probe.Ping(pingCtx).Err()
	}); err != nil {
		_ = probe.Close()
		return nil, err
	}
	return &RealRedis{
		Addr:      options.Addr,
		Password:  options.Password,
		TLS:       tlsEnabled,
		Source:    source,
		probe:     probe,
		container: container,
		process:   process,
	}, nil
}

func realRedisOptions(configuredAddr, configuredPassword string, database int) (*goredis.Options, bool, error) {
	configuredAddr = strings.TrimSpace(configuredAddr)
	if configuredAddr == "" {
		return nil, false, errors.New("Redis address is required")
	}
	if strings.Contains(configuredAddr, "://") {
		options, err := goredis.ParseURL(configuredAddr)
		if err != nil {
			return nil, false, fmt.Errorf("parse Redis address: %w", err)
		}
		if configuredPassword != "" {
			options.Password = configuredPassword
		}
		options.DB = database
		return options, strings.HasPrefix(configuredAddr, "rediss://"), nil
	}
	return &goredis.Options{
		Addr:     configuredAddr,
		Password: configuredPassword,
		DB:       database,
	}, false, nil
}

func (r *RealRedis) client(database int) (*goredis.Client, error) {
	if r == nil {
		return nil, errors.New("real Redis is not initialized")
	}
	options, _, err := realRedisOptions(r.Addr, r.Password, database)
	if err != nil {
		return nil, err
	}
	if r.TLS {
		options.TLSConfig = r.probe.Options().TLSConfig
	}
	return goredis.NewClient(options), nil
}

func (r *RealRedis) Ping(ctx context.Context, database int) error {
	client, err := r.client(database)
	if err != nil {
		return err
	}
	defer client.Close()
	return client.Ping(ctx).Err()
}

func (r *RealRedis) Set(
	ctx context.Context,
	database int,
	key string,
	value string,
	ttl time.Duration,
) error {
	client, err := r.client(database)
	if err != nil {
		return err
	}
	defer client.Close()
	return client.Set(ctx, key, value, ttl).Err()
}

func (r *RealRedis) Get(ctx context.Context, database int, key string) (string, error) {
	client, err := r.client(database)
	if err != nil {
		return "", err
	}
	defer client.Close()
	return client.Get(ctx, key).Result()
}

func (r *RealRedis) TTL(
	ctx context.Context,
	database int,
	key string,
) (time.Duration, error) {
	client, err := r.client(database)
	if err != nil {
		return 0, err
	}
	defer client.Close()
	return client.TTL(ctx, key).Result()
}

func (r *RealRedis) Exists(ctx context.Context, database int, key string) (bool, error) {
	client, err := r.client(database)
	if err != nil {
		return false, err
	}
	defer client.Close()
	count, err := client.Exists(ctx, key).Result()
	return count > 0, err
}

func (r *RealRedis) FlushDBs(ctx context.Context, databases ...int) error {
	unique := make(map[int]struct{}, len(databases))
	for _, database := range databases {
		unique[database] = struct{}{}
	}
	sorted := make([]int, 0, len(unique))
	for database := range unique {
		sorted = append(sorted, database)
	}
	sort.Ints(sorted)
	var flushErr error
	for _, database := range sorted {
		client, err := r.client(database)
		if err != nil {
			flushErr = errors.Join(flushErr, err)
			continue
		}
		err = client.FlushDB(ctx).Err()
		closeErr := client.Close()
		if err != nil {
			flushErr = errors.Join(flushErr, fmt.Errorf("flush Redis DB %d: %w", database, err))
		}
		if closeErr != nil {
			flushErr = errors.Join(flushErr, fmt.Errorf("close Redis DB %d client: %w", database, closeErr))
		}
	}
	return flushErr
}

func (r *RealRedis) Close(ctx context.Context) error {
	if r == nil {
		return nil
	}
	var closeErr error
	if r.probe != nil {
		if err := r.probe.Close(); err != nil {
			closeErr = errors.Join(closeErr, fmt.Errorf("close Redis probe client: %w", err))
		}
	}
	if r.container != nil {
		if err := r.container.Terminate(ctx); err != nil {
			closeErr = errors.Join(closeErr, fmt.Errorf("terminate Redis testcontainer: %w", err))
		}
	}
	if err := r.process.close(ctx); err != nil {
		closeErr = errors.Join(closeErr, err)
	}
	return closeErr
}
