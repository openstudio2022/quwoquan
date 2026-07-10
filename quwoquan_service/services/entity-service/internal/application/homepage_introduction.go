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

type HomepageIntroductionAsset struct {
	AssetID   string `json:"assetId"`
	URL       string `json:"url"`
	Caption   string `json:"caption,omitempty"`
	Role      string `json:"role,omitempty"`
	SourceRef string `json:"sourceRef,omitempty"`
}

type HomepageIntroductionTimelineItem struct {
	DateLabel string `json:"dateLabel"`
	Text      string `json:"text"`
	AssetURL  string `json:"assetUrl,omitempty"`
	SourceRef string `json:"sourceRef,omitempty"`
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
	RelatedObjects []map[string]any              `json:"relatedObjects"`
	SourceRefs     []string                      `json:"sourceRefs"`
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
	// 数据工程 page.md 三段结构投影优先；无正文承载时回退合成 sections。
	if strings.TrimSpace(homepage.IntroductionMarkdown) != "" {
		return buildIntroductionFromPageMarkdown(homepage)
	}
	sourceRefs := homepageSourceRefs(homepage)
	summary := introductionSummary(homepage)
	keywords := strings.Join(homepage.CategoryTags, "、")
	if keywords == "" {
		keywords = "待补充"
	}
	sections := []HomepageIntroductionSection{
		{
			Kind:         "overview",
			Title:        "概况",
			BodyMarkdown: genericOverviewMarkdown(homepage),
			Assets:       introductionAssets(homepage),
		},
		{
			Kind:  "keyFacts",
			Title: "核心信息",
			BodyMarkdown: "- 类型：" + nonEmpty(homepage.HomepageType, "对象主页") +
				"\n- 所在城市：" + nonEmpty(homepage.City, "暂未登记") +
				"\n- 关键词：" + keywords +
				"\n- 主页状态：" + nonEmpty(homepage.Status, "整理中") +
				"\n- 最近更新时间：" + homepage.UpdatedAt.UTC().Format("2006-01-02 15:04 UTC"),
		},
		{
			Kind:  "timeline",
			Title: "时间线",
			BodyMarkdown: homepage.Title + " 的内容沉淀采用“来源进入 -> 内容补齐 -> 讨论聚合”的节奏推进。当前主页会把已发布内容、问答与关联对象都收敛在同一条对象语境中，方便后续的交集、相关推荐和主页治理继续沿着同一锚点扩展，而不是再分散到多个临时视图中。",
			TimelineItems: []HomepageIntroductionTimelineItem{
				{
					DateLabel: homepage.CreatedAt.UTC().Format("2006-01-02"),
					Text:      "主页创建，进入对象网络等待补齐基础信息与可信来源。",
					SourceRef: firstSourceRef(sourceRefs),
				},
				{
					DateLabel: publishedDateLabel(homepage),
					Text:      "主页发布后进入稳定对象承接链，允许内容、交集和对象页围绕统一 canonical 键继续沉淀。",
					SourceRef: firstEntitySourceRef(sourceRefs),
				},
			},
		},
		{
			Kind:  "history",
			Title: "整理与演进",
			BodyMarkdown: homepage.Title + " 的介绍页并不是一次性生成的静态说明，而是会随着主页状态、内容预览、问答预览和相关群组的补齐逐步演进。当前版本优先保证对象锚点、交集证据和可读摘要在同一真相源下闭环：对象页展示只读后端 bundle，交集证据只来自结构化 points，相关对象和内容预览也都通过主页自身的数据沉淀来扩展。这保证了后续无论是继续补内容、补时间线、还是补对象关系，都不需要重新引入本地 fallback 或多格式对象键。\n\n换句话说，这个介绍页承担的是“把对象长期整理清楚”的角色，而不是把临时结果堆成营销文案。只要一个主页后续又补入了新的作品、问答、群组或治理记录，这些增量都应该继续沿着同一条对象主线更新，而不是再派生出第二份对象定义。这样做的价值在于：对象页、交集卡、搜索命中、行为上报和助手上下文都能复用同一个 canonical 身份，后续增加任何内容维度时，也不会再被旧格式 entityRefs、空洞 summary fallback 或本地拼装的说明文本拖回多真相源状态。",
		},
	}
	return HomepageIntroduction{
		HomepageID:     homepage.ID,
		DisplayName:    homepage.Title,
		HomepageType:   homepage.HomepageType,
		CoverURL:       homepage.CoverURL,
		Summary:        summary,
		Sections:       sections,
		RelatedObjects: cloneObjectSlice(homepage.RelatedGroups),
		SourceRefs:     sourceRefs,
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
		RelatedObjects: cloneObjectSlice(homepage.RelatedGroups),
		SourceRefs:     homepageSourceRefs(homepage),
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
		return homepage.Title + " 的基础信息、内容和讨论正在持续整理中。"
	}
	return strings.Join(parts, " · ")
}

func genericOverviewMarkdown(homepage *Homepage) string {
	return introductionSummary(homepage) + "\n\n这个页面用于长期整理与 " + homepage.Title +
		" 相关的基础信息、内容、讨论和兴趣圈。随着更多真实内容与来源进入，介绍页会继续补充时间线、关键事实与相关对象。" +
		"\n\n为了避免对象语义漂移，这里默认把主页本身视为一个长期演进的对象入口：标题、摘要、内容预览、相关群组、更新时间和可追溯来源都要围绕同一个对象键汇聚，而不是在客户端通过多格式 entityRef 或临时拼装文案去兜底。这样无论是后续补充新的内容作品、用户问答、地点路线，还是让推荐链路继续往交集场景延展，都能保持对象锚点与展示语义的稳定。"
}

func introductionAssets(homepage *Homepage) []HomepageIntroductionAsset {
	if strings.TrimSpace(homepage.CoverURL) == "" {
		return nil
	}
	return []HomepageIntroductionAsset{
		{
			AssetID:   homepage.ID + "_cover",
			URL:       homepage.CoverURL,
			Caption:   homepage.Title + " 封面图",
			Role:      introductionAssetRoleCover,
			SourceRef: homepageSourceRefs(homepage)[0],
		},
	}
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
