package redis

import (
	goredis "github.com/redis/go-redis/v9"
	rtredis "quwoquan_service/runtime/redis"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-001.t1
func TestNamedACLForwardedToBothProviderTopologies(t *testing.T) {
	cfg := rtredis.SceneConfig{Mode: "standalone", Addr: "localhost:6379", Username: "named-owner", Password: "isolated-key"}
	standalone, err := newStandaloneClient(cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer standalone.Close()
	opts := standalone.(*client).raw.(*goredis.Client).Options()
	if opts.Username != cfg.Username || opts.Password != cfg.Password {
		t.Fatal("standalone credentials lost")
	}
	cfg.Mode = "cluster"
	cfg.Addrs = []string{"localhost:6379"}
	cluster, err := newClusterClient(cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer cluster.Close()
	clusterOpts := cluster.(*client).raw.(*goredis.ClusterClient).Options()
	if clusterOpts.Username != cfg.Username || clusterOpts.Password != cfg.Password {
		t.Fatal("cluster credentials lost")
	}
}
