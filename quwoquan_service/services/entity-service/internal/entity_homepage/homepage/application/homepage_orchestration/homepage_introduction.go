package application

import (
	"context"
	"regexp"
	"sort"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
)

// 三段结构 asset role 闭集（projections/homepage_introduction_asset.yaml 同源）。
const (
	introductionAssetRoleCover   = "cover"
	introductionAssetRoleInline  = "inline"
	introductionAssetRoleRelated = "related"
)

type HomepageIntroductionTimelineItem struct {
	DateLabel string `json:"dateLabel"`
	Text      string `json:"text"`
	AssetURL  string `json:"assetUrl,omitempty"`
}

type HomepageIntroductionSection struct {
	Kind          string                             `json:"kind"`
	Title         string                             `json:"title"`
	BodyMarkdown  string                             `json:"bodyMarkdown,omitempty"`
	Assets        []HomepageIntroductionAsset        `json:"assets"`
	TimelineItems []HomepageIntroductionTimelineItem `json:"timelineItems"`
}

type HomepageIntroduction struct {
	HomepageID     string                        `json:"homepageId"`
	DisplayName    string                        `json:"displayName"`
	HomepageType   string                        `json:"homepageType"`
	CoverURL       string                        `json:"coverUrl,omitempty"`
	Summary        string                        `json:"summary"`
	Sections       []HomepageIntroductionSection `json:"sections"`
	RelatedObjects []HomepageRelatedGroup        `json:"relatedObjects"`
	PrimarySource  *HomepageSource               `json:"primarySource,omitempty"`
	SourceURLs     []string                      `json:"sourceUrls"`
	UpdatedAt      string                        `json:"updatedAt"`
}

func (s *HomepageService) GetHomepageIntroduction(ctx context.Context, homepageID string) (*HomepageIntroduction, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.GetHomepageIntroduction",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	introduction := buildHomepageIntroduction(homepage)
	return &introduction, nil
}

func buildHomepageIntroduction(homepage *Homepage) HomepageIntroduction {
	if homepage == nil {
		return HomepageIntroduction{}
	}
	// 数据工程 page.md 三段结构投影优先；无正文时只投影真实主档字段。
	if strings.TrimSpace(homepage.IntroductionMarkdown) != "" {
		return buildIntroductionFromPageMarkdown(homepage)
	}
	summary := introductionSummary(homepage)
	sections := []HomepageIntroductionSection{}
	if overview := genericOverviewMarkdown(homepage); overview != "" {
		sections = append(sections, HomepageIntroductionSection{
			Kind:         "overview",
			Title:        "概况",
			BodyMarkdown: overview,
			Assets:       introductionAssets(homepage),
		})
	}
	if facts := introductionKeyFacts(homepage); facts != "" {
		sections = append(sections, HomepageIntroductionSection{
			Kind: "keyFacts", Title: "核心信息", BodyMarkdown: facts,
		})
	}
	return HomepageIntroduction{
		HomepageID:     homepage.ID,
		DisplayName:    homepage.Title,
		HomepageType:   homepage.HomepageType,
		CoverURL:       homepage.CoverURL,
		Summary:        summary,
		Sections:       sections,
		RelatedObjects: emptyRelatedGroups(homepage.RelatedGroups),
		PrimarySource:  homepage.PrimarySource,
		SourceURLs:     cloneStrings(homepage.SourceURLs),
		UpdatedAt:      homepage.UpdatedAt.UTC().Format(time.RFC3339),
	}
}

