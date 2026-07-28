// Command homepage-import 的纯加载层（无 mongo 依赖，可单测）。
//
// 消费 quwoquan_data publish 主线的 entities 目录树（page.md 三件套），构建
// application.ImportedHomepageInput 投影：introductionMarkdown 承载 page.md 全文，
// introductionAssets 只通过 release MediaAsset authority 解析 public slice URL，
// role 归一为 metadata 闭集 cover/inline/related
// （services/entity-service/contracts/entity_homepage/homepage/projections/homepage_introduction_asset.yaml）。
package homepageimport

import (
	"encoding/json"
	"fmt"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
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

// 数据工程 homepage manifest role → introduction asset role 闭集映射。
//
// `manifest.json` is the only semantic asset source. `asset.refs.json` is a
// CAS-closure index and deliberately contains no role or caption; using it as
// a projection input silently turns every asset into a related image.
var assetRoleToIntroductionRole = map[string]string{
	"cover":   "cover",
	"inline":  "inline",
	"related": "related",
}

type entityHeader struct {
	Label         string                      `json:"label"`
	Domain        string                      `json:"domain"`
	Type          string                      `json:"type"`
	City          string                      `json:"city"`
	SourceTaskId  string                      `json:"sourceTaskId"`
	TagRefs       []string                    `json:"tagRefs"`
	PrimarySource *application.HomepageSource `json:"primarySource"`
	SourceURLs    []string                    `json:"sourceUrls"`
}

var homepageSourceKinds = map[string]bool{
	"wikipedia": true, "baidu_baike": true, "sogou_baike": true, "toutiao_baike": true,
}

const homepageSourcePolicy = "encyclopedia-primary"

func validatePublicHomepageSources(header entityHeader) error {
	if header.PrimarySource == nil || !homepageSourceKinds[strings.TrimSpace(header.PrimarySource.SourceKind)] {
		return fmt.Errorf("primarySource.sourceKind 不在四百科闭集")
	}
	if header.PrimarySource.PolicyRevision != homepageSourcePolicy {
		return fmt.Errorf("primarySource.policyRevision 与当前合同不一致")
	}
	if len(header.SourceURLs) == 0 || strings.TrimSpace(header.PrimarySource.SourceURL) != strings.TrimSpace(header.SourceURLs[0]) {
		return fmt.Errorf("sourceUrls 与 primarySource.sourceUrl 不一致")
	}
	for _, raw := range header.SourceURLs {
		parsed, err := url.Parse(strings.TrimSpace(raw))
		if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" || parsed.User != nil {
			return fmt.Errorf("sourceUrls 含非 canonical HTTPS URL")
		}
		host := strings.ToLower(parsed.Hostname())
		if host == "localhost" || strings.HasSuffix(host, ".local") {
			return fmt.Errorf("sourceUrls 含私网主机")
		}
		if ip := net.ParseIP(host); ip != nil && (ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast()) {
			return fmt.Errorf("sourceUrls 含私网 IP")
		}
		for key := range parsed.Query() {
			lower := strings.ToLower(key)
			if strings.Contains(lower, "token") || strings.Contains(lower, "signature") ||
				strings.Contains(lower, "credential") || strings.Contains(lower, "auth") {
				return fmt.Errorf("sourceUrls 含敏感 query")
			}
		}
	}
	return nil
}

type entityManifestAsset struct {
	AssetID   string `json:"assetId"`
	Kind      string `json:"kind"`
	SHA256    string `json:"sha256"`
	Caption   string `json:"caption"`
	Role      string `json:"role"`
	SourceRef string `json:"sourceRef"`
	ObjectKey string `json:"objectKey"`
}

type entityHomepageManifest struct {
	ExecutionID string                `json:"executionId"`
	Assets      []entityManifestAsset `json:"assets"`
}

