package application

import (
	"context"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
)

type HomepageIntroductionAsset struct {
	AssetID   string `json:"assetId"`
	URL       string `json:"url"`
	Caption   string `json:"caption,omitempty"`
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
