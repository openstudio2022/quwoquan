// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-redis/spec.md#sit-001
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-032
package api_integration

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	goredis "github.com/redis/go-redis/v9"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/infrastructure/redisstore"
)

func TestLeaseFenceRealRedisConcurrentAcquireAlwaysRejectsOldRenew(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	realRedis, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("lease fence api_integration requires real standalone Redis: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cleanupCancel()
		_ = realRedis.Close(cleanupCtx)
	})
	if err := realRedis.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush Redis: %v", err)
	}
	client := newLeaseFenceTestClient(t, rtredis.SceneConfig{
		Mode: "standalone", Addr: realRedis.Addr, Password: realRedis.Password, DB: 0, TLS: realRedis.TLS,
	})
	store := redisstore.NewLeaseStore(client)
	identity := application.TrustedIdentity{
		AccountID: "account-lease-race", PersonaID: "persona-lease-race", DeviceID: "device-lease-race",
	}

	for iteration := 0; iteration < 64; iteration++ {
		oldConnection := fmt.Sprintf("old-%03d", iteration)
		newConnection := fmt.Sprintf("new-%03d", iteration)
		oldFence, acquireErr := store.Acquire(ctx, identity, oldConnection, 2*time.Minute)
		if acquireErr != nil {
			t.Fatalf("iteration %d acquire old: %v", iteration, acquireErr)
		}
		ready := make(chan struct{})
		start := make(chan struct{})
		result := make(chan error, 2)
		var newFence int64
		go func() {
			ready <- struct{}{}
			<-start
			fence, currentErr := store.Acquire(ctx, identity, newConnection, 2*time.Minute)
			newFence = fence
			result <- currentErr
		}()
		go func() {
			ready <- struct{}{}
			<-start
			result <- store.Renew(ctx, identity, oldConnection, oldFence, 2*time.Minute)
		}()
		<-ready
		<-ready
		close(start)
		for range 2 {
			if raceErr := <-result; raceErr != nil &&
				!errors.Is(raceErr, application.ErrLeaseFenced) {
				t.Fatalf("iteration %d race: %v", iteration, raceErr)
			}
		}
		if newFence <= oldFence {
			t.Fatalf("iteration %d fence did not advance: old=%d new=%d", iteration, oldFence, newFence)
		}
		if renewErr := store.Renew(
			ctx, identity, oldConnection, oldFence, 2*time.Minute,
		); !errors.Is(renewErr, application.ErrLeaseFenced) {
			t.Fatalf("iteration %d old renew after acquire=%v, want ErrLeaseFenced", iteration, renewErr)
		}
		if releaseErr := store.Release(
			ctx, identity, newConnection, oldFence,
		); !errors.Is(releaseErr, application.ErrLeaseFenced) {
			t.Fatalf("iteration %d old release=%v, want ErrLeaseFenced", iteration, releaseErr)
		}
		if renewErr := store.Renew(
			ctx, identity, newConnection, newFence, 2*time.Minute,
		); renewErr != nil {
			t.Fatalf("iteration %d old release removed current lease: %v", iteration, renewErr)
		}
	}
}

