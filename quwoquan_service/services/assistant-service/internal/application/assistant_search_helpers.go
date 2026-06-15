package application

import (
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

func assistantRetrieveDocuments(query string) []rtsearch.Document {
	suffix := stableAssistantSearchSuffix(query)
	return []rtsearch.Document{
		{
			ObjectType:   rtsearch.ObjectTypeContentPost,
			ObjectID:     "post_" + suffix,
			Title:        "相关内容：" + query,
			Summary:      "内容 provider 返回文章、图文与标签实体证据，可作为小趣 citation。",
			SourceDomain: "content",
			ContentType:  "article",
			Visibility:   "public",
			BadgeLabel:   "内容",
			Tags:         []string{"小趣", "搜索", "Topic/内容"},
		},
		{
			ObjectType:   rtsearch.ObjectTypeEntityHomepage,
			ObjectID:     "homepage_" + suffix,
			Title:        "相关实体：" + query,
			Summary:      "实体主页 provider 返回地点、品牌、景点或共享主页上下文。",
			SourceDomain: "entity",
			Visibility:   "public",
			BadgeLabel:   "主页",
			Entities:     []string{"entity:" + query},
		},
		{
			ObjectType:   rtsearch.ObjectTypeCircleGroup,
			ObjectID:     "group_" + suffix,
			Title:        "相关群组：" + query,
			Summary:      "群组 provider 提供圈子/群组线索，后续可接 remote + local fallback。",
			SourceDomain: "circle",
			Visibility:   "public",
			BadgeLabel:   "群组",
			Tags:         []string{"圈子", "群组"},
		},
		{
			ObjectType:   rtsearch.ObjectTypeUserProfile,
			ObjectID:     "user_" + suffix,
			Title:        "相关用户：" + query,
			Summary:      "用户 provider 返回创作者公开资料，可作为关注或私信线索。",
			SourceDomain: "user",
			Visibility:   "public",
			BadgeLabel:   "用户",
		},
	}
}

// assistantQueryTerms splits the natural-language query into a search-engine
// style keyword sequence while keeping the whole query as a coarse term.
func assistantQueryTerms(query string) []string {
	query = strings.TrimSpace(query)
	if query == "" {
		return nil
	}
	terms := []string{query}
	for _, token := range strings.Fields(query) {
		token = strings.TrimSpace(token)
		if token != "" && token != query {
			terms = append(terms, token)
		}
	}
	return terms
}

func assistantWebSupplementCitation(query string) assistant.AssistantSearchCitationView {
	suffix := stableAssistantSearchSuffix(query)
	return assistant.AssistantSearchCitationView{
		CitationID:    "cite_web_" + suffix,
		ObjectType:    "web",
		ObjectID:      "web_" + suffix,
		Title:         "公开网页线索：" + query,
		Snippet:       "外部网页作为 citation 补充，由 planner 决定是否引用，不作为业务对象 target。",
		URL:           "https://quwoquan.app/search?q=" + strings.ReplaceAll(strings.TrimSpace(query), " ", "+"),
		BadgeLabel:    "网页",
		SourceDomain:  "web",
		Score:         0.5,
		RecallSource:  "web_supplement",
		ObjectTypeRef: "web",
	}
}

func assistantTargetBadge(target rtsearch.Target) string {
	switch target {
	case rtsearch.TargetArticle:
		return "文章"
	case rtsearch.TargetPhoto:
		return "图文"
	case rtsearch.TargetVideo:
		return "视频"
	case rtsearch.TargetUser:
		return "用户"
	case rtsearch.TargetEntity:
		return "主页"
	case rtsearch.TargetCircle:
		return "圈子"
	case rtsearch.TargetGroup:
		return "群组"
	case rtsearch.TargetChat:
		return "聊天"
	default:
		return "对象"
	}
}

func assistantTargetDomain(target rtsearch.Target) string {
	switch target {
	case rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo:
		return "content"
	case rtsearch.TargetUser:
		return "user"
	case rtsearch.TargetEntity:
		return "entity"
	case rtsearch.TargetCircle, rtsearch.TargetGroup:
		return "circle"
	case rtsearch.TargetChat:
		return "messages"
	default:
		return "search"
	}
}

func stableAssistantSearchSuffix(query string) string {
	query = strings.TrimSpace(strings.ToLower(query))
	if query == "" {
		return "default"
	}
	replacer := strings.NewReplacer(" ", "_", "/", "_", "\\", "_", "?", "_", "&", "_")
	value := replacer.Replace(query)
	runes := []rune(value)
	if len(runes) > 24 {
		value = string(runes[:24])
	}
	return value
}
