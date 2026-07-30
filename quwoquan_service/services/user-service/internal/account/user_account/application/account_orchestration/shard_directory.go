package application

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"gopkg.in/yaml.v3"

	useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"
)

type ShardDirectoryEntry struct {
	Prefix        string `yaml:"prefix"`
	PhysicalShard string `yaml:"physical_shard"`
}

type ShardDirectory struct {
	SlotCount            int                   `yaml:"slot_count"`
	HashFn               string                `yaml:"hash_fn"`
	DefaultPhysicalShard string                `yaml:"default_physical_shard"`
	Entries              []ShardDirectoryEntry `yaml:"entries"`
}

var shardDirectoryPrefixPattern = regexp.MustCompile(`^[0-9a-f]*$`)

const shardDirectoryServiceRelativePath = "contracts/account/user_account/shard_directory.yaml"

func LoadShardDirectory(path string) (*ShardDirectory, error) {
	contents, err := os.ReadFile(filepath.Clean(path))
	if err != nil {
		return nil, fmt.Errorf("read shard directory: %w", err)
	}
	var directory ShardDirectory
	decoder := yaml.NewDecoder(strings.NewReader(string(contents)))
	decoder.KnownFields(true)
	if err := decoder.Decode(&directory); err != nil {
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
	workingDirectory, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("resolve shard directory cwd: %w", err)
	}
	for directory := workingDirectory; ; directory = filepath.Dir(directory) {
		candidates := []string{
			filepath.Join(directory, shardDirectoryServiceRelativePath),
			filepath.Join(directory, "services", "user-service", shardDirectoryServiceRelativePath),
			filepath.Join(directory, "quwoquan_service", "services", "user-service", shardDirectoryServiceRelativePath),
		}
		for _, candidate := range candidates {
			if info, statErr := os.Stat(candidate); statErr == nil && !info.IsDir() {
				return filepath.Clean(candidate), nil
			}
		}
		parent := filepath.Dir(directory)
		if parent == directory {
			break
		}
	}
	return "", fmt.Errorf("resolve shard directory contract path from cwd %q", workingDirectory)
}

func (d *ShardDirectory) Validate() error {
	if d == nil {
		return fmt.Errorf("shard directory is nil")
	}
	if d.SlotCount != useridentity.SlotCount {
		return fmt.Errorf("unexpected slot_count: %d", d.SlotCount)
	}
	if strings.TrimSpace(strings.ToLower(d.HashFn)) != useridentity.HashFunction {
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

func (d *ShardDirectory) ResolvePhysicalShardForOwnerID(ownerID string) (string, error) {
	parsed, err := useridentity.ParseOwnerID(ownerID)
	if err != nil {
		return "", fmt.Errorf("parse owner identity for shard routing: %w", err)
	}
	return d.ResolvePhysicalShardByPrefix(parsed.RoutingKey()), nil
}

func normalizeShardPrefix(prefix string) string {
	return strings.ToLower(strings.TrimSpace(prefix))
}