func TestLeaseFenceRealRedisAuthorityLossNeverRevalidatesOldLease(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	realRedis, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("lease fence api_integration requires real standalone Redis: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cleanupCancel()
		_ = realRedis.Close(cleanupCtx)
	})
	if err := realRedis.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush Redis: %v", err)
	}
	client := newLeaseFenceTestClient(t, rtredis.SceneConfig{
		Mode: "standalone", Addr: realRedis.Addr, Password: realRedis.Password, DB: 0, TLS: realRedis.TLS,
	})
	store := redisstore.NewLeaseStore(client)
	identity := application.TrustedIdentity{
		AccountID: "account-authority-loss",
		PersonaID: "persona-authority-loss",
		DeviceID:  "device-authority-loss",
	}
	oldFence, err := store.Acquire(ctx, identity, "connection-old", 2*time.Minute)
	if err != nil {
		t.Fatalf("acquire old lease: %v", err)
	}
	raw := goredis.NewClient(&goredis.Options{
		Addr: realRedis.Addr, Password: realRedis.Password, DB: 0,
	})
	t.Cleanup(func() { _ = raw.Close() })
	keys, _, err := raw.Scan(ctx, 0, "rt:conn:*", 8).Result()
	if err != nil || len(keys) != 2 {
		t.Fatalf("initial lease keys=%v err=%v, want fence+lease", keys, err)
	}
	var fenceKey string
	for _, key := range keys {
		if strings.HasPrefix(key, "rt:conn:fence:") {
			fenceKey = key
		}
	}
	if fenceKey == "" {
		t.Fatalf("fence key missing from %v", keys)
	}
	if ttl, ttlErr := raw.PTTL(ctx, fenceKey).Result(); ttlErr != nil || ttl != -1 {
		t.Fatalf("fence authority TTL=%v err=%v, want persistent -1ns", ttl, ttlErr)
	}
	if err := raw.Del(ctx, fenceKey).Err(); err != nil {
		t.Fatalf("delete fence authority: %v", err)
	}
	if renewErr := store.Renew(
		ctx, identity, "connection-old", oldFence, 2*time.Minute,
	); !errors.Is(renewErr, application.ErrLeaseExpired) {
		t.Fatalf("old renew after authority loss=%v, want ErrLeaseExpired", renewErr)
	}
	if _, err := store.Acquire(
		ctx, identity, "connection-old", 2*time.Minute,
	); err == nil || !strings.Contains(err.Error(), "authority missing") {
		t.Fatalf("same-key acquire after authority loss error=%v, want fail-closed", err)
	}
	for _, key := range keys {
		if strings.HasPrefix(key, "rt:conn:lease:") {
			if err := raw.Del(ctx, key).Err(); err != nil {
				t.Fatalf("expire old lease before recovery acquire: %v", err)
			}
		}
	}
	newFence, err := store.Acquire(ctx, identity, "connection-new", 2*time.Minute)
	if err != nil {
		t.Fatalf("acquire new key after simulated authority loss: %v", err)
	}
	if newFence != oldFence {
		t.Fatalf("loss simulation expected numeric reuse old=%d new=%d", oldFence, newFence)
	}
	if renewErr := store.Renew(
		ctx, identity, "connection-old", oldFence, 2*time.Minute,
	); !errors.Is(renewErr, application.ErrLeaseExpired) {
		t.Fatalf("old expired lease became valid after token reuse: %v", renewErr)
	}
	if releaseErr := store.Release(
		ctx, identity, "connection-old", oldFence,
	); !errors.Is(releaseErr, application.ErrLeaseExpired) {
		t.Fatalf("old expired release became valid after token reuse: %v", releaseErr)
	}
	if renewErr := store.Renew(
		ctx, identity, "connection-new", newFence, 2*time.Minute,
	); renewErr != nil {
		t.Fatalf("new lease rejected after old attempts: %v", renewErr)
	}
}

