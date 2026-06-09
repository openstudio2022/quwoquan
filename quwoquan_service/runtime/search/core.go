package search

import (
	"crypto/sha1"
	"encoding/hex"
	"regexp"
	"sort"
	"strings"
	"time"
	"unicode"
)

const (
	ObjectTypeWebDocument      = "web.document"
	ObjectTypeContentPost      = "content.post"
	ObjectTypeEntityHomepage   = "entity.homepage"
	ObjectTypeUserProfile      = "user.profile"
	ObjectTypeChatMessage      = "chat.message"
	ObjectTypeChatConversation = "chat.conversation"
	ObjectTypeChatContact      = "chat.contact"
	ObjectTypeCircleGroup      = "circle.group"
	ObjectTypeCircle           = "circle.circle"
	ObjectTypeTag              = "tag"
)

type SearchMode string

const (
	ModeSuggest   SearchMode = "suggest"
	ModeResult    SearchMode = "result"
	ModeRetrieval SearchMode = "retrieval"
)

type Document struct {
	ObjectType   string
	ObjectID     string
	Title        string
	Summary      string
	Body         string
	URL          string
	DeepLink     string
	SourceDomain string
	ContentType  string
	Visibility   string
	BadgeLabel   string
	Tags         []string
	Entities     []string
	Fields       map[string]string
	Popularity   float64
	Freshness    time.Time
}

type Request struct {
	Query          string
	Mode           SearchMode
	ObjectTypes    []string
	Limit          int
	IncludeWeb     bool
	IncludePrivate bool
	Context        map[string]string
}

type Response struct {
	QueryEcho        string
	InterpretedQuery InterpretedQuery
	Hits             []Hit
	Citations        []Citation
	Facets           []Facet
	DegradeSignals   []DegradeSignal
	Provenance       Provenance
}

type InterpretedQuery struct {
	Normalized          string
	Tokens              []string
	Variants            []string
	DetectedEntities    []string
	DetectedTags        []string
	SelectedObjectTypes []string
}

type Hit struct {
	ObjectType   string
	ObjectID     string
	Title        string
	Snippet      string
	URL          string
	DeepLink     string
	Score        float64
	SourceDomain string
	ContentType  string
	Visibility   string
	BadgeLabel   string
	MatchedField string
	Reasons      []Reason
	Evidence     []Evidence
}

type Citation struct {
	CitationID   string
	ObjectType   string
	ObjectID     string
	Title        string
	ContentType  string
	Snippet      string
	URL          string
	DeepLink     string
	BadgeLabel   string
	SourceDomain string
	Score        float64
}

type Reason struct {
	Code   string
	Label  string
	Weight float64
}

type Evidence struct {
	Field   string
	Snippet string
}

type Facet struct {
	Key   string
	Label string
	Count int
}

type DegradeSignal struct {
	Code       string
	Message    string
	ObjectType string
}

type Provenance struct {
	Provider     string
	IndexVersion string
	GeneratedAt  time.Time
}

type QuerySafety struct {
	Blocked bool
	Code    string
	Message string
}

var splitRe = regexp.MustCompile(`[\s[:punct:]~!@#$%^&*+=|\\<>{}\[\]、，。！？；：“”‘’（）【】《》]+`)

var synonymGroups = [][]string{
	{"旅游", "旅行", "出行", "游玩", "攻略", "路线"},
	{"露营", "营地", "户外"},
	{"民宿", "客栈", "酒店", "住宿"},
	{"圈子", "社群", "群组", "社区"},
	{"主页", "实体", "地点", "商家", "景点"},
	{"小趣", "助手", "assistant"},
	{"内容", "帖子", "文章", "post"},
}

var correctionMap = map[string]string{
	"泸营": "露营",
	"路营": "露营",
	"名宿": "民宿",
	"攻虐": "攻略",
	"小去": "小趣",
	"小区": "小趣",
}

var pinyinInitials = map[rune]string{
	'北': "b", '京': "j", '上': "s", '海': "h", '深': "s", '圳': "z",
	'广': "g", '州': "z", '杭': "h", '成': "c", '都': "d", '四': "s",
	'川': "c", '旅': "l", '游': "y", '行': "x", '攻': "g", '略': "l",
	'露': "l", '营': "y", '民': "m", '宿': "s", '圈': "q", '子': "z",
	'群': "q", '组': "z", '主': "z", '页': "y", '实': "s", '体': "t",
	'内': "n", '容': "r", '文': "w", '章': "z", '小': "x", '趣': "q",
}