func loadIntroductionAssets(
	entityRef string,
	entityDir string,
	releaseAssets map[string]runtimemedia.ReleaseMediaAsset,
	mediaBases runtimemedia.MediaDeliveryBases,
) ([]application.HomepageIntroductionAsset, string, error) {
	rawManifest, err := os.ReadFile(filepath.Join(entityDir, "manifest.json"))
	if err != nil {
		return nil, "", fmt.Errorf("%s: read semantic manifest.json: %w", entityRef, err)
	}
	var manifest entityHomepageManifest
	if err := json.Unmarshal(rawManifest, &manifest); err != nil {
		return nil, "", fmt.Errorf("%s: invalid semantic manifest.json: %w", entityRef, err)
	}
	if len(manifest.Assets) == 0 {
		return nil, "", fmt.Errorf("%s: semantic manifest.json has no homepage assets", entityRef)
	}

	assets := make([]application.HomepageIntroductionAsset, 0, len(manifest.Assets))
	coverCount := 0
	for index, asset := range manifest.Assets {
		assetID := strings.TrimSpace(asset.AssetID)
		if assetID == "" {
			return nil, "", fmt.Errorf("%s: manifest assets[%d] lacks assetId", entityRef, index)
		}
		if strings.TrimSpace(asset.ObjectKey) != "" {
			return nil, "", fmt.Errorf(
				"%s: manifest asset %s contains forbidden objectKey",
				entityRef,
				assetID,
			)
		}
		role, ok := assetRoleToIntroductionRole[strings.TrimSpace(asset.Role)]
		if !ok {
			return nil, "", fmt.Errorf("%s: manifest asset %s has unsupported role %q", entityRef, assetID, asset.Role)
		}
		resolved, resolveErr := runtimemedia.ResolveReleaseMediaAsset(
			releaseAssets,
			mediaBases,
			assetID,
			asset.Kind,
			asset.SHA256,
			"entities/"+entityRef,
		)
		if resolveErr != nil {
			return nil, "", fmt.Errorf(
				"%s: manifest asset %s differs from release media authority: %w",
				entityRef,
				assetID,
				resolveErr,
			)
		}
		if role == "cover" {
			coverCount++
		}
		assets = append(assets, application.HomepageIntroductionAsset{
			AssetID: assetID,
			URL:     resolved.PublicURL,
			Caption: strings.TrimSpace(asset.Caption),
			Role:    role,
		})
	}
	if coverCount != 1 {
		return nil, "", fmt.Errorf("%s: semantic manifest must contain exactly one cover asset, got %d", entityRef, coverCount)
	}
	return assets, strings.TrimSpace(manifest.ExecutionID), nil
}

func frontmatterCoverAssetID(page []byte) (string, error) {
	lines := strings.Split(strings.ReplaceAll(string(page), "\r\n", "\n"), "\n")
	if len(lines) < 3 || strings.TrimSpace(lines[0]) != "---" {
		return "", fmt.Errorf("page.md lacks YAML frontmatter")
	}
	coverID := ""
	closed := false
	for _, line := range lines[1:] {
		trimmed := strings.TrimSpace(line)
		if trimmed == "---" {
			closed = true
			break
		}
		if !strings.HasPrefix(trimmed, "coverImage:") {
			continue
		}
		if coverID != "" {
			return "", fmt.Errorf("page.md contains multiple coverImage values")
		}
		value := strings.TrimSpace(strings.TrimPrefix(trimmed, "coverImage:"))
		if !strings.HasPrefix(value, "asset://") || strings.TrimSpace(strings.TrimPrefix(value, "asset://")) == "" {
			return "", fmt.Errorf("page.md coverImage must reference asset://<assetId>")
		}
		coverID = strings.TrimSpace(strings.TrimPrefix(value, "asset://"))
	}
	if !closed || coverID == "" {
		return "", fmt.Errorf("page.md lacks coverImage")
	}
	return coverID, nil
}

// LoadHomepageProjections 遍历 publish/entities，把有 page.md 的实体转为导入投影。
// filter 必须来自 immutable release desired state。
func LoadHomepageProjections(
	publishRoot string,
	filter map[string]bool,
	releaseAssets map[string]runtimemedia.ReleaseMediaAsset,
	mediaBases runtimemedia.MediaDeliveryBases,
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
		if sourceErr := validatePublicHomepageSources(header); sourceErr != nil {
			issues = append(issues, fmt.Sprintf("%s: %v，跳过", entityRef, sourceErr))
			return nil
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

		assets, executionID, assetErr := loadIntroductionAssets(
			entityRef,
			filepath.Dir(path),
			releaseAssets,
			mediaBases,
		)
		if assetErr != nil {
			return assetErr
		}
		coverID, coverErr := frontmatterCoverAssetID(page)
		if coverErr != nil {
			return fmt.Errorf("%s: %w", entityRef, coverErr)
		}
		coverMatches := false
		for _, asset := range assets {
			if asset.Role == "cover" && asset.AssetID == coverID {
				coverMatches = true
				break
			}
		}
		if !coverMatches {
			return fmt.Errorf("%s: page.md coverImage %q does not match semantic cover asset", entityRef, coverID)
		}
		sourceTask := strings.TrimSpace(header.SourceTaskId)
		if sourceTask == "" {
			sourceTask = executionID
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
			PrimarySource:        header.PrimarySource,
			SourceURLs:           append([]string(nil), header.SourceURLs...),
		})
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return inputs, issues, err
	}
	return inputs, issues, nil
}
