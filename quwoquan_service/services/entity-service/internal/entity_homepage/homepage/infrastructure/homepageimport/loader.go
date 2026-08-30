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
// 地点类覆盖 entity_type_taxonomy.PILOT_PRIMARY_TYPES 试点 scope 全集（裁决 6），
// 并前置登记 taxonomy 已有但尚未进入试点 scope 的 entityType，使试点扩容时无需改码。
// 未登记的实体类型属于契约缺口：跳过并报 issue，禁止猜测默认值。
var entityTypeToHomepageType = map[string]string{
	"景区":   "sight",
	"机位":   "photo_spot",
	"交通枢纽": "transport_hub",
	"城市":   "city",
	"住宿":   "hotel",
	"餐饮":   "restaurant",
	"学校":   "school",
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

// MediaDeliveryAccessMode 契约 enum 值（唯一真相源
// contracts/metadata/_shared/types.yaml MediaDeliveryAccessMode）。
// research release 的媒体交付引用是相对私有 CAS key，App 必须换短签消费；
// commercial release 的交付引用是 canonical public slice。
const (
	mediaDeliveryAccessModePublic      = "public"
	mediaDeliveryAccessModeSignedGrant = "signed_grant"
)

// mediaDeliveryAccessModeForReleaseClass 把 release header 的 releaseClass 映射
// 为逐资产 accessMode（DEC-033）：research → signed_grant、commercial → public。
// 其它/未声明类别返回空串表示缺席——契约 accessMode 为 NULLABLE，缺席时端按
// 存量 public 交付消费，不得由 importer 造值。
func mediaDeliveryAccessModeForReleaseClass(releaseClass string) string {
	switch strings.TrimSpace(releaseClass) {
	case "research":
		return mediaDeliveryAccessModeSignedGrant
	case "commercial":
		return mediaDeliveryAccessModePublic
	default:
		return ""
	}
}

type entityHeader struct {
	Label           string                       `json:"label"`
	Domain          string                       `json:"domain"`
	Type            string                       `json:"type"`
	City            string                       `json:"city"`
	Coordinates     *entityCoordinates           `json:"coordinates"`
	TagRefs         []string                     `json:"tagRefs"`
	StructuredFacts *application.StructuredFacts `json:"structuredFacts"`
	PrimarySource   *application.HomepageSource  `json:"primarySource"`
	SourceURLs      []string                     `json:"sourceUrls"`
}

// entityCoordinates 对齐 quwoquan_data/schema/publish/entity.schema.json 的
// coordinates（lat/lon 双精度、NULLABLE）。这是主页 location 的唯一入口：
// 缺坐标的实体保持 location 为空，由 App「附近」入口自然缺席，不得就近推断。
type entityCoordinates struct {
	Lat *float64 `json:"lat"`
	Lon *float64 `json:"lon"`
}

// geoPointFromCoordinates 把发布态坐标翻译成主页 GeoPoint；缺字段或越界一律
// 返回 nil + 原因，由调用方按 issue 跳过坐标而非跳过整个主页。
func geoPointFromCoordinates(coordinates *entityCoordinates) (*application.GeoPoint, string) {
	if coordinates == nil {
		return nil, ""
	}
	if coordinates.Lat == nil || coordinates.Lon == nil {
		return nil, "coordinates 缺少 lat 或 lon"
	}
	point := application.GeoPoint{Latitude: *coordinates.Lat, Longitude: *coordinates.Lon}
	if !point.InRange() {
		return nil, fmt.Sprintf("coordinates (%v, %v) 越界或为缺省零点", *coordinates.Lat, *coordinates.Lon)
	}
	return &point, ""
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
	Assets []entityManifestAsset `json:"assets"`
}

func loadIntroductionAssets(
	entityRef string,
	entityDir string,
	releaseAssets map[string]runtimemedia.ReleaseMediaAsset,
	mediaBases runtimemedia.MediaDeliveryBases,
	accessMode string,
) ([]application.HomepageIntroductionAsset, error) {
	rawManifest, err := os.ReadFile(filepath.Join(entityDir, "manifest.json"))
	if err != nil {
		return nil, fmt.Errorf("%s: read semantic manifest.json: %w", entityRef, err)
	}
	var manifest entityHomepageManifest
	if err := json.Unmarshal(rawManifest, &manifest); err != nil {
		return nil, fmt.Errorf("%s: invalid semantic manifest.json: %w", entityRef, err)
	}
	if len(manifest.Assets) == 0 {
		return nil, fmt.Errorf("%s: semantic manifest.json has no homepage assets", entityRef)
	}

	assets := make([]application.HomepageIntroductionAsset, 0, len(manifest.Assets))
	coverCount := 0
	for index, asset := range manifest.Assets {
		assetID := strings.TrimSpace(asset.AssetID)
		if assetID == "" {
			return nil, fmt.Errorf("%s: manifest assets[%d] lacks assetId", entityRef, index)
		}
		if strings.TrimSpace(asset.ObjectKey) != "" {
			return nil, fmt.Errorf(
				"%s: manifest asset %s contains forbidden objectKey",
				entityRef,
				assetID,
			)
		}
		role, ok := assetRoleToIntroductionRole[strings.TrimSpace(asset.Role)]
		if !ok {
			return nil, fmt.Errorf("%s: manifest asset %s has unsupported role %q", entityRef, assetID, asset.Role)
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
			return nil, fmt.Errorf(
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
			AssetID:    assetID,
			URL:        resolved.DeliveryRef,
			AccessMode: accessMode,
			Caption:    strings.TrimSpace(asset.Caption),
			Role:       role,
		})
	}
	if coverCount != 1 {
		return nil, fmt.Errorf("%s: semantic manifest must contain exactly one cover asset, got %d", entityRef, coverCount)
	}
	return assets, nil
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
// filter 必须来自 immutable release desired state；releaseClass 必须来自 release
// header（DEC-031：交付形态由 release 断言，不得推断），它决定逐资产 accessMode。
func LoadHomepageProjections(
	publishRoot string,
	filter map[string]bool,
	releaseAssets map[string]runtimemedia.ReleaseMediaAsset,
	mediaBases runtimemedia.MediaDeliveryBases,
	releaseClass string,
) ([]application.ImportedHomepageInput, []string, error) {
	accessMode := mediaDeliveryAccessModeForReleaseClass(releaseClass)
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

		assets, assetErr := loadIntroductionAssets(
			entityRef,
			filepath.Dir(path),
			releaseAssets,
			mediaBases,
			accessMode,
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
		// WP3 统一打标：_entity.json.tagRefs → categoryTags 投影，
		// 与 content-service import 导 entities.tagRefs 同源（消除双轨不一致）。
		categoryTags := make([]string, 0, len(header.TagRefs))
		for _, ref := range header.TagRefs {
			if trimmed := strings.TrimSpace(ref); trimmed != "" {
				categoryTags = append(categoryTags, trimmed)
			}
		}
		location, geoIssue := geoPointFromCoordinates(header.Coordinates)
		if geoIssue != "" {
			issues = append(issues, fmt.Sprintf("%s: %s，主页 location 留空", entityRef, geoIssue))
		}
		// 缺证据或形状非法的事实字段在这里就被丢掉并报 issue：聚合还会再收敛一次，
		// 但只有导入阶段能把「哪个实体的哪个字段被丢了」交回数据侧修。
		facts, factIssues := application.SanitizeStructuredFacts(header.StructuredFacts)
		for _, factIssue := range factIssues {
			issues = append(issues, fmt.Sprintf("%s: structuredFacts %s，该字段不投影", entityRef, factIssue))
		}
		inputs = append(inputs, application.ImportedHomepageInput{
			EntityRef:            entityRef,
			Title:                title,
			HomepageType:         homepageType,
			City:                 strings.TrimSpace(header.City),
			Location:             location,
			IntroductionMarkdown: string(page),
			IntroductionAssets:   assets,
			StructuredFacts:      facts,
			CategoryTags:         categoryTags,
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
