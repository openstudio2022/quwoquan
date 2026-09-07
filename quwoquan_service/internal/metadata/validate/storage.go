package validate

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
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

func storageRedisAtomicKeyIssues(metadataDir string) ([]Issue, error) {
	var issues []Issue
	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || entry.Name() != "storage.yaml" {
			return nil
		}
		document, loadErr := storagecontract.LoadOptional(path)
		if loadErr != nil || document == nil {
			return loadErr
		}
		sourcePath := relativeMetadataPath(metadataDir, path)
		declared := make(map[string]int, len(document.RedisCache))
		for index, cache := range document.RedisCache {
			declared[cache.Key] = index
		}

		atomicDeclarationRequired := make(map[int]bool)
		for index, cache := range document.RedisCache {
			if strings.TrimSpace(cache.CreateOperation) != "" ||
				strings.TrimSpace(cache.QuotaIndex) != "" || strings.TrimSpace(cache.QuotaMetadata) != "" {
				atomicDeclarationRequired[index] = true
			}
			for _, quotaKey := range []string{cache.QuotaIndex, cache.QuotaMetadata} {
				if participantIndex, exists := declared[quotaKey]; quotaKey != "" && exists {
					atomicDeclarationRequired[participantIndex] = true
				}
			}
		}

		for index, cache := range document.RedisCache {
			prefix := strings.TrimSpace(cache.KeyPrefix)
			if prefix != "" && !strings.HasPrefix(cache.Key, prefix) {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.REDIS_KEY_PREFIX_MISMATCH",
					sourcePath,
					"redis_cache[%d] key %q does not start with key_prefix %q",
					index, cache.Key, prefix,
				))
			}

			if atomicDeclarationRequired[index] &&
				(len(cache.AtomicKeys) == 0 || strings.TrimSpace(cache.HashTag) == "") {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.REDIS_ATOMIC_DECLARATION_REQUIRED",
					sourcePath,
					"redis_cache[%d] key %q participates in create_operation or quota keys and must declare atomic_keys and hash_tag",
					index, cache.Key,
				))
			}
			if cache.QuotaIndex != "" {
				if _, exists := declared[cache.QuotaIndex]; !exists {
					issues = append(issues, issue(
						"CONTRACT.STORAGE.REDIS_QUOTA_INDEX_UNKNOWN",
						sourcePath,
						"redis_cache[%d] quota_index %q is not declared by this object",
						index, cache.QuotaIndex,
					))
				}
			}
			if cache.QuotaMetadata != "" {
				if _, exists := declared[cache.QuotaMetadata]; !exists {
					issues = append(issues, issue(
						"CONTRACT.STORAGE.REDIS_QUOTA_METADATA_UNKNOWN",
						sourcePath,
						"redis_cache[%d] quota_metadata %q is not declared by this object",
						index, cache.QuotaMetadata,
					))
				}
			}

			hasQuotaMechanism := cache.QuotaIndex != "" || cache.QuotaMetadata != ""
			if hasQuotaMechanism && (cache.QuotaIndex == "" || cache.QuotaMetadata == "") {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.REDIS_QUOTA_REFERENCES_REQUIRED",
					sourcePath,
					"redis_cache[%d] key %q must declare both quota_index and quota_metadata",
					index, cache.Key,
				))
			}
			if cache.QuotaIndex != "" && cache.QuotaMetadata != "" {
				expected := []string{cache.Key, cache.QuotaIndex, cache.QuotaMetadata}
				for _, participantKey := range expected {
					participantIndex, exists := declared[participantKey]
					if !exists {
						continue
					}
					participant := document.RedisCache[participantIndex]
					if len(participant.AtomicKeys) != 0 && !sameStringSet(participant.AtomicKeys, expected) {
						issues = append(issues, issue(
							"CONTRACT.STORAGE.REDIS_ATOMIC_SET_MISMATCH",
							sourcePath,
							"redis_cache[%d] quota participant %q must declare exactly the value, quota_index, and quota_metadata atomic_keys set",
							participantIndex, participantKey,
						))
					}
					if strings.TrimSpace(participant.HashTag) != strings.TrimSpace(cache.HashTag) {
						issues = append(issues, issue(
							"CONTRACT.STORAGE.REDIS_ATOMIC_PARTICIPANT_HASH_TAG_MISMATCH",
							sourcePath,
							"redis_cache[%d] quota participant %q declares hash_tag %q instead of %q",
							participantIndex, participantKey, participant.HashTag, cache.HashTag,
						))
					}
				}
			}

			if len(cache.AtomicKeys) == 0 {
				continue
			}
			if _, present := slicesBinarySearch(cache.AtomicKeys, cache.Key); !present {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.REDIS_ATOMIC_SELF_MISSING",
					sourcePath,
					"redis_cache[%d] key %q is missing from atomic_keys",
					index, cache.Key,
				))
			}
			for _, atomicKey := range cache.AtomicKeys {
				participantIndex, exists := declared[atomicKey]
				if !exists {
					issues = append(issues, issue(
						"CONTRACT.STORAGE.REDIS_ATOMIC_KEY_UNKNOWN",
						sourcePath,
						"redis_cache[%d] atomic key %q is not declared by this object",
						index, atomicKey,
					))
				} else {
					participant := document.RedisCache[participantIndex]
					if !sameStringSet(cache.AtomicKeys, participant.AtomicKeys) {
						issues = append(issues, issue(
							"CONTRACT.STORAGE.REDIS_ATOMIC_SET_MISMATCH",
							sourcePath,
							"redis_cache[%d] atomic participant %q must declare the same atomic_keys closed set",
							index, atomicKey,
						))
					}
					if strings.TrimSpace(participant.HashTag) != strings.TrimSpace(cache.HashTag) {
						issues = append(issues, issue(
							"CONTRACT.STORAGE.REDIS_ATOMIC_PARTICIPANT_HASH_TAG_MISMATCH",
							sourcePath,
							"redis_cache[%d] atomic participant %q declares hash_tag %q instead of %q",
							index, atomicKey, participant.HashTag, cache.HashTag,
						))
					}
				}
				if cache.HashTag == "" || redisClusterHashTag(atomicKey) != cache.HashTag {
					issues = append(issues, issue(
						"CONTRACT.STORAGE.REDIS_ATOMIC_HASH_TAG_MISMATCH",
						sourcePath,
						"redis_cache[%d] atomic key %q does not share hash_tag %q",
						index, atomicKey, cache.HashTag,
					))
				}
			}
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	sortIssues(issues)
	return issues, nil
}

