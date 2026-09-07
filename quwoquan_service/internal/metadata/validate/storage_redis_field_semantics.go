package validate

import (
	"io/fs"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/storagecontract"
)

const (
	redisFenceTokenValue     = "token_value"
	redisFenceCurrentCounter = "current_counter"
)

// storageRedisFieldSemanticsIssues 补齐 storage.schema.json 已声明但此前未被校验的
// redis_cache 跨字段语义：
//
//   - fence 必须成对：runtime/redis AcquireLeaseFenceAtomic 用一个 Lua 同时推进
//     current_counter 并写入 token_value，只有一半的声明无法证明原子性；两者还必须
//     共享同一 hash_tag 才能落入 Redis Cluster 同一 slot。
//   - durability: ephemeral 且 eviction_consequence: fail_closed 的键会在 eviction
//     或重启后让依赖它的路径拒绝服务，因此声明位必须说明恢复来源；schema 没有
//     结构化的恢复字段，故要求 description 明确写出「恢复」/recover 语义。
func storageRedisFieldSemanticsIssues(metadataDir string) ([]Issue, error) {
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
			// 形状错误由 closed schema / typed reader 校验拥有。
			return nil
		}
		sourcePath := relativeMetadataPath(metadataDir, path)

		fenceByRole := map[string][]int{}
		for index, cache := range document.RedisCache {
			if fence := strings.TrimSpace(cache.Fence); fence != "" {
				fenceByRole[fence] = append(fenceByRole[fence], index)
			}
			if strings.TrimSpace(cache.Durability) == "ephemeral" &&
				strings.TrimSpace(cache.EvictionConsequence) == "fail_closed" &&
				!describesRecoverySource(cache.Description) {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.REDIS_RECOVERY_SOURCE_REQUIRED",
					sourcePath,
					"redis_cache[%d] key %q is durability=ephemeral with eviction_consequence=fail_closed and must state its recovery source in description (恢复 / recover)",
					index, cache.Key,
				))
			}
		}
		if len(fenceByRole) == 0 {
			return nil
		}
		tokens := fenceByRole[redisFenceTokenValue]
		counters := fenceByRole[redisFenceCurrentCounter]
		if len(tokens) == 0 || len(counters) == 0 {
			roles := make([]string, 0, len(fenceByRole))
			for role := range fenceByRole {
				roles = append(roles, role)
			}
			sort.Strings(roles)
			issues = append(issues, issue(
				"CONTRACT.STORAGE.REDIS_FENCE_PAIR_INCOMPLETE",
				sourcePath,
				"redis_cache declares fence %s but a fence needs both token_value and current_counter keys",
				strings.Join(roles, ", "),
			))
			return nil
		}
		hashTags := map[string]struct{}{}
		for _, indexes := range [][]int{tokens, counters} {
			for _, index := range indexes {
				hashTags[strings.TrimSpace(document.RedisCache[index].HashTag)] = struct{}{}
			}
		}
		if _, empty := hashTags[""]; empty || len(hashTags) != 1 {
			tags := make([]string, 0, len(hashTags))
			for tag := range hashTags {
				tags = append(tags, tag)
			}
			sort.Strings(tags)
			issues = append(issues, issue(
				"CONTRACT.STORAGE.REDIS_FENCE_PAIR_INCOMPLETE",
				sourcePath,
				"fence token_value and current_counter keys must share one non-empty hash_tag, got %q",
				strings.Join(tags, "\", \""),
			))
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	sortIssues(issues)
	return issues, nil
}

func describesRecoverySource(description string) bool {
	text := strings.ToLower(strings.TrimSpace(description))
	if text == "" {
		return false
	}
	return strings.Contains(text, "恢复") || strings.Contains(text, "recover")
}
