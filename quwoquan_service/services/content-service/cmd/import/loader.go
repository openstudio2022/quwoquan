// Package main: publish→运行库 importer 的纯加载层（无 mongo 依赖，可单测）。
//
// 唯一内容真相源是 quwoquan_data/publish 主线（单一发布主线，无版本目录）。
// 本加载层只读消费 publish/posts 与 publish/entities 目录树，按可选 sample bundle
// 过滤出某环境应灌入的 postRef / entityRef 子集，构建可幂等 upsert 的文档。
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var (
	sha256Pattern        = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	casObjectKeyPattern  = regexp.MustCompile(`^media/objects/sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}\.[A-Za-z0-9]+$`)
)

type AssetManifestItem struct {
	AssetID              string `json:"assetId" bson:"assetId"`
	Kind                 string `json:"kind,omitempty" bson:"kind,omitempty"`
	ObjectKey            string `json:"objectKey" bson:"objectKey"`
	CDNURL               string `json:"cdnUrl,omitempty" bson:"cdnUrl,omitempty"`
	Sha256               string `json:"sha256" bson:"sha256"`
	MimeType             string `json:"mimeType,omitempty" bson:"mimeType,omitempty"`
	SourceOriginalSha256 string `json:"sourceOriginalSha256,omitempty" bson:"sourceOriginalSha256,omitempty"`
}

type ArticleAssetManifestDoc struct {
	SchemaVersion         int                 `json:"schemaVersion" bson:"schemaVersion"`
	ArticleMarkdownVersion string             `json:"articleMarkdownVersion,omitempty" bson:"articleMarkdownVersion,omitempty"`
	ArticleMarkdownDigest string              `json:"articleMarkdownDigest" bson:"articleMarkdownDigest"`
	DocumentSha256        string              `json:"documentSha256" bson:"documentSha256"`
	AssetManifestSha256   string              `json:"assetManifestSha256" bson:"assetManifestSha256"`
	DocumentVersionSha256 string              `json:"documentVersionSha256" bson:"documentVersionSha256"`
	Assets                []AssetManifestItem `json:"assets" bson:"assets"`
}

type EntityAssetManifestDoc struct {
	Assets []AssetManifestItem `json:"assets" bson:"assets"`
}

// PostDoc 是灌入运行库的文章文档（与 publish post manifest + article.md 对齐）。
type PostDoc struct {
	PostRef              string                   `json:"postRef" bson:"postRef"`
	ContentType          string                   `json:"contentType" bson:"contentType"`
	Title                string                   `json:"title" bson:"title"`
	Angle                string                   `json:"angle" bson:"angle"`
	Seq                  int                      `json:"seq" bson:"seq"`
	EntityRefs           []string                 `json:"entityRefs" bson:"entityRefs"`
	TagRefs              []string                 `json:"tagRefs" bson:"tagRefs"`
	Template             string                   `json:"template" bson:"template"`
	GeneratorModel       string                   `json:"generatorModel" bson:"generatorModel"`
	ArticleMarkdown      string                   `json:"articleMarkdown" bson:"articleMarkdown"`
	ArticleDigest        string                   `json:"articleDigest" bson:"articleDigest"`
	ArticleAssetManifest *ArticleAssetManifestDoc `json:"articleAssetManifest" bson:"articleAssetManifest"`
	SourceTaskId         string                   `json:"sourceTaskId" bson:"sourceTaskId"`
}

// EntityDoc 是灌入运行库的实体文档（与 publish entity _entity.json + page.md 对齐）。
type EntityDoc struct {
	EntityRef     string                  `json:"entityRef" bson:"entityRef"`
	Domain        string                  `json:"domain" bson:"domain"`
	Etype         string                  `json:"etype" bson:"etype"`
	Name          string                  `json:"name" bson:"name"`
	Label         string                  `json:"label" bson:"label"`
	TagRefs       []string                `json:"tagRefs" bson:"tagRefs"`
	Page          string                  `json:"page" bson:"page"`
	HasPage       bool                    `json:"hasPage" bson:"hasPage"`
	AssetManifest *EntityAssetManifestDoc `json:"assetManifest" bson:"assetManifest"`
	// ConditionProfile 条件画像（L3 实体级 {regions/seasons/altitudeMeters}），从 _entity.json 透传到运行库。
	ConditionProfile map[string]any `json:"conditionProfile" bson:"conditionProfile"`
	SourceTaskId     string         `json:"sourceTaskId" bson:"sourceTaskId"`
}

