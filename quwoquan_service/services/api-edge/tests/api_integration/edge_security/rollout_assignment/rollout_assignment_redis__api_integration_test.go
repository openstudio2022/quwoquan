// spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-003
// readiness_case: production-rollout-assignment-api
package api_integration

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"testing"
	"time"

	redis "github.com/redis/go-redis/v9"

	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/redisstore"
)

func TestCandidateAssignmentUsesAtomicSetNXAndRetainedTTL(t *testing.T) {
	client := newRealRedisClient(t)
	t.Cleanup(func() { _ = client.Close() })
	store, err := redisstore.New(client)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	ttl := 30 * 24 * time.Hour
	if err := store.AssignCandidate(ctx, "campaign-1", "subject-digest", ttl); err != nil {
		t.Fatal(err)
	}
	if err := store.AssignCandidate(ctx, "campaign-1", "subject-digest", ttl); err != nil {
		t.Fatal(err)
	}
	candidate, err := store.IsCandidate(ctx, "campaign-1", "subject-digest")
	if err != nil {
		t.Fatal(err)
	}
	if !candidate {
		t.Fatal("candidate assignment was not retained")
	}
	got, err := client.TTL(ctx, "edge:rollout:{campaign-1}:subject-digest").Result()
	if err != nil {
		t.Fatal(err)
	}
	if got != ttl {
		t.Fatalf("assignment ttl=%s want=%s", got, ttl)
	}
}

func TestUnknownAssignmentRemainsUnassigned(t *testing.T) {
	client := newRealRedisClient(t)
	t.Cleanup(func() { _ = client.Close() })
	store, err := redisstore.New(client)
	if err != nil {
		t.Fatal(err)
	}
	candidate, err := store.IsCandidate(context.Background(), "campaign-1", "missing")
	if err != nil {
		t.Fatal(err)
	}
	if candidate {
		t.Fatal("missing assignment must not become candidate")
	}
}

func newRealRedisClient(t *testing.T) *redis.Client {
	t.Helper()
	binary, err := exec.LookPath("redis-server")
	if err != nil {
		t.Fatalf("redis-server is required for api_integration: %v", err)
	}
	directory, err := os.MkdirTemp(os.TempDir(), "qe-rollout-")
	if err != nil {
		t.Fatalf("create Redis temporary directory: %v", err)
	}
	socket := filepath.Join(directory, "r.sock")
	command := exec.Command(
		binary,
		"--port", "0",
		"--unixsocket", socket,
		"--unixsocketperm", "700",
		"--save", "",
		"--appendonly", "no",
	)
	var logs bytes.Buffer
	command.Stdout = &logs
	command.Stderr = &logs
	if err := command.Start(); err != nil {
		_ = os.RemoveAll(directory)
		t.Fatalf("start redis-server: %v", err)
	}
	var stopOnce sync.Once
	stop := func() {
		stopOnce.Do(func() {
			if command.Process != nil {
				_ = command.Process.Kill()
			}
			_ = command.Wait()
			_ = os.RemoveAll(directory)
		})
	}
	t.Cleanup(stop)

	client := redis.NewClient(&redis.Options{
		Network:      "unix",
		Addr:         socket,
		PoolSize:     1,
		DialTimeout:  100 * time.Millisecond,
		ReadTimeout:  100 * time.Millisecond,
		WriteTimeout: 100 * time.Millisecond,
	})
	deadline := time.Now().Add(3 * time.Second)
	for {
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		pingErr := client.Ping(ctx).Err()
		cancel()
		if pingErr == nil {
			return client
		}
		if time.Now().After(deadline) {
			_ = client.Close()
			stop()
			t.Fatalf("redis-server did not become ready: %s", logs.String())
		}
		time.Sleep(20 * time.Millisecond)
	}
}
