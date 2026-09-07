package validate

import (
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/storagecontract"

	"gopkg.in/yaml.v3"
)

// elasticsearchProjectionPolicyKeys 是 Elasticsearch 查询投影的 consistency_policy
// 必须给出的最小可判定闭集：没有 source_version_field / apply_mode 就无法证明写入
// 走的是 sourceVersion 原子条件写；没有 delete_mode 就无法证明删除是带版本
// tombstone；没有 rebuild_strategy 就无法证明重建不会把旧文档写回读别名
// （search-provider-routing DEC-002 / system-architecture DEC-032）。
var elasticsearchProjectionPolicyKeys = []string{
	"source_version_field",
	"apply_mode",
	"delete_mode",
	"rebuild_strategy",
}

// projectionConsistencyPolicyIssues 要求：对象 storage.yaml 的 resources 中一旦声明
// engine: elasticsearch 且 role: query_projection，该对象 projections/ 下至少一个
// read_model 文档必须声明完整的 consistency_policy。这里只判定「是否声明」；
// 每个字段的取值闭集由 projection.schema.json 拥有，不在此复制第二套枚举。
func projectionConsistencyPolicyIssues(metadataDir string) ([]Issue, error) {
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
		objectDir := filepath.Dir(path)
		if _, statErr := os.Stat(filepath.Join(objectDir, "object.yaml")); statErr != nil {
			return nil
		}
		document, loadErr := storagecontract.LoadOptional(path)
		if loadErr != nil || document == nil {
			// 形状错误由 closed schema / typed reader 校验拥有。
			return nil
		}
		if !declaresElasticsearchQueryProjection(document.Resources) {
			return nil
		}
		sourcePath := relativeMetadataPath(metadataDir, path)
		readModels, incomplete, scanErr := elasticsearchProjectionPolicyCoverage(objectDir)
		if scanErr != nil {
			return scanErr
		}
		if len(readModels) > 0 {
			return nil
		}
		if len(incomplete) == 0 {
			issues = append(issues, issue(
				"CONTRACT.PROJECTION.CONSISTENCY_POLICY_REQUIRED",
				sourcePath,
				"storage resources declare an elasticsearch query_projection but no projections/*.yaml read_model declares consistency_policy (%s)",
				strings.Join(elasticsearchProjectionPolicyKeys, ", "),
			))
			return nil
		}
		sort.Strings(incomplete)
		issues = append(issues, issue(
			"CONTRACT.PROJECTION.CONSISTENCY_POLICY_REQUIRED",
			sourcePath,
			"storage resources declare an elasticsearch query_projection but no read_model declares a complete consistency_policy (%s); incomplete: %s",
			strings.Join(elasticsearchProjectionPolicyKeys, ", "),
			strings.Join(incomplete, "; "),
		))
		return nil
	})
	if err != nil {
		return nil, err
	}
	sortIssues(issues)
	return issues, nil
}

func declaresElasticsearchQueryProjection(resources map[string]ast.StorageResource) bool {
	for _, resource := range resources {
		if strings.TrimSpace(resource.Engine) == "elasticsearch" &&
			strings.TrimSpace(resource.Role) == "query_projection" {
			return true
		}
	}
	return false
}

// elasticsearchProjectionPolicyCoverage 返回声明了完整 consistency_policy 的
// read_model 名单，以及有 read_model 却缺少或不完整声明的文档描述。
func elasticsearchProjectionPolicyCoverage(objectDir string) (complete []string, incomplete []string, err error) {
	projectionDir := filepath.Join(objectDir, "projections")
	entries, readErr := os.ReadDir(projectionDir)
	if readErr != nil {
		if os.IsNotExist(readErr) {
			return nil, nil, nil
		}
		return nil, nil, readErr
	}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".yaml" {
			continue
		}
		path := filepath.Join(projectionDir, entry.Name())
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return nil, nil, readErr
		}
		var top map[string]any
		if decodeErr := yaml.Unmarshal(data, &top); decodeErr != nil {
			// 形状错误由 projection.schema.json 校验拥有。
			continue
		}
		readModel, _ := top["read_model"].(string)
		readModel = strings.TrimSpace(readModel)
		if readModel == "" {
			continue
		}
		policy, _ := top["consistency_policy"].(map[string]any)
		if policy == nil {
			incomplete = append(incomplete, entry.Name()+" lacks consistency_policy")
			continue
		}
		var missing []string
		for _, key := range elasticsearchProjectionPolicyKeys {
			if value, _ := policy[key].(string); strings.TrimSpace(value) == "" {
				missing = append(missing, key)
			}
		}
		if len(missing) > 0 {
			incomplete = append(incomplete, entry.Name()+" lacks "+strings.Join(missing, ", "))
			continue
		}
		complete = append(complete, readModel)
	}
	return complete, incomplete, nil
}