func TestLeaseFenceRealThreeNodeRedisClusterUsesOneSlotAndExecutesLua(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	cluster := startNativeRedisCluster(t, ctx)
	raw := goredis.NewClusterClient(&goredis.ClusterOptions{Addrs: cluster.addresses})
	t.Cleanup(func() { _ = raw.Close() })
	if err := raw.Ping(ctx).Err(); err != nil {
		t.Fatalf("ping real Redis Cluster: %v", err)
	}
	client := newLeaseFenceTestClient(t, rtredis.SceneConfig{Mode: "cluster", Addrs: cluster.addresses})
	store := redisstore.NewLeaseStore(client)
	identity := application.TrustedIdentity{
		AccountID: "account-cluster", PersonaID: "persona-cluster", DeviceID: "device-cluster",
	}
	fence, err := store.Acquire(ctx, identity, "connection-cluster", time.Minute)
	if err != nil {
		t.Fatalf("cluster Acquire Lua: %v", err)
	}
	keys, err := scanClusterKeys(ctx, raw, "rt:conn:*")
	if err != nil {
		t.Fatalf("scan lease keys: %v", err)
	}
	if len(keys) != 2 {
		t.Fatalf("cluster lease key count=%d keys=%v, want fence+lease", len(keys), keys)
	}
	slots := map[int64]struct{}{}
	for _, key := range keys {
		slot, slotErr := raw.ClusterKeySlot(ctx, key).Result()
		if slotErr != nil {
			t.Fatalf("CLUSTER KEYSLOT %q: %v", key, slotErr)
		}
		slots[slot] = struct{}{}
		if strings.Contains(key, identity.PersonaID) || strings.Contains(key, identity.DeviceID) {
			t.Fatalf("lease key leaked raw identity: %q", key)
		}
	}
	if len(slots) != 1 {
		t.Fatalf("lease/fence slots=%v, want one", slots)
	}
	if err := store.Renew(ctx, identity, "connection-cluster", fence, time.Minute); err != nil {
		t.Fatalf("cluster Renew Lua: %v", err)
	}
	if err := store.Release(ctx, identity, "connection-cluster", fence); err != nil {
		t.Fatalf("cluster Release Lua: %v", err)
	}

	untagged := []string{
		strings.ReplaceAll(keys[0], "{", ""),
		strings.ReplaceAll(keys[1], "{", ""),
	}
	untagged[0] = strings.ReplaceAll(untagged[0], "}", "")
	untagged[1] = strings.ReplaceAll(untagged[1], "}", "")
	for suffix := 0; ; suffix++ {
		candidate := untagged[1] + strconv.Itoa(suffix)
		firstSlot, _ := raw.ClusterKeySlot(ctx, untagged[0]).Result()
		secondSlot, _ := raw.ClusterKeySlot(ctx, candidate).Result()
		if firstSlot != secondSlot {
			untagged[1] = candidate
			break
		}
	}
	evalErr := raw.Eval(
		ctx,
		"return {redis.call('GET', KEYS[1]), redis.call('GET', KEYS[2])}",
		untagged,
	).Err()
	if evalErr == nil || !strings.Contains(evalErr.Error(), "CROSSSLOT") {
		t.Fatalf("untagged EVAL error=%v, want real CROSSSLOT", evalErr)
	}
}

func newLeaseFenceTestClient(t *testing.T, scene rtredis.SceneConfig) rtredis.Client {
	t.Helper()
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{"realtime": scene}, DefaultScene: "realtime",
	})
	if err != nil {
		t.Fatalf("new Redis router: %v", err)
	}
	t.Cleanup(func() { _ = router.Close() })
	return router.Scene("realtime")
}

func scanClusterKeys(
	ctx context.Context,
	client *goredis.ClusterClient,
	pattern string,
) ([]string, error) {
	keys := map[string]struct{}{}
	var mu sync.Mutex
	err := client.ForEachMaster(ctx, func(ctx context.Context, node *goredis.Client) error {
		var cursor uint64
		for {
			current, next, scanErr := node.Scan(ctx, cursor, pattern, 32).Result()
			if scanErr != nil {
				return scanErr
			}
			mu.Lock()
			for _, key := range current {
				keys[key] = struct{}{}
			}
			mu.Unlock()
			if next == 0 {
				return nil
			}
			cursor = next
		}
	})
	if err != nil {
		return nil, err
	}
	result := make([]string, 0, len(keys))
	for key := range keys {
		result = append(result, key)
	}
	sort.Strings(result)
	return result, nil
}

type nativeRedisCluster struct {
	addresses []string
	commands  []*exec.Cmd
	logs      []*bytes.Buffer
	dirs      []string
}

