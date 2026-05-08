package application

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"gopkg.in/yaml.v3"
)

type ShardDirectoryEntry struct {
	Prefix        string `yaml:"prefix"`
	PhysicalShard string `yaml:"physical_shard"`
}

type ShardDirectory struct {
	Version              int                   `yaml:"version"`
	RuleVersion          string                `yaml:"rule_version"`
	SlotCount            int                   `yaml:"slot_count"`
	HashFn               string                `yaml:"hash_fn"`
	DefaultPhysicalShard string                `yaml:"default_physical_shard"`
	Entries              []ShardDirectoryEntry `yaml:"entries"`
}

var shardDirectoryPrefixPattern = regexp.MustCompile(`^[0-9a-f]*$`)

const shardDirectoryMetadataRelativePath = "contracts/metadata/user/user_profile/shard_directory.yaml"

func LoadShardDirectory(path string) (*ShardDirectory, error) {
	contents, err := os.ReadFile(filepath.Clean(path))
	if err != nil {
		return nil, fmt.Errorf("read shard directory: %w", err)
	}
	var directory ShardDirectory
	if err := yaml.Unmarshal(contents, &directory); err != nil {
		return nil, fmt.Errorf("decode shard directory: %w", err)
	}
	if err := directory.Validate(); err != nil {
		return nil, err
	}
	return &directory, nil
}

func LoadDefaultShardDirectory() (*ShardDirectory, error) {
	path, err := ResolveDefaultShardDirectoryPath()
	if err != nil {
		return nil, err
	}
	return LoadShardDirectory(path)
}

func ResolveDefaultShardDirectoryPath() (string, error) {
	candidates := []string{
		shardDirectoryMetadataRelativePath,
		filepath.Join("..", shardDirectoryMetadataRelativePath),
		filepath.Join("..", "..", shardDirectoryMetadataRelativePath),
		filepath.Join("..", "..", "..", shardDirectoryMetadataRelativePath),
		filepath.Join("..", "..", "..", "..", shardDirectoryMetadataRelativePath),
		filepath.Join("..", "..", "..", "..", "..", shardDirectoryMetadataRelativePath),
	}
	for _, candidate := range candidates {
		cleaned := filepath.Clean(candidate)
		if _, err := os.Stat(cleaned); err == nil {
			return cleaned, nil
		}
	}
	wd, _ := os.Getwd()
	return "", fmt.Errorf("resolve shard directory metadata path from cwd %q", wd)
}

func (d *ShardDirectory) Validate() error {
	if d == nil {
		return fmt.Errorf("shard directory is nil")
	}
	if d.Version != 1 {
		return fmt.Errorf("unsupported shard directory version: %d", d.Version)
	}
	if strings.TrimSpace(d.RuleVersion) != identityRuleVersion {
		return fmt.Errorf("unexpected shard rule version: %s", d.RuleVersion)
	}
	if d.SlotCount != identitySlotCount {
		return fmt.Errorf("unexpected slot_count: %d", d.SlotCount)
	}
	if strings.TrimSpace(strings.ToLower(d.HashFn)) != identityHashFunction {
		return fmt.Errorf("unexpected hash_fn: %s", d.HashFn)
	}
	if strings.TrimSpace(d.DefaultPhysicalShard) == "" {
		return fmt.Errorf("default_physical_shard is required")
	}
	seen := make(map[string]struct{}, len(d.Entries))
	for _, entry := range d.Entries {
		prefix := normalizeShardPrefix(entry.Prefix)
		if !shardDirectoryPrefixPattern.MatchString(prefix) {
			return fmt.Errorf("invalid shard prefix: %s", entry.Prefix)
		}
		if strings.TrimSpace(entry.PhysicalShard) == "" {
			return fmt.Errorf("physical_shard is required for prefix %q", prefix)
		}
		if _, exists := seen[prefix]; exists {
			return fmt.Errorf("duplicate shard prefix: %s", prefix)
		}
		seen[prefix] = struct{}{}
	}
	return nil
}

func (d *ShardDirectory) ResolvePhysicalShardByPrefix(routeKey string) string {
	if d == nil {
		return ""
	}
	normalizedKey := normalizeShardPrefix(routeKey)
	longestPrefix := ""
	physicalShard := strings.TrimSpace(d.DefaultPhysicalShard)
	for _, entry := range d.Entries {
		prefix := normalizeShardPrefix(entry.Prefix)
		if prefix == "" {
			continue
		}
		if strings.HasPrefix(normalizedKey, prefix) && len(prefix) > len(longestPrefix) {
			longestPrefix = prefix
			physicalShard = strings.TrimSpace(entry.PhysicalShard)
		}
	}
	return physicalShard
}

func (d *ShardDirectory) ResolvePhysicalShardForOwnerID(ownerID string) string {
	originCode, entropyBody, ok := parseOwnerIdentity(ownerID)
	if !ok {
		return strings.TrimSpace(d.DefaultPhysicalShard)
	}
	return d.ResolvePhysicalShardByPrefix(buildShardRoutingKey(originCode, entropyBody))
}

func parseOwnerIdentity(ownerID string) (originCode string, entropyBody string, ok bool) {
	parts := strings.Split(strings.TrimSpace(ownerID), "_")
	if len(parts) != 5 || parts[0] != "uo" {
		return "", "", false
	}
	if strings.TrimSpace(parts[1]) != identityRuleVersion {
		return "", "", false
	}
	originCode = strings.TrimSpace(parts[2])
	entropyBody = strings.TrimSpace(parts[4])
	if originCode == "" || entropyBody == "" {
		return "", "", false
	}
	return originCode, entropyBody, true
}

func normalizeShardPrefix(prefix string) string {
	return strings.ToLower(strings.TrimSpace(prefix))
}