var sensitiveTerms = []string{"赌博", "博彩", "诈骗", "外挂"}

func Analyze(query string, objectTypes []string) InterpretedQuery {
	normalized := normalize(query)
	for wrong, right := range correctionMap {
		normalized = strings.ReplaceAll(normalized, normalize(wrong), normalize(right))
	}
	tokens := tokenize(normalized)
	variants := expandVariants(normalized, tokens)
	return InterpretedQuery{
		Normalized:          normalized,
		Tokens:              tokens,
		Variants:            variants,
		DetectedEntities:    detectPrefixed(tokens, "entity:"),
		DetectedTags:        detectPrefixed(tokens, "tag:"),
		SelectedObjectTypes: compactStrings(objectTypes),
	}
}

func CheckQuerySafety(query string) QuerySafety {
	normalized := normalize(query)
	for _, term := range sensitiveTerms {
		if strings.Contains(normalized, normalize(term)) {
			return QuerySafety{
				Blocked: true,
				Code:    "SEARCH.USER.sensitive_query",
				Message: "搜索词包含受限内容，已停止检索。",
			}
		}
	}
	return QuerySafety{}
}

func Execute(req Request, docs []Document) Response {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	query := strings.TrimSpace(req.Query)
	interpreted := Analyze(query, req.ObjectTypes)
	provenance := Provenance{
		Provider:     "canonical_search",
		IndexVersion: "runtime-search-v1",
		GeneratedAt:  time.Now().UTC(),
	}
	safety := CheckQuerySafety(query)
	if safety.Blocked {
		return Response{
			QueryEcho:        query,
			InterpretedQuery: interpreted,
			DegradeSignals: []DegradeSignal{{
				Code:    safety.Code,
				Message: safety.Message,
			}},
			Provenance: provenance,
		}
	}

	allowedTypes := makeSet(req.ObjectTypes)
	hits := make([]Hit, 0, len(docs))
	facetCounts := map[string]int{}
	for _, doc := range docs {
		if strings.TrimSpace(doc.ObjectID) == "" || strings.TrimSpace(doc.ObjectType) == "" {
			continue
		}
		if len(allowedTypes) > 0 {
			if _, ok := allowedTypes[doc.ObjectType]; !ok {
				continue
			}
		}
		if !req.IncludePrivate && isPrivateVisibility(doc.Visibility) {
			continue
		}
		score, matchedField, snippet, reasons := scoreDocument(interpreted, doc)
		if query != "" && score <= 0 {
			continue
		}
		if query == "" {
			score = 0.1 + popularityScore(doc.Popularity)
			if matchedField == "" {
				matchedField = "default"
			}
			if snippet == "" {
				snippet = firstNonEmpty(doc.Summary, doc.Body, doc.Title)
			}
			reasons = append(reasons, Reason{Code: "default_discovery", Label: "默认发现", Weight: score})
		}
		hit := Hit{
			ObjectType:   doc.ObjectType,
			ObjectID:     doc.ObjectID,
			Title:        firstNonEmpty(doc.Title, doc.ObjectID),
			Snippet:      truncate(snippet, 180),
			URL:          doc.URL,
			DeepLink:     doc.DeepLink,
			Score:        score,
			SourceDomain: firstNonEmpty(doc.SourceDomain, doc.ObjectType),
			ContentType:  doc.ContentType,
			Visibility:   firstNonEmpty(doc.Visibility, "public"),
			BadgeLabel:   doc.BadgeLabel,
			MatchedField: matchedField,
			Reasons:      reasons,
			Evidence:     []Evidence{{Field: matchedField, Snippet: truncate(snippet, 180)}},
		}
		hits = append(hits, hit)
		facetCounts[doc.ObjectType]++
	}
	sort.SliceStable(hits, func(i, j int) bool {
		if hits[i].Score == hits[j].Score {
			return hits[i].Title < hits[j].Title
		}
		return hits[i].Score > hits[j].Score
	})
	if len(hits) > limit {
		hits = hits[:limit]
	}
	return Response{
		QueryEcho:        query,
		InterpretedQuery: interpreted,
		Hits:             hits,
		Citations:        citationsFromHits(hits),
		Facets:           facetsFromCounts(facetCounts),
		Provenance:       provenance,
	}
}

