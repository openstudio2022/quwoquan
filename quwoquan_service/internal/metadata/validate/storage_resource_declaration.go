package validate

import (
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/storagecontract"
)

// physicalStorageEngines 与 storage.schema.json#/$defs/physicalStorageEngine 同构：
// 只有这些 backend 值代表一个真实的物理引擎；service_resource /
// observability_log_sink / owner_named_readers 是宿主语义，其物理引擎由
// environment_backends 或 resources 给出。
var physicalStorageEngines = map[string]bool{
	"postgres":       true,
	"mongodb":        true,
	"elasticsearch":  true,
	"redis":          true,
	"object_storage": true,
}

// storagePhysicalEngines 从一份 storage.yaml 推导它实际触达的物理引擎闭集：
// backend（或非物理 backend 的 environment_backends）、redis_cache 块隐含的 redis、
// 以及 resources 已显式声明的引擎（Elasticsearch 查询投影、对象存储等）。
func storagePhysicalEngines(document ast.StorageDocument) map[string]bool {
	engines := map[string]bool{}
	backend := strings.TrimSpace(document.Backend)
	if physicalStorageEngines[backend] {
		engines[backend] = true
	} else {
		for _, environment := range document.EnvironmentBackends {
			if engine := strings.TrimSpace(environment.Backend); physicalStorageEngines[engine] {
				engines[engine] = true
			}
		}
	}
	if len(document.RedisCache) > 0 {
		engines["redis"] = true
	}
	for _, resource := range document.Resources {
		if engine := strings.TrimSpace(resource.Engine); physicalStorageEngines[engine] {
			engines[engine] = true
		}
	}
	return engines
}

// storageResourceDeclarationIssues 实施 DEC-032 的可判定规则：对象触达的物理引擎数
// 大于 1 时，必须在 resources 中逐引擎声明具名逻辑资源（含自身 backend 权威引擎），
// 否则跨引擎一致性、就绪与恢复语义没有可绑定的资源身份。单引擎对象不强制。
func storageResourceDeclarationIssues(metadataDir string) ([]Issue, error) {
	var issues []Issue
	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			name := entry.Name()
			if path != metadataDir && (name == ".git" || name == "test_fixtures" || strings.HasPrefix(name, "_")) {
				return filepath.SkipDir
			}
			return nil
		}
		if entry.Name() != "storage.yaml" {
			return nil
		}
		if _, statErr := os.Stat(filepath.Join(filepath.Dir(path), "object.yaml")); statErr != nil {
			return nil
		}
		document, loadErr := storagecontract.LoadOptional(path)
		if loadErr != nil || document == nil {
			// 形状错误由 closed schema / typed reader 校验拥有。
			return nil
		}
		engines := storagePhysicalEngines(*document)
		if len(engines) <= 1 {
			return nil
		}
		declared := map[string]bool{}
		for _, resource := range document.Resources {
			declared[strings.TrimSpace(resource.Engine)] = true
		}
		var missing []string
		for engine := range engines {
			if !declared[engine] {
				missing = append(missing, engine)
			}
		}
		if len(missing) == 0 {
			return nil
		}
		sort.Strings(missing)
		all := make([]string, 0, len(engines))
		for engine := range engines {
			all = append(all, engine)
		}
		sort.Strings(all)
		issues = append(issues, issue(
			"CONTRACT.STORAGE.RESOURCE_DECLARATION_REQUIRED",
			relativeMetadataPath(metadataDir, path),
			"object touches %d physical engines (%s) and must declare a named resource for each; missing: %s",
			len(engines), strings.Join(all, ", "), strings.Join(missing, ", "),
		))
		return nil
	})
	if err != nil {
		return nil, err
	}
	sortIssues(issues)
	return issues, nil
}