func startNativeRedisCluster(t *testing.T, ctx context.Context) *nativeRedisCluster {
	t.Helper()
	serverBinary, err := exec.LookPath("redis-server")
	if err != nil {
		t.Fatalf("real three-node Redis Cluster requires redis-server: %v", err)
	}
	cliBinary, err := exec.LookPath("redis-cli")
	if err != nil {
		t.Fatalf("real three-node Redis Cluster requires redis-cli: %v", err)
	}
	runtime := &nativeRedisCluster{}
	t.Cleanup(func() {
		for _, command := range runtime.commands {
			if command.Process != nil {
				_ = command.Process.Kill()
			}
			_ = command.Wait()
		}
		for _, directory := range runtime.dirs {
			_ = os.RemoveAll(directory)
		}
	})
	ports := make([]int, 0, 3)
	for range 3 {
		port := reserveRedisClusterPort(t)
		ports = append(ports, port)
		directory, dirErr := os.MkdirTemp("", "qwq-realtime-cluster-*")
		if dirErr != nil {
			t.Fatalf("create Redis Cluster directory: %v", dirErr)
		}
		runtime.dirs = append(runtime.dirs, directory)
		address := "127.0.0.1:" + strconv.Itoa(port)
		runtime.addresses = append(runtime.addresses, address)
		logBuffer := &bytes.Buffer{}
		command := exec.CommandContext(
			ctx,
			serverBinary,
			"--bind", "127.0.0.1",
			"--port", strconv.Itoa(port),
			"--protected-mode", "no",
			"--cluster-enabled", "yes",
			"--cluster-port", strconv.Itoa(port+10_000),
			"--cluster-config-file", filepath.Join(directory, "nodes.conf"),
			"--cluster-node-timeout", "5000",
			"--appendonly", "no",
			"--save", "",
			"--dir", directory,
		)
		command.Stdout = logBuffer
		command.Stderr = logBuffer
		if startErr := command.Start(); startErr != nil {
			t.Fatalf("start Redis Cluster node %s: %v", address, startErr)
		}
		runtime.commands = append(runtime.commands, command)
		runtime.logs = append(runtime.logs, logBuffer)
	}
	for index, address := range runtime.addresses {
		waitForRedisClusterNode(t, ctx, address, runtime.commands[index], runtime.logs[index])
	}
	arguments := append([]string{"--cluster", "create"}, runtime.addresses...)
	arguments = append(arguments, "--cluster-replicas", "0", "--cluster-yes")
	output, err := exec.CommandContext(ctx, cliBinary, arguments...).CombinedOutput()
	if err != nil {
		t.Fatalf("create real Redis Cluster: %v\n%s", err, output)
	}
	deadline := time.Now().Add(30 * time.Second)
	probe := goredis.NewClusterClient(&goredis.ClusterOptions{Addrs: runtime.addresses})
	defer probe.Close()
	for {
		info, infoErr := probe.ClusterInfo(ctx).Result()
		if infoErr == nil && strings.Contains(info, "cluster_state:ok") {
			return runtime
		}
		if time.Now().After(deadline) {
			t.Fatalf("Redis Cluster did not become healthy: info=%q err=%v", info, infoErr)
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func reserveRedisClusterPort(t *testing.T) int {
	t.Helper()
	const (
		firstPort = 10_000
		portCount = 10_000
	)
	start := int(time.Now().UnixNano() % portCount)
	for offset := range portCount {
		port := firstPort + (start+offset)%portCount
		clientListener, clientErr := net.Listen("tcp", "127.0.0.1:"+strconv.Itoa(port))
		if clientErr != nil {
			continue
		}
		busListener, busErr := net.Listen("tcp", "127.0.0.1:"+strconv.Itoa(port+10_000))
		if busErr != nil {
			_ = clientListener.Close()
			continue
		}
		if closeErr := busListener.Close(); closeErr != nil {
			_ = clientListener.Close()
			t.Fatalf("release Redis Cluster bus port: %v", closeErr)
		}
		if closeErr := clientListener.Close(); closeErr != nil {
			t.Fatalf("release Redis Cluster client port: %v", closeErr)
		}
		return port
	}
	t.Fatal("reserve Redis Cluster client and bus ports: no available pair")
	return 0
}

func waitForRedisClusterNode(
	t *testing.T,
	ctx context.Context,
	address string,
	command *exec.Cmd,
	logs *bytes.Buffer,
) {
	t.Helper()
	deadline := time.Now().Add(10 * time.Second)
	for {
		if command.ProcessState != nil {
			t.Fatalf("Redis Cluster node %s exited: %s", address, logs.String())
		}
		probe := goredis.NewClient(&goredis.Options{Addr: address})
		pingErr := probe.Ping(ctx).Err()
		_ = probe.Close()
		if pingErr == nil {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("Redis Cluster node %s not ready: %v\n%s", address, pingErr, logs.String())
		}
		time.Sleep(20 * time.Millisecond)
	}
}