// buildIntroductionFromPageMarkdown 把数据工程 page.md（固定三段结构：frontmatter
// 封面 / 正文含 :::figure 块级内嵌图 / 页尾「## 相关图片」gallery）投影为
// introduction sections：正文章节 kind=body（bodyMarkdown 保留 figure 指令，
// assets 提供 role=inline 绑定），页尾章节 kind=relatedImages（assets 全部
// role=related，gallery 指令不下发）。
func buildIntroductionFromPageMarkdown(homepage *Homepage) HomepageIntroduction {
	assetByID := map[string]HomepageIntroductionAsset{}
	for _, asset := range homepage.IntroductionAssets {
		if strings.TrimSpace(asset.AssetID) != "" {
			assetByID[strings.TrimSpace(asset.AssetID)] = asset
		}
	}
	frontmatter, body := splitPageFrontmatter(homepage.IntroductionMarkdown)
	coverURL := strings.TrimSpace(homepage.CoverURL)
	if coverAssetID := frontmatterCoverAssetID(frontmatter); coverAssetID != "" {
		if asset, ok := assetByID[coverAssetID]; ok && strings.TrimSpace(asset.URL) != "" {
			coverURL = strings.TrimSpace(asset.URL)
		}
	}
	if coverURL == "" {
		coverURL = coverURLFromIntroductionAssets(homepage.IntroductionAssets)
	}

	lead, chapters := splitPageChapters(body)
	sections := make([]HomepageIntroductionSection, 0, len(chapters)+1)
	if strings.TrimSpace(lead) != "" {
		sections = append(sections, HomepageIntroductionSection{
			Kind:         "overview",
			Title:        "概况",
			BodyMarkdown: strings.TrimSpace(lead),
			Assets:       introductionSectionAssets(lead, assetByID, introductionAssetRoleInline),
		})
	}
	for _, chapter := range chapters {
		if chapter.title == relatedImagesHeading {
			assets := introductionSectionAssets(chapter.body, assetByID, introductionAssetRoleRelated)
			if len(assets) == 0 {
				continue
			}
			sections = append(sections, HomepageIntroductionSection{
				Kind:   "relatedImages",
				Title:  relatedImagesHeading,
				Assets: assets,
			})
			continue
		}
		sections = append(sections, HomepageIntroductionSection{
			Kind:         "body",
			Title:        chapter.title,
			BodyMarkdown: strings.TrimSpace(chapter.body),
			Assets:       introductionSectionAssets(chapter.body, assetByID, introductionAssetRoleInline),
		})
	}

	summary := strings.TrimSpace(homepage.Subtitle)
	if summary == "" {
		summary = firstParagraphSummary(lead)
	}
	if summary == "" {
		summary = introductionSummary(homepage)
	}
	return HomepageIntroduction{
		HomepageID:     homepage.ID,
		DisplayName:    homepage.Title,
		HomepageType:   homepage.HomepageType,
		CoverURL:       coverURL,
		Summary:        summary,
		Sections:       sections,
		RelatedObjects: emptyRelatedGroups(homepage.RelatedGroups),
		PrimarySource:  homepage.PrimarySource,
		SourceURLs:     cloneStrings(homepage.SourceURLs),
		UpdatedAt:      homepage.UpdatedAt.UTC().Format(time.RFC3339),
	}
}

const relatedImagesHeading = "相关图片"

var (
	assetRefLineRe = regexp.MustCompile(`(?m)^asset://(\S+)\s*$`)
	// 数据侧 asset_placement 的 gallery 规范形态：`:::gallery ids="a,b" layout="grid"`。
	galleryIDsAttrRe = regexp.MustCompile(`(?m)^:::gallery\b[^\n]*\bids="([^"]*)"`)
)

type pageChapter struct {
	title string
	body  string
}

// splitPageFrontmatter 分离 YAML frontmatter（若有），返回 (frontmatter, body)。
func splitPageFrontmatter(text string) (string, string) {
	if !strings.HasPrefix(text, "---\n") {
		return "", text
	}
	end := strings.Index(text[4:], "\n---\n")
	if end < 0 {
		return "", text
	}
	cut := 4 + end + len("\n---\n")
	return text[:cut], text[cut:]
}

func frontmatterCoverAssetID(frontmatter string) string {
	for _, line := range strings.Split(frontmatter, "\n") {
		trimmed := strings.TrimSpace(line)
		if !strings.HasPrefix(trimmed, "coverImage:") {
			continue
		}
		value := strings.TrimSpace(strings.TrimPrefix(trimmed, "coverImage:"))
		value = strings.Trim(value, `"'`)
		return strings.TrimPrefix(value, "asset://")
	}
	return ""
}

// splitPageChapters 按 `## ` 标题切分正文；返回导语（首个 `##` 之前，剥掉 H1）与章节列表。
func splitPageChapters(body string) (string, []pageChapter) {
	lines := strings.Split(body, "\n")
	var leadLines []string
	var chapters []pageChapter
	var current *pageChapter
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "## ") {
			if current != nil {
				chapters = append(chapters, *current)
			}
			current = &pageChapter{title: strings.TrimSpace(strings.TrimPrefix(trimmed, "## "))}
			continue
		}
		if current != nil {
			current.body += line + "\n"
			continue
		}
		if strings.HasPrefix(trimmed, "# ") {
			continue
		}
		leadLines = append(leadLines, line)
	}
	if current != nil {
		chapters = append(chapters, *current)
	}
	return strings.TrimSpace(strings.Join(leadLines, "\n")), chapters
}