func ProviderHitMap(hit Hit) map[string]any {
	return map[string]any{
		"objectType":   hit.ObjectType,
		"objectId":     hit.ObjectID,
		"title":        hit.Title,
		"snippet":      hit.Snippet,
		"url":          hit.URL,
		"deepLink":     hit.DeepLink,
		"score":        hit.Score,
		"sourceDomain": hit.SourceDomain,
		"contentType":  hit.ContentType,
		"visibility":   hit.Visibility,
		"badgeLabel":   hit.BadgeLabel,
		"matchedField": hit.MatchedField,
		"reasons":      reasonsToMaps(hit.Reasons),
		"evidence":     evidenceToMaps(hit.Evidence),
	}
}

func CitationMap(c Citation) map[string]any {
	return map[string]any{
		"citationId":   c.CitationID,
		"objectType":   c.ObjectType,
		"objectId":     c.ObjectID,
		"title":        c.Title,
		"contentType":  c.ContentType,
		"snippet":      c.Snippet,
		"url":          c.URL,
		"deepLink":     c.DeepLink,
		"badgeLabel":   c.BadgeLabel,
		"sourceDomain": c.SourceDomain,
		"score":        c.Score,
	}
}

func scoreDocument(query InterpretedQuery, doc Document) (float64, string, string, []Reason) {
	if query.Normalized == "" {
		return 0, "", "", nil
	}
	fields := documentFields(doc)
	var bestScore float64
	bestField := ""
	bestSnippet := ""
	reasons := []Reason{}
	for _, field := range fields {
		value := normalize(field.value)
		if value == "" {
			continue
		}
		score := 0.0
		directMatch := false
		if strings.Contains(value, query.Normalized) {
			score += field.weight * 4
			directMatch = true
		}
		for _, token := range query.Tokens {
			if token == "" {
				continue
			}
			if strings.Contains(value, token) {
				score += field.weight
				directMatch = true
			}
		}
		initials := initials(field.value)
		for _, variant := range query.Variants {
			if variant == "" {
				continue
			}
			if strings.Contains(value, variant) {
				score += field.weight * 0.75
			}
			if initials != "" && strings.Contains(initials, variant) {
				score += field.weight * 1.2
				directMatch = true
			}
		}
		if !directMatch {
			score = 0
		}
		if score > 0 {
			score += popularityScore(doc.Popularity)
			if !doc.Freshness.IsZero() {
				score += freshnessScore(doc.Freshness)
			}
		}
		if score > bestScore {
			bestScore = score
			bestField = field.name
			bestSnippet = field.value
		}
	}
	if bestScore > 0 {
		reasons = append(reasons, Reason{
			Code:   "query_match",
			Label:  "命中" + bestField,
			Weight: bestScore,
		})
		if len(doc.Tags) > 0 || len(doc.Entities) > 0 {
			reasons = append(reasons, Reason{
				Code:   "tag_entity_signal",
				Label:  "标签/实体相关",
				Weight: 0.5,
			})
			bestScore += 0.5
		}
	}
	return bestScore, bestField, bestSnippet, reasons
}

type weightedField struct {
	name   string
	value  string
	weight float64
}

func documentFields(doc Document) []weightedField {
	fields := []weightedField{
		{name: "title", value: doc.Title, weight: 3.0},
		{name: "summary", value: doc.Summary, weight: 2.0},
		{name: "body", value: doc.Body, weight: 1.0},
		{name: "tags", value: strings.Join(doc.Tags, " "), weight: 2.2},
		{name: "entities", value: strings.Join(doc.Entities, " "), weight: 2.0},
	}
	for key, value := range doc.Fields {
		fields = append(fields, weightedField{name: key, value: value, weight: 1.5})
	}
	return fields
}

func tokenize(raw string) []string {
	parts := splitRe.Split(raw, -1)
	out := []string{}
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		out = append(out, part)
		if hasCJK(part) {
			rs := []rune(part)
			for i := range rs {
				out = append(out, string(rs[i]))
				if i+1 < len(rs) {
					out = append(out, string(rs[i:i+2]))
				}
			}
		}
	}
	return compactStrings(out)
}

