// Command homepage-import 的纯加载层（无 mongo 依赖，可单测）。
//
// 消费 quwoquan_data publish 主线的 entities 目录树（page.md 三件套），构建
// application.ImportedHomepageInput 投影：introductionMarkdown 承载 page.md 全文，
// introductionAssets 把 manifest assets 的 CAS objectKey 经 media origin/CDN base
// 映射为可访问 URL，role 归一为 metadata 闭集 cover/inline/related
// （contracts/metadata/entity/homepage/projections/homepage_introduction_asset.yaml）。
package homepageimport

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"quwoquan_service/services/entity-service/internal/application"
)

// 数据工程实体类型 → 主页类型闭集（application.validateHomepageInput 同源；
// 枚举唯一真相源 contracts/metadata/_shared/types.yaml HomepageType）。
// 地点类覆盖 entity_type_taxonomy.PILOT_PRIMARY_TYPES 试点 scope 全集（裁决 6）。
// 未登记的实体类型属于契约缺口：跳过并报 issue，禁止猜测默认值。
var entityTypeToHomepageType = map[string]string{
	"景区":   "sight",
	"机位":   "travel_photo",
	"住宿":   "hotel",
	"餐饮":   "restaurant",
	"学校":   "university",
	"博物馆":  "museum",
	"遗址":   "heritage_site",
	"古镇":   "ancient_town",
	"宗教场所": "religious_site",
	"打卡地":  "check_in_spot",
	"自然景观": "natural_landscape",
	"公园":   "park",
	"温泉":   "hot_spring",
	"主题乐园": "theme_park",
}

// 数据工程 manifest role → introduction asset role 闭集映射。
var assetRoleToIntroductionRole = map[string]string{
	"cover":   "cover",
	"detail":  "inline",
	"node":    "inline",
	"closing": "related",
}

type entityHeader struct {
	Label        string   `json:"label"`
	Domain       string   `json:"domain"`
	Type         string   `json:"type"`
	City         string   `json:"city"`
	SourceTaskId string   `json:"sourceTaskId"`
	TagRefs      []string `json:"tagRefs"`
}

type entityManifestAsset struct {
	AssetID   string `json:"assetId"`
	Caption   string `json:"caption"`
	Role      string `json:"role"`
	ObjectKey string `json:"objectKey"`
	CDNURL    string `json:"cdnUrl"`
	SourceRef string `json:"sourceRef"`
}

type entityManifest struct {
	SourceTaskId string                `json:"sourceTaskId"`
	Assets       []entityManifestAsset `json:"assets"`
}

func assetURL(asset entityManifestAsset, mediaBaseURL string) string {
	objectKey := strings.TrimSpace(asset.ObjectKey)
	base := strings.TrimRight(strings.TrimSpace(mediaBaseURL), "/")
	if base != "" && objectKey != "" {
		return base + "/" + strings.TrimLeft(objectKey, "/")
	}
	return strings.TrimSpace(asset.CDNURL)
}

// LoadHomepageProjections 遍历 publish/entities，把有 page.md 的实体转为导入投影。
// filter 非空时只保留其中的 entityRef（与 content importer 的 sample bundle 同源）。
func LoadHomepageProjections(
	publishRoot string,
	filter map[string]bool,
	mediaBaseURL string,
) ([]application.ImportedHomepageInput, []string, error) {
	entRoot := filepath.Join(publishRoot, "entities")
	var inputs []application.ImportedHomepageInput
	var issues []string
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
		var header entityHeader
		if jerr := json.Unmarshal(raw, &header); jerr != nil {
			return fmt.Errorf("%s: invalid _entity.json: %w", entityRef, jerr)
		}
		page, perr := os.ReadFile(filepath.Join(filepath.Dir(path), "page.md"))
		if perr != nil {
			// 无 page.md 的实体没有 introduction 可投影，静默跳过（entities
			// collection 导入仍由 content importer 覆盖）。
			return nil
		}
		segs := strings.Split(entityRef, "/")
		etype := strings.TrimSpace(header.Type)
		if etype == "" && len(segs) >= 2 {
			etype = segs[1]
		}
		homepageType, ok := entityTypeToHomepageType[etype]
		if !ok {
			issues = append(issues, fmt.Sprintf("%s: 实体类型 %q 未登记主页类型映射，跳过", entityRef, etype))
			return nil
		}
		title := strings.TrimSpace(header.Label)
		if title == "" {
			title = segs[len(segs)-1]
		}

		var manifest entityManifest
		if rawManifest, merr := os.ReadFile(filepath.Join(filepath.Dir(path), "manifest.json")); merr == nil {
			if jerr := json.Unmarshal(rawManifest, &manifest); jerr != nil {
				return fmt.Errorf("%s: invalid manifest.json: %w", entityRef, jerr)
			}
		}
		assets := make([]application.HomepageIntroductionAsset, 0, len(manifest.Assets))
		for _, asset := range manifest.Assets {
			url := assetURL(asset, mediaBaseURL)
			if url == "" {
				issues = append(issues, fmt.Sprintf(
					"%s: 资产 %s 无 objectKey/cdnUrl 可映射 URL（publish 树未 materialize？）",
					entityRef, asset.AssetID,
				))
				continue
			}
			role, ok := assetRoleToIntroductionRole[strings.TrimSpace(asset.Role)]
			if !ok {
				role = "related"
			}
			assets = append(assets, application.HomepageIntroductionAsset{
				AssetID:   strings.TrimSpace(asset.AssetID),
				URL:       url,
				Caption:   strings.TrimSpace(asset.Caption),
				Role:      role,
				SourceRef: strings.TrimSpace(asset.SourceRef),
			})
		}
		sourceTask := strings.TrimSpace(header.SourceTaskId)
		if sourceTask == "" {
			sourceTask = strings.TrimSpace(manifest.SourceTaskId)
		}
		// WP3 统一打标：_entity.json.tagRefs → categoryTags 投影，
		// 与 content-service import 导 entities.tagRefs 同源（消除双轨不一致）。
		categoryTags := make([]string, 0, len(header.TagRefs))
		for _, ref := range header.TagRefs {
			if trimmed := strings.TrimSpace(ref); trimmed != "" {
				categoryTags = append(categoryTags, trimmed)
			}
		}
		inputs = append(inputs, application.ImportedHomepageInput{
			EntityRef:            entityRef,
			Title:                title,
			HomepageType:         homepageType,
			City:                 strings.TrimSpace(header.City),
			IntroductionMarkdown: string(page),
			IntroductionAssets:   assets,
			CategoryTags:         categoryTags,
			SourceTaskID:         sourceTask,
		})
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return inputs, issues, err
	}
	return inputs, issues, nil
}