// introductionSectionAssets 提取章节内资产引用并绑定资产元数据（按出现顺序去重）。
// 支持两种同源形态：figure 块内 `asset://<id>` 独立行，以及页尾 gallery 指令的
// `ids="a,b"` 属性（`_common/asset_placement.py` 的规范产物）。
func introductionSectionAssets(
	sectionBody string,
	assetByID map[string]HomepageIntroductionAsset,
	role string,
) []HomepageIntroductionAsset {
	var out []HomepageIntroductionAsset
	seen := map[string]bool{}
	appendAsset := func(assetID string) {
		assetID = strings.TrimSpace(assetID)
		if assetID == "" || seen[assetID] {
			return
		}
		seen[assetID] = true
		asset, ok := assetByID[assetID]
		if !ok || strings.TrimSpace(asset.URL) == "" {
			return
		}
		asset.Role = role
		out = append(out, asset)
	}
	type refGroup struct {
		index int
		ids   []string
	}
	var groups []refGroup
	for _, match := range assetRefLineRe.FindAllStringSubmatchIndex(sectionBody, -1) {
		groups = append(groups, refGroup{index: match[0], ids: []string{sectionBody[match[2]:match[3]]}})
	}
	for _, match := range galleryIDsAttrRe.FindAllStringSubmatchIndex(sectionBody, -1) {
		groups = append(groups, refGroup{index: match[0], ids: strings.Split(sectionBody[match[2]:match[3]], ",")})
	}
	sort.Slice(groups, func(i, j int) bool { return groups[i].index < groups[j].index })
	for _, group := range groups {
		for _, id := range group.ids {
			appendAsset(id)
		}
	}
	return out
}

func firstParagraphSummary(lead string) string {
	for _, paragraph := range strings.Split(lead, "\n\n") {
		text := strings.TrimSpace(paragraph)
		if text == "" || strings.HasPrefix(text, ":::") || strings.HasPrefix(text, "asset://") {
			continue
		}
		runes := []rune(text)
		if len(runes) > 120 {
			return string(runes[:120])
		}
		return text
	}
	return ""
}

func introductionSummary(homepage *Homepage) string {
	parts := []string{}
	if strings.TrimSpace(homepage.Subtitle) != "" {
		parts = append(parts, strings.TrimSpace(homepage.Subtitle))
	}
	if len(homepage.CategoryTags) > 0 {
		tags := homepage.CategoryTags
		if len(tags) > 3 {
			tags = tags[:3]
		}
		parts = append(parts, strings.Join(tags, "、"))
	}
	if strings.TrimSpace(homepage.City) != "" {
		parts = append(parts, strings.TrimSpace(homepage.City))
	}
	if len(parts) == 0 {
		return ""
	}
	return strings.Join(parts, " · ")
}

func genericOverviewMarkdown(homepage *Homepage) string {
	return introductionSummary(homepage)
}

func introductionAssets(homepage *Homepage) []HomepageIntroductionAsset {
	return cloneIntroductionAssets(homepage.IntroductionAssets)
}

func introductionKeyFacts(homepage *Homepage) string {
	lines := []string{}
	appendFact := func(label, value string) {
		if strings.TrimSpace(value) != "" {
			lines = append(lines, "- "+label+"："+strings.TrimSpace(value))
		}
	}
	appendFact("类型", homepage.HomepageType)
	appendFact("所在城市", homepage.City)
	appendFact("地址", homepage.Address)
	if len(homepage.CategoryTags) > 0 {
		appendFact("关键词", strings.Join(homepage.CategoryTags, "、"))
	}
	return strings.Join(lines, "\n")
}

func homepageSourceRefs(homepage *Homepage) []string {
	if homepage == nil {
		return nil
	}
	entity := strings.TrimSpace(homepage.CanonicalEntityID)
	refs := []string{"entity-service/homepage/" + homepage.ID}
	if entity != "" {
		refs = append(refs, entity)
	}
	return refs
}

func firstSourceRef(sourceRefs []string) string {
	if len(sourceRefs) == 0 {
		return ""
	}
	return sourceRefs[0]
}

func firstEntitySourceRef(sourceRefs []string) string {
	if len(sourceRefs) <= 1 {
		return firstSourceRef(sourceRefs)
	}
	return sourceRefs[1]
}

func publishedDateLabel(homepage *Homepage) string {
	if homepage != nil && homepage.PublishedAt != nil {
		return homepage.PublishedAt.UTC().Format("2006-01-02")
	}
	if homepage != nil {
		return homepage.UpdatedAt.UTC().Format("2006-01-02")
	}
	return ""
}
