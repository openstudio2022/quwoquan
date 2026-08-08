package validate

import (
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// isProjectionDocument 判断一个文件是否是对象包的投影声明文档。
//
// 投影文件名由读模型自己决定（content_post_projection.yaml、feed_object_card.yaml
// …），所以它无法像 fields.yaml / operations.yaml 那样按 filename 索引 schema。
// 唯一稳定的身份事实是位置：宿主对象包 projections/ 目录下的 .yaml。这与 loader
// 的 loadProjections 使用同一条位置规则，不构成第二套投影识别口径。
func isProjectionDocument(path string, entry fs.DirEntry) bool {
	if entry.IsDir() || filepath.Ext(entry.Name()) != ".yaml" {
		return false
	}
	projectionDir := filepath.Dir(path)
	if filepath.Base(projectionDir) != "projections" {
		return false
	}
	_, err := os.Stat(filepath.Join(filepath.Dir(projectionDir), "object.yaml"))
	return err == nil
}

// projectionCoPresenceIssues 关闭 co_present_with 的悬空引用。
//
// JSON Schema 只能约束这一位的形状，不能证明 peer 真的存在；而 all-present-or-
// all-absent 分组只有在 peer 是同一读模型里的兄弟字段时才有意义。悬空 peer 会被
// 解码器静默降级成「无约束」，因此必须在声明位 fail-closed。
func projectionCoPresenceIssues(sourcePath string, instance any) []Issue {
	document, ok := instance.(map[string]any)
	if !ok {
		return nil
	}
	var issues []Issue
	for _, fieldsKey := range []string{"fields", "envelope_fields"} {
		entries, ok := document[fieldsKey].([]any)
		if !ok {
			continue
		}
		declared := projectionFieldNameSet(entries)
		for _, entry := range entries {
			field, ok := entry.(map[string]any)
			if !ok {
				continue
			}
			name, _ := field["name"].(string)
			peers, ok := field["co_present_with"].([]any)
			if !ok {
				continue
			}
			for _, rawPeer := range peers {
				peer, ok := rawPeer.(string)
				if !ok {
					continue
				}
				peer = strings.TrimSpace(peer)
				if peer == strings.TrimSpace(name) {
					issues = append(issues, issue(
						"CONTRACT.PROJECTION.SELF_CO_PRESENT_FIELD",
						sourcePath,
						"%s field %q declares co_present_with on itself",
						fieldsKey,
						name,
					))
					continue
				}
				if _, exists := declared[peer]; !exists {
					issues = append(issues, issue(
						"CONTRACT.PROJECTION.UNKNOWN_CO_PRESENT_FIELD",
						sourcePath,
						"%s field %q declares co_present_with %q, which is not a sibling field of this read model",
						fieldsKey,
						name,
						peer,
					))
				}
			}
		}
	}
	return issues
}

func projectionFieldNameSet(entries []any) map[string]struct{} {
	declared := make(map[string]struct{}, len(entries))
	for _, entry := range entries {
		switch typed := entry.(type) {
		case string:
			if name := strings.TrimSpace(typed); name != "" {
				declared[name] = struct{}{}
			}
		case map[string]any:
			if name, ok := typed["name"].(string); ok {
				if trimmed := strings.TrimSpace(name); trimmed != "" {
					declared[trimmed] = struct{}{}
				}
			}
		}
	}
	return declared
}
