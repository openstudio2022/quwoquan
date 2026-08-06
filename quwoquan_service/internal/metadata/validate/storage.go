package validate

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/storagecontract"

	"gopkg.in/yaml.v3"
)

type redisKeyspaceDocument struct {
	SceneRouting struct {
		Fallback string `yaml:"fallback"`
		Scenes   map[string]struct {
			KeyPrefixes []string `yaml:"key_prefixes"`
		} `yaml:"scenes"`
	} `yaml:"scene_routing"`
}

// storageRedisSceneIssues binds storage.yaml redis_cache[].scene to the one
// shared scene-routing vocabulary. A cache may omit scene and use ForKey's
// longest-prefix/fallback route, but an explicit scene must exist and must
// select the same route as its key.
func storageRedisSceneIssues(metadataDir string) ([]Issue, error) {
	type explicitCacheScene struct {
		sourcePath string
		index      int
		key        string
		scene      string
	}
	var caches []explicitCacheScene
	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || entry.Name() != "storage.yaml" {
			return nil
		}
		document, loadErr := storagecontract.LoadOptional(path)
		if loadErr != nil {
			return loadErr
		}
		if document == nil {
			return nil
		}
		sourcePath := relativeMetadataPath(metadataDir, path)
		for index, cache := range document.RedisCache {
			scene := strings.TrimSpace(cache.Scene)
			if scene == "" {
				continue
			}
			caches = append(caches, explicitCacheScene{
				sourcePath: sourcePath,
				index:      index,
				key:        cache.Key,
				scene:      scene,
			})
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	// Partial metadata fixtures that do not declare an explicit Redis scene do
	// not need to copy the shared keyspace document. The canonical repository
	// does declare explicit scenes, so its validation remains fail-closed when
	// the shared routing contract is absent or malformed.
	if len(caches) == 0 {
		return nil, nil
	}

	keyspacePath := filepath.Join(metadataDir, "_shared", "redis_keyspace.yaml")
	data, err := os.ReadFile(keyspacePath)
	if err != nil {
		return nil, fmt.Errorf("read Redis keyspace: %w", err)
	}
	var keyspace redisKeyspaceDocument
	if err := yaml.Unmarshal(data, &keyspace); err != nil {
		return nil, fmt.Errorf("decode Redis keyspace: %w", err)
	}
	if strings.TrimSpace(keyspace.SceneRouting.Fallback) == "" || len(keyspace.SceneRouting.Scenes) == 0 {
		return nil, fmt.Errorf("%s: scene_routing must declare fallback and scenes", keyspacePath)
	}

	var issues []Issue
	for _, cache := range caches {
		if _, exists := keyspace.SceneRouting.Scenes[cache.scene]; !exists {
			issues = append(issues, issue(
				"CONTRACT.STORAGE.REDIS_SCENE_UNKNOWN",
				cache.sourcePath,
				"redis_cache[%d] key %q declares unknown scene %q",
				cache.index, cache.key, cache.scene,
			))
			continue
		}
		routed := redisSceneForKey(cache.key, keyspace)
		if cache.scene != routed {
			issues = append(issues, issue(
				"CONTRACT.STORAGE.REDIS_SCENE_MISMATCH",
				cache.sourcePath,
				"redis_cache[%d] key %q declares scene %q but shared keyspace routes it to %q",
				cache.index, cache.key, cache.scene, routed,
			))
		}
	}
	sortIssues(issues)
	return issues, nil
}

func redisSceneForKey(key string, keyspace redisKeyspaceDocument) string {
	type candidate struct {
		scene  string
		prefix string
	}
	var candidates []candidate
	for scene, route := range keyspace.SceneRouting.Scenes {
		for _, prefix := range route.KeyPrefixes {
			if strings.HasPrefix(key, prefix) {
				candidates = append(candidates, candidate{scene: scene, prefix: prefix})
			}
		}
	}
	sort.Slice(candidates, func(i, j int) bool {
		if len(candidates[i].prefix) != len(candidates[j].prefix) {
			return len(candidates[i].prefix) > len(candidates[j].prefix)
		}
		return candidates[i].scene < candidates[j].scene
	})
	if len(candidates) == 0 {
		return strings.TrimSpace(keyspace.SceneRouting.Fallback)
	}
	return candidates[0].scene
}
