package testinfra

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/testcontainers/testcontainers-go"
)

const containerProbeTimeout = 3 * time.Second

type DependencySource string

const (
	DependencySourceExternal  DependencySource = "external"
	DependencySourceContainer DependencySource = "testcontainer"
	DependencySourceNative    DependencySource = "native-process"
)

var (
	dockerProbeOnce sync.Once
	dockerProbeErr  error
	databaseCounter atomic.Uint64
)

func UniqueDatabaseName(prefix string) string {
	var builder strings.Builder
	for _, character := range strings.TrimSpace(prefix) {
		switch {
		case character >= 'a' && character <= 'z':
			builder.WriteRune(character)
		case character >= 'A' && character <= 'Z':
			builder.WriteRune(character + ('a' - 'A'))
		case character >= '0' && character <= '9':
			builder.WriteRune(character)
		default:
			builder.WriteByte('_')
		}
	}
	normalized := strings.Trim(builder.String(), "_")
	if normalized == "" {
		normalized = "api_integration"
	}
	if len(normalized) > 32 {
		normalized = normalized[:32]
	}
	return fmt.Sprintf("%s_%d_%d", normalized, os.Getpid(), databaseCounter.Add(1))
}

func containerRuntimeAvailable() error {
	if disabled, _ := strconv.ParseBool(strings.TrimSpace(os.Getenv("TESTINFRA_DISABLE_CONTAINERS"))); disabled {
		return fmt.Errorf("containers disabled by TESTINFRA_DISABLE_CONTAINERS")
	}
	ConfigureLocalContainerRuntime()
	dockerProbeOnce.Do(func() {
		ctx, cancel := context.WithTimeout(context.Background(), containerProbeTimeout)
		defer cancel()
		defer func() {
			if recovered := recover(); recovered != nil {
				dockerProbeErr = fmt.Errorf("container runtime probe panic: %v", recovered)
			}
		}()

		client, err := testcontainers.NewDockerClientWithOpts(ctx)
		if err != nil {
			dockerProbeErr = fmt.Errorf("create Docker client: %w", err)
			return
		}
		defer client.Close()
		if _, err := client.Ping(ctx); err != nil {
			dockerProbeErr = fmt.Errorf("ping Docker daemon: %w", err)
		}
	})
	return dockerProbeErr
}

// ConfigureLocalContainerRuntime discovers the supported local Docker sockets
// before a service integration suite starts a testcontainer.
func ConfigureLocalContainerRuntime() {
	if strings.TrimSpace(os.Getenv("DOCKER_HOST")) != "" {
		return
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return
	}
	for _, socketPath := range []string{
		filepath.Join(home, ".colima", "default", "docker.sock"),
		filepath.Join(home, ".orbstack", "run", "docker.sock"),
		filepath.Join(home, ".docker", "run", "docker.sock"),
	} {
		info, statErr := os.Stat(socketPath)
		if statErr != nil || info.Mode()&os.ModeSocket == 0 {
			continue
		}
		_ = os.Setenv("DOCKER_HOST", "unix://"+socketPath)
		if strings.TrimSpace(os.Getenv("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE")) == "" {
			_ = os.Setenv("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "/var/run/docker.sock")
		}
		return
	}
}