func expandVariants(normalized string, tokens []string) []string {
	variants := []string{}
	for _, group := range synonymGroups {
		found := false
		for _, item := range group {
			if strings.Contains(normalized, normalize(item)) {
				found = true
				break
			}
		}
		if found {
			variants = append(variants, group...)
		}
	}
	if initial := initials(normalized); initial != "" {
		variants = append(variants, initial)
	}
	variants = append(variants, tokens...)
	return compactStrings(normalizeAll(variants))
}

func citationsFromHits(hits []Hit) []Citation {
	citations := make([]Citation, 0, len(hits))
	for _, hit := range hits {
		citations = append(citations, Citation{
			CitationID:   citationID(hit.ObjectType, hit.ObjectID),
			ObjectType:   hit.ObjectType,
			ObjectID:     hit.ObjectID,
			Title:        hit.Title,
			ContentType:  hit.ContentType,
			Snippet:      hit.Snippet,
			URL:          hit.URL,
			DeepLink:     hit.DeepLink,
			BadgeLabel:   hit.BadgeLabel,
			SourceDomain: hit.SourceDomain,
			Score:        hit.Score,
		})
	}
	return citations
}

func facetsFromCounts(counts map[string]int) []Facet {
	facets := make([]Facet, 0, len(counts))
	for key, count := range counts {
		facets = append(facets, Facet{Key: key, Label: key, Count: count})
	}
	sort.Slice(facets, func(i, j int) bool {
		if facets[i].Count == facets[j].Count {
			return facets[i].Key < facets[j].Key
		}
		return facets[i].Count > facets[j].Count
	})
	return facets
}

func reasonsToMaps(items []Reason) []map[string]any {
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		out = append(out, map[string]any{"code": item.Code, "label": item.Label, "weight": item.Weight})
	}
	return out
}

func evidenceToMaps(items []Evidence) []map[string]any {
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		out = append(out, map[string]any{"field": item.Field, "snippet": item.Snippet})
	}
	return out
}

func normalize(raw string) string {
	raw = strings.ToLower(strings.TrimSpace(raw))
	var b strings.Builder
	for _, r := range raw {
		if unicode.IsSpace(r) {
			b.WriteRune(' ')
			continue
		}
		if unicode.IsPunct(r) || unicode.IsSymbol(r) {
			b.WriteRune(' ')
			continue
		}
		b.WriteRune(r)
	}
	return strings.Join(strings.Fields(b.String()), " ")
}

func normalizeAll(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		out = append(out, normalize(value))
	}
	return out
}

func initials(raw string) string {
	var b strings.Builder
	for _, r := range raw {
		if value, ok := pinyinInitials[r]; ok {
			b.WriteString(value)
		} else if r <= unicode.MaxASCII && unicode.IsLetter(r) {
			b.WriteRune(unicode.ToLower(r))
		}
	}
	return b.String()
}

func hasCJK(raw string) bool {
	for _, r := range raw {
		if unicode.Is(unicode.Han, r) {
			return true
		}
	}
	return false
}

func compactStrings(values []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	return out
}

func makeSet(values []string) map[string]struct{} {
	set := map[string]struct{}{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			set[value] = struct{}{}
		}
	}
	return set
}

func detectPrefixed(tokens []string, prefix string) []string {
	out := []string{}
	for _, token := range tokens {
		if strings.HasPrefix(token, prefix) {
			out = append(out, strings.TrimPrefix(token, prefix))
		}
	}
	return compactStrings(out)
}

func isPrivateVisibility(value string) bool {
	value = strings.TrimSpace(strings.ToLower(value))
	return value == "private" || value == "secret"
}

func popularityScore(value float64) float64 {
	if value <= 0 {
		return 0
	}
	if value > 10000 {
		return 2
	}
	return value / 5000
}

func freshnessScore(t time.Time) float64 {
	age := time.Since(t)
	if age < 0 {
		return 0.2
	}
	switch {
	case age <= 24*time.Hour:
		return 0.6
	case age <= 7*24*time.Hour:
		return 0.3
	case age <= 30*24*time.Hour:
		return 0.1
	default:
		return 0
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func truncate(value string, maxRunes int) string {
	value = strings.TrimSpace(value)
	rs := []rune(value)
	if len(rs) <= maxRunes {
		return value
	}
	return string(rs[:maxRunes]) + "..."
}

func citationID(objectType, objectID string) string {
	sum := sha1.Sum([]byte(objectType + ":" + objectID))
	return objectType + "." + hex.EncodeToString(sum[:6])
}