// redisClusterHashTag implements Redis Cluster's key hash-tag rule: only the
// first non-empty {...} pair participates in slot selection. A later matching
// pair cannot repair an earlier non-empty tag.
func redisClusterHashTag(key string) string {
	for searchFrom := 0; searchFrom < len(key); {
		openOffset := strings.IndexByte(key[searchFrom:], '{')
		if openOffset < 0 {
			return ""
		}
		open := searchFrom + openOffset
		closeOffset := strings.IndexByte(key[open+1:], '}')
		if closeOffset < 0 {
			return ""
		}
		close := open + 1 + closeOffset
		if close > open+1 {
			return key[open+1 : close]
		}
		searchFrom = close + 1
	}
	return ""
}

func slicesBinarySearch(values []string, target string) (int, bool) {
	for index, value := range values {
		if value == target {
			return index, true
		}
	}
	return 0, false
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

// storageResourceIdentityIssues proves that authored local names produce one
// collision-free logical identity. A contract view resolves each file through
// its immutable provenance so service identity is not guessed from domain.
// Operation/projection-to-adapter consistency remains object-owned conformance:
// metadata has no unambiguous cross-file resource reference and this validator
// must not invent a central registry.
func storageResourceIdentityIssues(metadataDir string) ([]Issue, error) {
	sourcePathFor, err := storageResourceSourcePathResolver(metadataDir)
	if err != nil {
		return nil, err
	}
	return storageResourceIdentityIssuesWithSource(metadataDir, sourcePathFor)
}

func storageResourceIdentityIssuesWithSource(
	metadataDir string,
	sourcePathFor func(string) (string, error),
) ([]Issue, error) {
	identities := map[string]string{}
	var issues []Issue
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
		if document == nil || len(document.Resources) == 0 {
			return nil
		}
		sourcePath, sourceErr := sourcePathFor(path)
		if sourceErr != nil {
			return sourceErr
		}
		names := make([]string, 0, len(document.Resources))
		for name := range document.Resources {
			names = append(names, name)
		}
		sort.Strings(names)
		for _, name := range names {
			identity, identityErr := ast.DerivedResourceIdentity(sourcePath, name)
			if identityErr != nil {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.RESOURCE_IDENTITY_INVALID", sourcePath, "%v", identityErr,
				))
				continue
			}
			if previous, exists := identities[identity]; exists {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.RESOURCE_IDENTITY_COLLISION", sourcePath,
					"resource %q derives identity %q already owned by %s", name, identity, previous,
				))
				continue
			}
			identities[identity] = sourcePath + "#resources." + name
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	sortIssues(issues)
	return issues, nil
}

type storageResourceProvenance struct {
	Files []struct {
		Path        string   `json:"path"`
		SourcePaths []string `json:"sourcePaths"`
	} `json:"files"`
}

func storageResourceSourcePathResolver(
	metadataDir string,
) (func(string) (string, error), error) {
	manifestPath := filepath.Join(metadataDir, ".contract-view-provenance")
	payload, err := os.ReadFile(manifestPath)
	if os.IsNotExist(err) {
		return func(path string) (string, error) {
			return relativeMetadataPath(metadataDir, path), nil
		}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read storage resource provenance: %w", err)
	}
	var provenance storageResourceProvenance
	if err := json.Unmarshal(payload, &provenance); err != nil {
		return nil, fmt.Errorf("decode storage resource provenance: %w", err)
	}
	sources := make(map[string]string, len(provenance.Files))
	for _, file := range provenance.Files {
		if len(file.SourcePaths) == 1 {
			sources[filepath.ToSlash(filepath.Clean(file.Path))] = filepath.ToSlash(filepath.Clean(file.SourcePaths[0]))
		}
	}
	return func(path string) (string, error) {
		relative := relativeMetadataPath(metadataDir, path)
		source, exists := sources[relative]
		if !exists {
			return "", fmt.Errorf("contract view provenance has no unique canonical source for %q", relative)
		}
		return source, nil
	}, nil
}
