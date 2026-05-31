// Package main: publish→运行库 importer 的纯加载层（无 mongo 依赖，可单测）。
//
// 唯一内容真相源是 quwoquan_data/publish 主线（单一发布主线，无版本目录）。
// 本加载层只读消费 publish/posts 与 publish/entities 目录树，按可选 sample bundle
// 过滤出某环境应灌入的 postRef / entityRef 子集，构建可幂等 upsert 的文档。
package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
)

// PostDoc 是灌入运行库的文章文档（与 publish post manifest + article.md 对齐）。
type PostDoc struct {
	PostRef         string   `json:"postRef" bson:"postRef"`
	ContentType     string   `json:"contentType" bson:"contentType"`
	Title           string   `json:"title" bson:"title"`
	Angle           string   `json:"angle" bson:"angle"`
	Seq             int      `json:"seq" bson:"seq"`
	EntityRefs      []string `json:"entityRefs" bson:"entityRefs"`
	TagRefs         []string `json:"tagRefs" bson:"tagRefs"`
	Template        string   `json:"template" bson:"template"`
	GeneratorModel  string   `json:"generatorModel" bson:"generatorModel"`
	ArticleMarkdown string   `json:"articleMarkdown" bson:"articleMarkdown"`
	ArticleDigest   string   `json:"articleDigest" bson:"articleDigest"`
}

// EntityDoc 是灌入运行库的实体文档（与 publish entity _entity.json + page.md 对齐）。
type EntityDoc struct {
	EntityRef string   `json:"entityRef" bson:"entityRef"`
	Domain    string   `json:"domain" bson:"domain"`
	Etype     string   `json:"etype" bson:"etype"`
	Name      string   `json:"name" bson:"name"`
	Label     string   `json:"label" bson:"label"`
	TagRefs   []string `json:"tagRefs" bson:"tagRefs"`
	Page      string   `json:"page" bson:"page"`
	HasPage   bool     `json:"hasPage" bson:"hasPage"`
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
	ContentType    string   `json:"contentType"`
	EntityRefs     []string `json:"entityRefs"`
	TagRefs        []string `json:"tagRefs"`
	Template       string   `json:"template"`
	GeneratorModel string   `json:"generatorModel"`
	ArticleDigest  string   `json:"articleMarkdownDigest"`
	PublishTitle   string   `json:"publishTitle"`
	PublishAngle   string   `json:"publishAngle"`
	PublishSeq     int      `json:"publishSeq"`
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
			PostRef:         postRef,
			ContentType:     m.ContentType,
			Title:           title,
			Angle:           angle,
			Seq:             m.PublishSeq,
			EntityRefs:      m.EntityRefs,
			TagRefs:         m.TagRefs,
			Template:        m.Template,
			GeneratorModel:  m.GeneratorModel,
			ArticleMarkdown: article,
			ArticleDigest:   m.ArticleDigest,
		})
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return docs, err
	}
	return docs, nil
}

type entityFile struct {
	Label   string   `json:"label"`
	Domain  string   `json:"domain"`
	Type    string   `json:"type"`
	TagRefs []string `json:"tagRefs"`
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
		label := ef.Label
		if label == "" {
			label = name
		}
		docs = append(docs, EntityDoc{
			EntityRef: entityRef,
			Domain:    domain,
			Etype:     etype,
			Name:      name,
			Label:     label,
			TagRefs:   ef.TagRefs,
			Page:      page,
			HasPage:   hasPage,
		})
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return docs, err
	}
	return docs, nil
}