// SampleBundle 是端云桥契约：某环境应灌入的 ref 子集。
type SampleBundle struct {
	Environment string   `json:"environment"`
	Posts       []string `json:"posts"`
	Entities    []string `json:"entities"`
}

func loadSampleBundle(path string) (*SampleBundle, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var b SampleBundle
	if err := json.Unmarshal(raw, &b); err != nil {
		return nil, err
	}
	return &b, nil
}

func toSet(items []string) map[string]bool {
	if len(items) == 0 {
		return nil
	}
	s := make(map[string]bool, len(items))
	for _, it := range items {
		s[it] = true
	}
	return s
}

type postManifest struct {
	ContentType          string                   `json:"contentType"`
	EntityRefs           []string                 `json:"entityRefs"`
	TagRefs              []string                 `json:"tagRefs"`
	Template             string                   `json:"template"`
	GeneratorModel       string                   `json:"generatorModel"`
	ArticleDigest        string                   `json:"articleMarkdownDigest"`
	PublishTitle         string                   `json:"publishTitle"`
	PublishAngle         string                   `json:"publishAngle"`
	PublishSeq           int                      `json:"publishSeq"`
	SourceTaskId         string                   `json:"sourceTaskId"`
	ArticleAssetManifest *ArticleAssetManifestDoc `json:"articleAssetManifest"`
}

func validateAssetItem(asset AssetManifestItem, ref string) error {
	if strings.TrimSpace(asset.AssetID) == "" {
		return fmt.Errorf("%s: asset manifest missing assetId", ref)
	}
	if !casObjectKeyPattern.MatchString(strings.TrimSpace(asset.ObjectKey)) {
		return fmt.Errorf("%s: asset manifest objectKey must be CAS path", ref)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(asset.Sha256)) {
		return fmt.Errorf("%s: asset manifest sha256 invalid", ref)
	}
	if asset.SourceOriginalSha256 != "" && !sha256Pattern.MatchString(strings.TrimSpace(asset.SourceOriginalSha256)) {
		return fmt.Errorf("%s: asset manifest sourceOriginalSha256 invalid", ref)
	}
	return nil
}

func validateArticleAssetManifest(manifest *ArticleAssetManifestDoc, ref string) error {
	if manifest == nil {
		return nil
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(manifest.ArticleMarkdownDigest)) {
		return fmt.Errorf("%s: articleAssetManifest.articleMarkdownDigest invalid", ref)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(manifest.DocumentSha256)) {
		return fmt.Errorf("%s: articleAssetManifest.documentSha256 invalid", ref)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(manifest.AssetManifestSha256)) {
		return fmt.Errorf("%s: articleAssetManifest.assetManifestSha256 invalid", ref)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(manifest.DocumentVersionSha256)) {
		return fmt.Errorf("%s: articleAssetManifest.documentVersionSha256 invalid", ref)
	}
	for _, asset := range manifest.Assets {
		if err := validateAssetItem(asset, ref); err != nil {
			return err
		}
	}
	return nil
}

func validateEntityAssetManifest(manifest *EntityAssetManifestDoc, ref string) error {
	if manifest == nil {
		return nil
	}
	for _, asset := range manifest.Assets {
		if err := validateAssetItem(asset, ref); err != nil {
			return err
		}
	}
	return nil
}

