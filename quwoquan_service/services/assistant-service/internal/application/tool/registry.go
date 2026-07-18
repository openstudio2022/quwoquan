package tool

import (
	"context"
	"fmt"
	"strings"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

type Request struct {
	ToolName string
	Input    map[string]any
	History  []string
}

type Result struct {
	Output map[string]any
}

type Handler func(context.Context, Request) (Result, error)

type Registry struct {
	metadata map[string]Metadata
	handlers map[string]Handler
}

func NewRegistry() Registry {
	return Registry{metadata: map[string]Metadata{}, handlers: map[string]Handler{}}
}

func (r Registry) IsZero() bool {
	return len(r.metadata) == 0 && len(r.handlers) == 0
}

func (r Registry) Metadata(toolName string) (Metadata, bool) {
	meta, ok := r.metadata[strings.TrimSpace(toolName)]
	return meta, ok
}

func (r Registry) ValidateInput(toolName string, input map[string]any) error {
	meta, ok := r.Metadata(toolName)
	if !ok {
		return fmt.Errorf("tool %q is not registered", toolName)
	}
	return validateKeys(input, meta.RequiredInputKeys, "input")
}

func (r *Registry) Register(meta Metadata, handler Handler) {
	if r.metadata == nil {
		r.metadata = map[string]Metadata{}
	}
	if r.handlers == nil {
		r.handlers = map[string]Handler{}
	}
	r.metadata[meta.ToolName] = meta
	r.handlers[meta.ToolName] = handler
}

func (r Registry) Execute(ctx context.Context, req Request) (Result, error) {
	meta, ok := r.metadata[req.ToolName]
	if !ok {
		return Result{}, fmt.Errorf("tool %q is not registered", req.ToolName)
	}
	if err := validateKeys(req.Input, meta.RequiredInputKeys, "input"); err != nil {
		return Result{}, err
	}
	if err := detectLoop(req.ToolName, req.History, meta.Resilience.LoopDetectionWindow); err != nil {
		return Result{}, err
	}
	handler, ok := r.handlers[req.ToolName]
	if !ok {
		return Result{}, fmt.Errorf("tool %q has no handler", req.ToolName)
	}
	result, err := handler(ctx, req)
	if err != nil {
		return Result{}, err
	}
	if err := validateKeys(result.Output, meta.RequiredOutputKeys, "output"); err != nil {
		return Result{}, err
	}
	return result, nil
}

func validateKeys(values map[string]any, keys []string, label string) error {
	for _, key := range keys {
		if _, ok := values[key]; !ok {
			return fmt.Errorf("tool %s missing required key %q", label, key)
		}
	}
	return nil
}

func detectLoop(toolName string, history []string, window int) error {
	if window <= 0 || len(history) < window {
		return nil
	}
	count := 0
	for i := len(history) - 1; i >= 0 && len(history)-i <= window; i-- {
		if history[i] == toolName {
			count++
		}
	}
	if count >= window {
		return fmt.Errorf("tool %q loop detected", toolName)
	}
	return nil
}

func DefaultRegistry() Registry {
	registry := NewRegistry()
	registry.Register(DefaultMetadata("mock_search"), func(_ context.Context, req Request) (Result, error) {
		return Result{Output: map[string]any{
			"summary": fmt.Sprintf("mock_search 已围绕“%v”返回 2 条模拟线索", req.Input["query"]),
			"items": []map[string]any{
				{"title": "模拟线索 A", "snippet": "用于验证云端 ReAct 工具观察。"},
				{"title": "模拟线索 B", "snippet": "用于验证最终回答可引用工具结果。"},
			},
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "web_search",
		DisplayName:        "网络搜索",
		Description:        "检索公开网络信息的云端工具，作为 canonical search 的 web.document provider scope。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"provider", "summary", "references"},
		Resilience:         DefaultMetadata("web_search").Resilience,
		Recovery:           DefaultMetadata("web_search").Recovery,
	}, func(_ context.Context, req Request) (Result, error) {
		resp := executeCanonicalToolSearch(req, []string{rtsearch.ObjectTypeWebDocument}, true)
		return Result{Output: map[string]any{
			"provider":   resp.Provenance.Provider,
			"summary":    summarizeCanonicalSearch(resp),
			"references": citationMaps(resp.Citations),
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "search",
		DisplayName:        "统一搜索",
		Description:        "统一对象检索：targets 指定业务对象，ids/names/terms 为主匹配条件，filters(tags,timeRange) 收窄；不接受 query/mode/type/relation。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  nil,
		RequiredOutputKeys: []string{"provider", "summary", "references", "coverage", "confidence", "freshnessHours"},
		Resilience:         DefaultMetadata("search").Resilience,
		Recovery:           DefaultMetadata("search").Recovery,
	}, func(ctx context.Context, req Request) (Result, error) {
		resp := executeRetrieveToolSearch(ctx, req, rtsearch.AllTargets)
		return Result{Output: map[string]any{
			"provider":       resp.Provenance.Provider,
			"summary":        summarizeRetrieve(resp),
			"coverage":       retrieveCoverage(resp),
			"confidence":     retrieveConfidence(resp),
			"freshnessHours": 12,
			"references":     citationMaps(resp.Citations),
			"hits":           retrieveHitMaps(resp.Hits),
			"degradeSignals": degradeMaps(resp.DegradeSignals),
			"provenance":     provenanceMap(resp.Provenance),
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "web_fetch",
		DisplayName:        "网页抓取",
		Description:        "抓取指定公开网页并返回可摘要正文。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"provider", "summary", "content", "coverage", "confidence", "freshnessHours"},
		Resilience:         DefaultMetadata("web_fetch").Resilience,
		Recovery:           DefaultMetadata("web_fetch").Recovery,
	}, func(_ context.Context, req Request) (Result, error) {
		query := fmt.Sprint(req.Input["query"])
		return Result{Output: map[string]any{
			"provider":       "fake_web_fetch",
			"summary":        fmt.Sprintf("web_fetch 已抓取“%s”的公开页面摘要", query),
			"content":        "模拟网页正文，用于云侧 ReAct 证据消化与引用。",
			"coverage":       0.74,
			"confidence":     0.72,
			"freshnessHours": 24,
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "memory_search",
		DisplayName:        "记忆检索",
		Description:        "检索用户授权范围内的助手记忆与最近上下文。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"summary", "memories", "coverage", "confidence", "freshnessHours"},
		Resilience:         DefaultMetadata("memory_search").Resilience,
		Recovery:           DefaultMetadata("memory_search").Recovery,
	}, func(_ context.Context, req Request) (Result, error) {
		query := fmt.Sprint(req.Input["query"])
		return Result{Output: map[string]any{
			"summary":        fmt.Sprintf("memory_search 已围绕“%s”返回授权记忆摘要", query),
			"coverage":       0.68,
			"confidence":     0.7,
			"freshnessHours": 48,
			"memories": []map[string]any{
				{"memoryId": "mem_fake_1", "snippet": "最近关注天气、出行和工作安排。"},
			},
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "app_search",
		DisplayName:        "应用信息检索",
		Description:        "检索趣我圈站内 article/photo/video/user/entity/circle/group/chat 对象；用 targets+ids/names/terms+filters，不接受 query/mode/type/relation。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  nil,
		RequiredOutputKeys: []string{"summary", "results"},
		Resilience:         DefaultMetadata("app_search").Resilience,
		Recovery:           DefaultMetadata("app_search").Recovery,
	}, func(ctx context.Context, req Request) (Result, error) {
		resp := executeRetrieveToolSearch(ctx, req, []rtsearch.Target{
			rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo,
			rtsearch.TargetUser, rtsearch.TargetEntity,
			rtsearch.TargetCircle, rtsearch.TargetGroup, rtsearch.TargetChat,
		})
		return Result{Output: map[string]any{
			"summary":        summarizeRetrieve(resp),
			"results":        retrieveHitMaps(resp.Hits),
			"citations":      citationMaps(resp.Citations),
			"degradeSignals": degradeMaps(resp.DegradeSignals),
			"provenance":     provenanceMap(resp.Provenance),
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:             "app_action",
		DisplayName:          "应用操作",
		Description:          "向端侧提出应用动作 proposal，必须由端侧确认后执行。",
		Placement:            PlacementDeviceAction,
		RequiredInputKeys:    []string{"actionType"},
		RequiresConfirmation: true,
		Resilience:           DefaultMetadata("app_action").Resilience,
		Recovery: RecoveryPolicy{
			Action:             "request_confirmation",
			DisruptionLevel:    "permissionCard",
			UserVisibleSummary: "需要用户确认后执行本机动作",
		},
	}, nil)
	for _, meta := range []Metadata{
		deviceProposalMetadata("scheduler", "日程调度", "向端侧提出日程、待办或提醒 proposal。"),
		deviceProposalMetadata("deep_link", "深链跳转", "向端侧提出打开应用内或外部目标的 proposal。"),
		deviceProposalMetadata("intent_bridge", "意图桥接", "向端侧提出系统 intent 或平台能力 proposal。"),
	} {
		registry.Register(meta, nil)
	}
	return registry
}

func executeCanonicalToolSearch(req Request, objectTypes []string, includeWeb bool) rtsearch.Response {
	query := fmt.Sprint(req.Input["query"])
	limit := 8
	if raw, ok := req.Input["limit"]; ok {
		if parsed, ok := raw.(int); ok && parsed > 0 {
			limit = parsed
		}
	}
	return rtsearch.Execute(rtsearch.Request{
		Query:       query,
		Mode:        rtsearch.ModeRetrieval,
		ObjectTypes: objectTypes,
		Limit:       limit,
		IncludeWeb:  includeWeb,
	}, canonicalToolDocuments(query))
}

func canonicalToolDocuments(query string) []rtsearch.Document {
	return []rtsearch.Document{
		{
			ObjectType:   rtsearch.ObjectTypeWebDocument,
			ObjectID:     "web_quwoquan_search_" + stableSuffix(query),
			Title:        "公开网页检索结果：" + query,
			Summary:      "来自 web.document provider 的公开网页线索，可与站内对象一起作为小趣回答 citation。",
			URL:          "https://quwoquan.app/search?q=" + strings.ReplaceAll(strings.TrimSpace(query), " ", "+"),
			SourceDomain: "web",
			ContentType:  "webpage",
			Visibility:   "public",
			BadgeLabel:   "网页",
			Fields: map[string]string{
				"provider": "web.document",
			},
		},
		{
			ObjectType:   rtsearch.ObjectTypeContentPost,
			ObjectID:     "content_search_" + stableSuffix(query),
			Title:        "站内内容线索：" + query,
			Summary:      "来自 content.post provider 的内容、标题、摘要、标签和实体召回结果。",
			DeepLink:     "quwoquan://content/post/content_search_" + stableSuffix(query),
			SourceDomain: "content",
			ContentType:  "post",
			Visibility:   "public",
			BadgeLabel:   "内容",
			Tags:         []string{"Topic/搜索", "小趣"},
		},
		{
			ObjectType:   rtsearch.ObjectTypeEntityHomepage,
			ObjectID:     "entity_search_" + stableSuffix(query),
			Title:        "相关实体主页：" + query,
			Summary:      "来自 entity.homepage provider 的地点、品牌、景点或共享主页线索。",
			DeepLink:     "quwoquan://homepages/entity_search_" + stableSuffix(query),
			SourceDomain: "entity",
			ContentType:  "homepage",
			Visibility:   "public",
			BadgeLabel:   "主页",
			Entities:     []string{"entity:" + query},
		},
		{
			ObjectType:   rtsearch.ObjectTypeCircleGroup,
			ObjectID:     "group_search_" + stableSuffix(query),
			Title:        "相关群组：" + query,
			Summary:      "来自 circle.group provider 的圈子群组线索，支持云优先和本地回退。",
			DeepLink:     "quwoquan://circle/group_search_" + stableSuffix(query),
			SourceDomain: "circle",
			ContentType:  "group",
			Visibility:   "public",
			BadgeLabel:   "群组",
			Tags:         []string{"圈子", "群组"},
		},
	}
}

// executeRetrieveToolSearch runs the unified retrieve contract for the cloud
// search/app_search tools. AI input is targets/ids/names/terms/filters only.
func executeRetrieveToolSearch(ctx context.Context, req Request, defaults []rtsearch.Target) rtsearch.RetrieveResponse {
	rreq := parseRetrieveToolRequest(req, defaults)
	display := retrieveDisplayQuery(rreq)
	backend := rtsearch.NewSliceBackend(canonicalRetrieveToolDocuments(display))
	resp, _ := rtsearch.Retrieve(ctx, rreq, backend, rtsearch.Viewer{})
	return resp
}

func parseRetrieveToolRequest(req Request, defaults []rtsearch.Target) rtsearch.RetrieveRequest {
	in := req.Input
	targets := []rtsearch.Target{}
	for _, t := range toStringSliceInput(in["targets"]) {
		if rt := rtsearch.Target(strings.ToLower(strings.TrimSpace(t))); rt != "" {
			targets = append(targets, rt)
		}
	}
	if len(targets) == 0 {
		targets = defaults
	}
	terms := toStringSliceInput(in["terms"])
	var filters rtsearch.RetrieveFilters
	if raw, ok := in["filters"].(map[string]any); ok {
		filters.Tags = toStringSliceInput(raw["tags"])
		if tr, ok := raw["timeRange"].(map[string]any); ok {
			filters.TimeRange = parseRetrieveTimeRange(tr)
		}
	}
	limit := 8
	if raw, ok := in["limit"]; ok {
		if n, ok := raw.(int); ok && n > 0 {
			limit = n
		} else if f, ok := raw.(float64); ok && f > 0 {
			limit = int(f)
		}
	}
	return rtsearch.RetrieveRequest{
		Targets: targets,
		IDs:     toStringSliceInput(in["ids"]),
		Names:   toStringSliceInput(in["names"]),
		Terms:   terms,
		Filters: filters,
		Page:    rtsearch.PageRequest{Limit: limit},
	}
}

func parseRetrieveTimeRange(raw map[string]any) *rtsearch.TimeRange {
	tr := &rtsearch.TimeRange{}
	if v, ok := raw["from"].(string); ok {
		if ts, err := time.Parse(time.RFC3339, strings.TrimSpace(v)); err == nil {
			tr.From = ts
		}
	}
	if v, ok := raw["to"].(string); ok {
		if ts, err := time.Parse(time.RFC3339, strings.TrimSpace(v)); err == nil {
			tr.To = ts
		}
	}
	if tr.From.IsZero() && tr.To.IsZero() {
		return nil
	}
	return tr
}

func toStringSliceInput(v any) []string {
	switch t := v.(type) {
	case []string:
		return t
	case []any:
		out := make([]string, 0, len(t))
		for _, e := range t {
			if s := strings.TrimSpace(fmt.Sprint(e)); s != "" && s != "<nil>" {
				out = append(out, s)
			}
		}
		return out
	case string:
		if s := strings.TrimSpace(t); s != "" {
			return []string{s}
		}
	}
	return nil
}

func splitRetrieveTerms(query string) []string {
	query = strings.TrimSpace(query)
	if query == "" {
		return nil
	}
	terms := []string{query}
	for _, token := range strings.Fields(query) {
		if token != "" && token != query {
			terms = append(terms, token)
		}
	}
	return terms
}

func retrieveDisplayQuery(req rtsearch.RetrieveRequest) string {
	if len(req.Terms) > 0 {
		return strings.Join(req.Terms, " ")
	}
	if len(req.Names) > 0 {
		return strings.Join(req.Names, " ")
	}
	if len(req.IDs) > 0 {
		return strings.Join(req.IDs, " ")
	}
	return "趣我圈"
}

func canonicalRetrieveToolDocuments(query string) []rtsearch.Document {
	suffix := stableSuffix(query)
	return []rtsearch.Document{
		{
			ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "content_search_" + suffix,
			Title: "站内内容线索：" + query, Summary: "来自内容 provider 的文章、图文召回结果。",
			DeepLink:     "quwoquan://content/post/content_search_" + suffix,
			SourceDomain: "content", ContentType: "article", Visibility: "public", BadgeLabel: "内容",
			Tags: []string{"小趣", "搜索"},
		},
		{
			ObjectType: rtsearch.ObjectTypeEntityHomepage, ObjectID: "entity_search_" + suffix,
			Title: "相关实体主页：" + query, Summary: "来自实体 provider 的地点、品牌、景点线索。",
			DeepLink:     "quwoquan://homepages/entity_search_" + suffix,
			SourceDomain: "entity", Visibility: "public", BadgeLabel: "主页",
			Entities: []string{"entity:" + query},
		},
		{
			ObjectType: rtsearch.ObjectTypeCircleGroup, ObjectID: "group_search_" + suffix,
			Title: "相关群组：" + query, Summary: "来自圈子 provider 的群组线索。",
			DeepLink:     "quwoquan://circle/group_search_" + suffix,
			SourceDomain: "circle", Visibility: "public", BadgeLabel: "群组",
		},
		{
			ObjectType: rtsearch.ObjectTypeUserProfile, ObjectID: "user_search_" + suffix,
			Title: "相关用户：" + query, Summary: "来自用户 provider 的创作者公开资料。",
			SourceDomain: "user", Visibility: "public", BadgeLabel: "用户",
		},
	}
}

func summarizeRetrieve(resp rtsearch.RetrieveResponse) string {
	if len(resp.DegradeSignals) > 0 && len(resp.Hits) == 0 {
		return resp.DegradeSignals[0].Message
	}
	return fmt.Sprintf("retrieve 已返回 %d 条可引用结果", len(resp.Hits))
}

func retrieveHitMaps(items []rtsearch.RetrieveHit) []map[string]any {
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		out = append(out, rtsearch.RetrieveHitMap(item))
	}
	return out
}

func retrieveCoverage(resp rtsearch.RetrieveResponse) float64 {
	if len(resp.Hits) == 0 {
		return 0
	}
	coverage := 0.4 + 0.1*float64(len(resp.Hits))
	if coverage > 0.95 {
		coverage = 0.95
	}
	return coverage
}

func retrieveConfidence(resp rtsearch.RetrieveResponse) float64 {
	if len(resp.Hits) == 0 {
		return 0
	}
	confidence := 0.5 + 0.08*float64(len(resp.Hits))
	if confidence > 0.92 {
		confidence = 0.92
	}
	return confidence
}

func summarizeCanonicalSearch(resp rtsearch.Response) string {
	if len(resp.DegradeSignals) > 0 && len(resp.Hits) == 0 {
		return resp.DegradeSignals[0].Message
	}
	return fmt.Sprintf("canonical search 已围绕“%s”返回 %d 条可引用结果", resp.QueryEcho, len(resp.Hits))
}

func citationMaps(items []rtsearch.Citation) []map[string]any {
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		out = append(out, rtsearch.CitationMap(item))
	}
	return out
}

func degradeMaps(items []rtsearch.DegradeSignal) []map[string]any {
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		out = append(out, map[string]any{"code": item.Code, "message": item.Message, "objectType": item.ObjectType})
	}
	return out
}

func provenanceMap(item rtsearch.Provenance) map[string]any {
	return map[string]any{
		"provider":     item.Provider,
		"indexVersion": item.IndexVersion,
		"generatedAt":  item.GeneratedAt.Format("2006-01-02T15:04:05Z07:00"),
	}
}

func stableSuffix(query string) string {
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

func deviceProposalMetadata(toolName, displayName, description string) Metadata {
	meta := DefaultMetadata(toolName)
	meta.DisplayName = displayName
	meta.Description = description
	meta.Placement = PlacementDeviceAction
	meta.RequiredInputKeys = []string{"query"}
	meta.RequiredOutputKeys = nil
	meta.RequiresConfirmation = true
	meta.Recovery = RecoveryPolicy{
		Action:             "request_confirmation",
		DisruptionLevel:    "permissionCard",
		UserVisibleSummary: "需要用户确认后执行本机动作",
	}
	return meta
}
