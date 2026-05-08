package application

import (
	"path/filepath"
	"testing"
)

func TestLoadShardDirectoryFromMetadata(t *testing.T) {
	path := filepath.Clean("../../../../contracts/metadata/user/user_profile/shard_directory.yaml")
	directory, err := LoadShardDirectory(path)
	if err != nil {
		t.Fatalf("load shard directory: %v", err)
	}
	if directory.SlotCount != identitySlotCount {
		t.Fatalf("expected slot_count=%d, got %d", identitySlotCount, directory.SlotCount)
	}
	if directory.HashFn != identityHashFunction {
		t.Fatalf("expected hash_fn=%s, got %s", identityHashFunction, directory.HashFn)
	}
	if directory.DefaultPhysicalShard == "" {
		t.Fatal("expected default physical shard")
	}
}

func TestShardDirectoryResolvePhysicalShardForOwnerID(t *testing.T) {
	directory := &ShardDirectory{
		Version:              1,
		RuleVersion:          identityRuleVersion,
		SlotCount:            identitySlotCount,
		HashFn:               identityHashFunction,
		DefaultPhysicalShard: "user-primary-a",
	}
	entropyBody := "01jtkp0j3n4jv7qg8w3g6h2k9m"
	routeKey := buildShardRoutingKey(originCodeAnonymousDevice, entropyBody)
	directory.Entries = []ShardDirectoryEntry{
		{Prefix: routeKey[:4], PhysicalShard: "user-primary-a"},
		{Prefix: routeKey[:5], PhysicalShard: "user-primary-b"},
	}
	if err := directory.Validate(); err != nil {
		t.Fatalf("validate shard directory: %v", err)
	}
	ownerID := "uo_01_ad_" + routeKey[:4] + "_" + entropyBody
	if got := directory.ResolvePhysicalShardForOwnerID(ownerID); got != "user-primary-b" {
		t.Fatalf("expected longest prefix shard user-primary-b, got %s", got)
	}
}

func TestShardDirectoryResolveFallsBackToDefault(t *testing.T) {
	directory := &ShardDirectory{
		Version:              1,
		RuleVersion:          identityRuleVersion,
		SlotCount:            identitySlotCount,
		HashFn:               identityHashFunction,
		DefaultPhysicalShard: "user-primary-a",
		Entries: []ShardDirectoryEntry{
			{Prefix: "01af1", PhysicalShard: "user-primary-b"},
		},
	}
	if got := directory.ResolvePhysicalShardForOwnerID("uo_01_ph_00aa_01jtkp0q6d2b8z1n5r4y7v3c0p"); got != "user-primary-a" {
		t.Fatalf("expected default shard user-primary-a, got %s", got)
	}
}
