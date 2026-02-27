package recommendation

import (
	"runtime"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
)

// ---------------------------------------------------------------------------
// Compile-time interface compliance
// ---------------------------------------------------------------------------

// These blank assignments fail at compile time if the adapter no longer
// satisfies the required interfaces — zero runtime overhead, instant feedback.
var (
	_ rtrec.RedisClient   = (*RedisClusterAdapter)(nil)
	_ rtrec.RedisPipeliner = (*RedisClusterAdapter)(nil)

	// Standalone adapter must still satisfy both interfaces too.
	_ rtrec.RedisClient   = (*RedisClientAdapter)(nil)
	_ rtrec.RedisPipeliner = (*RedisClientAdapter)(nil)
)

// ---------------------------------------------------------------------------
// DefaultClusterPoolConfig
// ---------------------------------------------------------------------------

func TestDefaultClusterPoolConfig_Values(t *testing.T) {
	cfg := DefaultClusterPoolConfig()
	cpus := runtime.GOMAXPROCS(0)

	if cfg.PoolSize != cpus*30 {
		t.Errorf("PoolSize: want %d (CPU×30), got %d", cpus*30, cfg.PoolSize)
	}
	if cfg.MinIdleConns != cpus*8 {
		t.Errorf("MinIdleConns: want %d (CPU×8), got %d", cpus*8, cfg.MinIdleConns)
	}
	if cfg.ReadTimeout != 100*time.Millisecond {
		t.Errorf("ReadTimeout: want 100ms, got %v", cfg.ReadTimeout)
	}
	if cfg.WriteTimeout != 100*time.Millisecond {
		t.Errorf("WriteTimeout: want 100ms, got %v", cfg.WriteTimeout)
	}
	if cfg.DialTimeout != 500*time.Millisecond {
		t.Errorf("DialTimeout: want 500ms, got %v", cfg.DialTimeout)
	}
}

// Cluster pool should be larger than standalone (more shards to connect to).
func TestDefaultClusterPoolConfig_LargerThanStandalone(t *testing.T) {
	cluster := DefaultClusterPoolConfig()
	standalone := DefaultRedisPoolConfig()

	if cluster.PoolSize <= standalone.PoolSize {
		t.Errorf("cluster PoolSize (%d) should exceed standalone PoolSize (%d)",
			cluster.PoolSize, standalone.PoolSize)
	}
	if cluster.MinIdleConns <= standalone.MinIdleConns {
		t.Errorf("cluster MinIdleConns (%d) should exceed standalone MinIdleConns (%d)",
			cluster.MinIdleConns, standalone.MinIdleConns)
	}
}

// ---------------------------------------------------------------------------
// DefaultRedisPoolConfig (standalone, regression guard)
// ---------------------------------------------------------------------------

func TestDefaultRedisPoolConfig_Values(t *testing.T) {
	cfg := DefaultRedisPoolConfig()
	cpus := runtime.GOMAXPROCS(0)

	if cfg.PoolSize != cpus*20 {
		t.Errorf("PoolSize: want %d (CPU×20), got %d", cpus*20, cfg.PoolSize)
	}
	if cfg.MinIdleConns != cpus*5 {
		t.Errorf("MinIdleConns: want %d (CPU×5), got %d", cpus*5, cfg.MinIdleConns)
	}
}
