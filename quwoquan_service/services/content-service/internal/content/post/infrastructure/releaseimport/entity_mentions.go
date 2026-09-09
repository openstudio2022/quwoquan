package releaseimport

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"unicode/utf16"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
)

type importedEntityMentionTarget struct {
	SubjectID  string
	HomepageID string
}

// BindPostEntityMentions 从 release 内显式 entityId/entityRef 绑定稳定主体，
// Homepage 身份只能来自已验证的 Entity 映射；目录、标题、地理层级均不参与 lookup。
func BindPostEntityMentions(posts []PostDoc, objectRoot string, mapping map[string]string) error {
	hasArticle := false
	for index := range posts {
		posts[index].EntityMentions = nil
		hasArticle = hasArticle || posts[index].ContentType == "article"
	}
	if len(mapping) == 0 || !hasArticle {
		return nil
	}
	targets := make(map[string]importedEntityMentionTarget, len(mapping)*2)
	seenRefs := make(map[string]bool, len(mapping))
	err := filepath.WalkDir(filepath.Join(objectRoot, "entities"), func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("entity mention closure must not contain symlinks")
		}
		if entry.IsDir() || entry.Name() != "manifest.json" {
			return nil
		}
		var manifest struct {
			EntityID  string `json:"entityId"`
			EntityRef string `json:"entityRef"`
		}
		if err := loadReleaseJSON(path, &manifest); err != nil {
			return err
		}
		ref := strings.TrimPrefix(manifest.EntityRef, "/entity/")
		homepageID, selected := mapping[ref]
		if !selected {
			return nil
		}
		if ref == manifest.EntityRef || seenRefs[ref] || strings.TrimSpace(manifest.EntityID) == "" || strings.TrimSpace(manifest.EntityID) != manifest.EntityID {
			return fmt.Errorf("entity mention closure has invalid or duplicate explicit identity")
		}
		target := importedEntityMentionTarget{SubjectID: manifest.EntityID, HomepageID: homepageID}
		for _, key := range []string{manifest.EntityRef, manifest.EntityID} {
			if _, exists := targets[key]; exists {
				return fmt.Errorf("entity mention subject identity is ambiguous")
			}
			targets[key] = target
		}
		seenRefs[ref] = true
		return nil
	})
	if err != nil {
		return err
	}
	if len(seenRefs) != len(mapping) {
		return fmt.Errorf("entity mention mapping lacks release manifest identity")
	}
	for index := range posts {
		if posts[index].ContentType == "article" {
			posts[index].EntityMentions = importedArticleEntityMentions(posts[index].ArticleMarkdown, targets)
		}
	}
	return nil
}

var articleEntityLink = regexp.MustCompile(`@?\[([^\]\n]+)\]\(([^)\s]+)\)`)
var articleMentionHeader = regexp.MustCompile(`(?s)^\x{FEFF}?---[ \t]*\r?\n.*?^---[ \t]*(?:\r?\n|$)`)

// range 使用原 articleMarkdown 中 label 的 UTF-16 字符区间（半开），不使用 UTF-8 byte offset。
// 保持原文及摘要不变；不存在映射时只省略导航增强，由现有阅读器显示原 label。
func importedArticleEntityMentions(markdown string, targets map[string]importedEntityMentionTarget) []postmodel.PostEntityMention {
	var mentions []postmodel.PostEntityMention
	frontMatter, body := splitArticleFrontMatter(markdown)
	bodyStart := 0
	if frontMatter != "" {
		bodyStart = strings.Index(markdown, body)
	}
	if bodyStart < 0 {
		return nil
	}
	fence := ""
	offset := bodyStart
	for _, line := range strings.SplitAfter(markdown[bodyStart:], "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "```") || strings.HasPrefix(trimmed, "~~~") {
			marker := trimmed[:3]
			if fence == "" {
				fence = marker
			} else if fence == marker {
				fence = ""
			}
			offset += len(line)
			continue
		}
		if fence == "" {
			for _, match := range articleEntityLink.FindAllStringSubmatchIndex(line, -1) {
				if match[0] > 0 && (line[match[0]-1] == '!' || line[match[0]-1] == '\\') {
					continue
				}
				// 成对行内 code 中的引用是示例文本，不产生实体导航。
				if strings.Count(line[:match[0]], "`")%2 != 0 {
					continue
				}
				target, exists := targets[line[match[4]:match[5]]]
				if !exists {
					continue
				}
				start := int64(len(utf16.Encode([]rune(markdown[:offset+match[2]]))))
				label := line[match[2]:match[3]]
				mentions = append(mentions, postmodel.PostEntityMention{
					SubjectType: "entity", SubjectId: target.SubjectID, HomepageId: target.HomepageID,
					DisplayName: label, RangeStart: start, RangeEnd: start + int64(len(utf16.Encode([]rune(label)))),
				})
			}
		}
		offset += len(line)
	}
	return mentions
}