// LoadPosts 从 publish/posts 加载文章；filter 非空时只保留其中的 postRef。
func LoadPosts(publishRoot string, filter map[string]bool) ([]PostDoc, error) {
	postsRoot := filepath.Join(publishRoot, "posts")
	var docs []PostDoc
	err := filepath.WalkDir(postsRoot, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || d.Name() != "manifest.json" {
			return nil
		}
		rel, rerr := filepath.Rel(publishRoot, filepath.Dir(path))
		if rerr != nil {
			return rerr
		}
		postRef := filepath.ToSlash(rel)
		if filter != nil && !filter[postRef] {
			return nil
		}
		raw, rerr := os.ReadFile(path)
		if rerr != nil {
			return rerr
		}
		var m postManifest
		if jerr := json.Unmarshal(raw, &m); jerr != nil {
			return jerr
		}
		if err := validateArticleAssetManifest(m.ArticleAssetManifest, postRef); err != nil {
			return err
		}
		article := ""
		if a, aerr := os.ReadFile(filepath.Join(filepath.Dir(path), "article.md")); aerr == nil {
			article = string(a)
		}
		segs := strings.Split(postRef, "/")
		title, angle := m.PublishTitle, m.PublishAngle
		if len(segs) >= 4 {
			if angle == "" {
				angle = segs[2]
			}
			if title == "" {
				title = segs[3]
			}
		}
		docs = append(docs, PostDoc{
			PostRef:              postRef,
			ContentType:          m.ContentType,
			Title:                title,
			Angle:                angle,
			Seq:                  m.PublishSeq,
			EntityRefs:           m.EntityRefs,
			TagRefs:              m.TagRefs,
			Template:             m.Template,
			GeneratorModel:       m.GeneratorModel,
			ArticleMarkdown:      article,
			ArticleDigest:        m.ArticleDigest,
			ArticleAssetManifest: m.ArticleAssetManifest,
			SourceTaskId:         m.SourceTaskId,
		})
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return docs, err
	}
	return docs, nil
}

type entityFile struct {
	Label            string         `json:"label"`
	Domain           string         `json:"domain"`
	Type             string         `json:"type"`
	TagRefs          []string       `json:"tagRefs"`
	ConditionProfile map[string]any `json:"conditionProfile"`
	SourceTaskId     string         `json:"sourceTaskId"`
}

// LoadEntities 从 publish/entities 加载实体；filter 非空时只保留其中的 entityRef。
func LoadEntities(publishRoot string, filter map[string]bool) ([]EntityDoc, error) {
	entRoot := filepath.Join(publishRoot, "entities")
	var docs []EntityDoc
	err := filepath.WalkDir(entRoot, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || d.Name() != "_entity.json" {
			return nil
		}
		rel, rerr := filepath.Rel(entRoot, filepath.Dir(path))
		if rerr != nil {
			return rerr
		}
		entityRef := filepath.ToSlash(rel)
		if filter != nil && !filter[entityRef] {
			return nil
		}
		raw, rerr := os.ReadFile(path)
		if rerr != nil {
			return rerr
		}
		var ef entityFile
		if jerr := json.Unmarshal(raw, &ef); jerr != nil {
			return jerr
		}
		segs := strings.Split(entityRef, "/")
		domain, etype, name := ef.Domain, ef.Type, ""
		if len(segs) >= 3 {
			if domain == "" {
				domain = segs[0]
			}
			if etype == "" {
				etype = segs[1]
			}
			name = segs[len(segs)-1]
		}
		page := ""
		hasPage := false
		if p, perr := os.ReadFile(filepath.Join(filepath.Dir(path), "page.md")); perr == nil {
			page = string(p)
			hasPage = true
		}
		assetManifest := (*EntityAssetManifestDoc)(nil)
		if rawManifest, merr := os.ReadFile(filepath.Join(filepath.Dir(path), "manifest.json")); merr == nil {
			var parsed EntityAssetManifestDoc
			if jerr := json.Unmarshal(rawManifest, &parsed); jerr != nil {
				return jerr
			}
			if err := validateEntityAssetManifest(&parsed, entityRef); err != nil {
				return err
			}
			assetManifest = &parsed
		}
		label := ef.Label
		if label == "" {
			label = name
		}
		docs = append(docs, EntityDoc{
			EntityRef:        entityRef,
			Domain:           domain,
			Etype:            etype,
			Name:             name,
			Label:            label,
			TagRefs:          ef.TagRefs,
			Page:             page,
			HasPage:          hasPage,
			AssetManifest:    assetManifest,
			ConditionProfile: ef.ConditionProfile,
			SourceTaskId:     ef.SourceTaskId,
		})
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return docs, err
	}
	return docs, nil
}
