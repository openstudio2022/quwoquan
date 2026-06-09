package search

import (
	"context"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Target is the AI/App-facing object name. It deliberately uses friendly names
// instead of internal object types so callers never reason about storage models.
type Target string

const (
	TargetArticle Target = "article"
	TargetPhoto   Target = "photo"
	TargetVideo   Target = "video"
	TargetUser    Target = "user"
	TargetEntity  Target = "entity"
	TargetCircle  Target = "circle"
	TargetGroup   Target = "group"
	TargetChat    Target = "chat"
)

// AllTargets is the frozen allowlist of AI-facing targets.
var AllTargets = []Target{
	TargetArticle, TargetPhoto, TargetVideo, TargetUser,
	TargetEntity, TargetCircle, TargetGroup, TargetChat,
}

func targetAllowed(t Target) bool {
	for _, a := range AllTargets {
		if a == t {
			return true
		}
	}
	return false
}

// TimeRange is the only time filter exposed in filters.
type TimeRange struct {
	From time.Time `json:"from,omitempty"`
	To   time.Time `json:"to,omitempty"`
}

// RetrieveFilters is a fixed, named filter group. It is intentionally NOT a
// free-form where clause.
type RetrieveFilters struct {
	Tags      []string   `json:"tags,omitempty"`
	TimeRange *TimeRange `json:"timeRange,omitempty"`
}

// PageRequest controls pagination.
type PageRequest struct {
	Limit  int    `json:"limit,omitempty"`
	Cursor string `json:"cursor,omitempty"`
}

// RetrieveRequest is the unified object retrieval contract shared by AI tools
// and the App. Match conditions are ids/names/terms; filters narrow the result.
// Relationships are inferred by the backend; callers never send type/relation.
type RetrieveRequest struct {
	Targets []Target        `json:"targets"`
	IDs     []string        `json:"ids,omitempty"`
	Names   []string        `json:"names,omitempty"`
	Terms   []string        `json:"terms,omitempty"`
	Filters RetrieveFilters `json:"filters,omitempty"`
	Page    PageRequest     `json:"page,omitempty"`
}

// Viewer carries the permission context. It is supplied by the service layer
// and never by the AI/App request body (visibility is implicit).
type Viewer struct {
	UserID         string
	IncludePrivate bool
	AllowedChatIDs map[string]bool
}

// RetrievePlan is the normalized, backend-agnostic representation of a request.
type RetrievePlan struct {
	Targets     []Target
	ObjectTypes []string
	IDs         []string
	Names       []string
	NormNames   []string
	Terms       []string
	Interpreted InterpretedQuery
	Tags        []string
	TimeRange   *TimeRange
	Limit       int
	Offset      int
	Viewer      Viewer
}

// WantsAny reports whether the plan targets include any of the given targets.
// Domain CandidateSources use it to skip work when their targets aren't requested.
func (p RetrievePlan) WantsAny(targets ...Target) bool {
	for _, want := range targets {
		for _, t := range p.Targets {
			if t == want {
				return true
			}
		}
	}
	return false
}

// RecallCandidate is what a backend returns; ranking/permission are applied by
// the shared CrossTypeRanker so backends stay thin.
type RecallCandidate struct {
	Document  Document
	BaseScore float64
	Source    string
}

// RetrieveHit is the standard, caller-agnostic result item.
type RetrieveHit struct {
	Target       Target         `json:"target"`
	ObjectID     string         `json:"objectId"`
	Title        string         `json:"title"`
	Snippet      string         `json:"snippet"`
	Score        float64        `json:"score"`
	MatchedTerms []string       `json:"matchedTerms,omitempty"`
	MatchedTags  []string       `json:"matchedTags,omitempty"`
	Evidence     []Evidence     `json:"evidence,omitempty"`
	Payload      map[string]any `json:"payload,omitempty"`
}

// RetrieveResponse is the unified response envelope.
type RetrieveResponse struct {
	Hits           []RetrieveHit   `json:"hits"`
	Citations      []Citation      `json:"citations"`
	Facets         []Facet         `json:"facets,omitempty"`
	DegradeSignals []DegradeSignal `json:"degradeSignals,omitempty"`
	Provenance     Provenance      `json:"provenance"`
}

// RecallBackend abstracts the recall engine. NativeStoreBackend is the launch
// default; ESBackend is the traffic-driven upgrade. Selection is transparent to
// callers.
type RecallBackend interface {
	Recall(ctx context.Context, plan RetrievePlan) ([]RecallCandidate, error)
	Name() string
}

// TargetForDocument resolves an internal Document to its AI-facing target.
func TargetForDocument(doc Document) Target {
	switch doc.ObjectType {
	case ObjectTypeContentPost:
		switch strings.ToLower(strings.TrimSpace(doc.ContentType)) {
		case "image", "photo":
			return TargetPhoto
		case "video":
			return TargetVideo
		default:
			return TargetArticle
		}
	case ObjectTypeUserProfile:
		return TargetUser
	case ObjectTypeEntityHomepage:
		return TargetEntity
	case ObjectTypeCircle:
		return TargetCircle
	case ObjectTypeCircleGroup:
		return TargetGroup
	case ObjectTypeChatMessage, ObjectTypeChatConversation, ObjectTypeChatContact:
		return TargetChat
	default:
		return ""
	}
}

// ObjectTypesForTargets maps AI targets back to internal object types so a
// backend can scope a store/index query.
func ObjectTypesForTargets(targets []Target) []string {
	seen := map[string]struct{}{}
	out := []string{}
	add := func(ot string) {
		if _, ok := seen[ot]; ok {
			return
		}
		seen[ot] = struct{}{}
		out = append(out, ot)
	}
	for _, t := range targets {
		switch t {
		case TargetArticle, TargetPhoto, TargetVideo:
			add(ObjectTypeContentPost)
		case TargetUser:
			add(ObjectTypeUserProfile)
		case TargetEntity:
			add(ObjectTypeEntityHomepage)
		case TargetCircle:
			add(ObjectTypeCircle)
		case TargetGroup:
			add(ObjectTypeCircleGroup)
		case TargetChat:
			add(ObjectTypeChatMessage)
			add(ObjectTypeChatConversation)
			add(ObjectTypeChatContact)
		}
	}
	return out
}

// PlanRequest validates and normalizes a RetrieveRequest into a RetrievePlan.
func PlanRequest(req RetrieveRequest, viewer Viewer) (RetrievePlan, []DegradeSignal) {
	degrade := []DegradeSignal{}
	targets := []Target{}
	for _, t := range req.Targets {
		t = Target(strings.ToLower(strings.TrimSpace(string(t))))
		if t == "" {
			continue
		}
		if !targetAllowed(t) {
			degrade = append(degrade, DegradeSignal{
				Code:    "SEARCH.PLANNER.unknown_target",
				Message: "忽略未知检索对象：" + string(t),
			})
			continue
		}
		targets = append(targets, t)
	}
	if len(targets) == 0 {
		targets = append(targets, AllTargets...)
	}

	terms := compactStrings(req.Terms)
	interpreted := Analyze(strings.Join(terms, " "), nil)

	limit := req.Page.Limit
	if limit <= 0 {
		limit = 20
	}
	offset := 0
	if c := strings.TrimSpace(req.Page.Cursor); c != "" {
		if v, err := strconv.Atoi(c); err == nil && v > 0 {
			offset = v
		}
	}

	plan := RetrievePlan{
		Targets:     targets,
		ObjectTypes: ObjectTypesForTargets(targets),
		IDs:         compactStrings(req.IDs),
		Names:       compactStrings(req.Names),
		NormNames:   compactStrings(normalizeAll(req.Names)),
		Terms:       terms,
		Interpreted: interpreted,
		Tags:        compactStrings(req.Filters.Tags),
		TimeRange:   req.Filters.TimeRange,
		Limit:       limit,
		Offset:      offset,
		Viewer:      viewer,
	}
	return plan, degrade
}

// Retrieve is the unified entrypoint. It runs the backend-agnostic pipeline:
// plan -> backend recall -> cross-type rank/merge -> permission gate -> envelope.
func Retrieve(ctx context.Context, req RetrieveRequest, backend RecallBackend, viewer Viewer) (RetrieveResponse, error) {
	provider := "native_store"
	if backend != nil {
		provider = backend.Name()
	}
	provenance := Provenance{
		Provider:     provider,
		IndexVersion: "retrieve-v1",
		GeneratedAt:  time.Now().UTC(),
	}

	safety := CheckQuerySafety(strings.Join(req.Terms, " "))
	if safety.Blocked {
		return RetrieveResponse{
			DegradeSignals: []DegradeSignal{{Code: safety.Code, Message: safety.Message}},
			Provenance:     provenance,
		}, nil
	}

	plan, degrade := PlanRequest(req, viewer)

	var candidates []RecallCandidate
	var err error
	if backend != nil {
		candidates, err = backend.Recall(ctx, plan)
		if err != nil {
			return RetrieveResponse{
				DegradeSignals: append(degrade, DegradeSignal{
					Code:    "SEARCH.BACKEND.recall_failed",
					Message: "检索后端暂不可用。",
				}),
				Provenance: provenance,
			}, err
		}
	}

	hits, facets := rankAndMerge(plan, candidates)
	return RetrieveResponse{
		Hits:           hits,
		Citations:      retrieveCitations(hits),
		Facets:         facets,
		DegradeSignals: degrade,
		Provenance:     provenance,
	}, nil
}

// rankAndMerge is the shared CrossTypeRanker + filter + permission gate.
func rankAndMerge(plan RetrievePlan, candidates []RecallCandidate) ([]RetrieveHit, []Facet) {
	targetSet := map[Target]struct{}{}
	for _, t := range plan.Targets {
		targetSet[t] = struct{}{}
	}
	hasMainCondition := len(plan.IDs) > 0 || len(plan.Names) > 0 || len(plan.Terms) > 0

	hits := make([]RetrieveHit, 0, len(candidates))
	facetCounts := map[string]int{}
	seen := map[string]struct{}{}

	for _, cand := range candidates {
		doc := cand.Document
		if strings.TrimSpace(doc.ObjectID) == "" || strings.TrimSpace(doc.ObjectType) == "" {
			continue
		}
		target := TargetForDocument(doc)
		if target == "" {
			continue
		}
		if _, ok := targetSet[target]; !ok {
			continue
		}
		// Permission gate (visibility is implicit, never from the request body).
		if !permitted(plan.Viewer, doc) {
			continue
		}
		// Hard filters: tags / timeRange.
		if !tagsPass(plan.Tags, doc) {
			continue
		}
		if !timeRangePass(plan.TimeRange, doc) {
			continue
		}

		base := cand.BaseScore
		var matchedField, snippet string
		var reasons []Reason
		var matchedTerms []string
		if len(plan.Terms) > 0 {
			var termScore float64
			termScore, matchedField, snippet, reasons = scoreDocument(plan.Interpreted, doc)
			matchedTerms = matchedTermsFor(plan, doc)
			if base <= 0 {
				base = termScore
			} else {
				base += termScore
			}
		}

		anchored, anchorBoost := anchorMatch(plan, doc)
		// A candidate must satisfy at least one provided main condition.
		if hasMainCondition {
			termMatched := base > 0 && len(plan.Terms) > 0
			if !termMatched && !anchored {
				continue
			}
		}

		score := base + anchorBoost
		if score <= 0 {
			// Discovery / anchor-only / no-condition path.
			score = 0.1 + popularityScore(doc.Popularity)
		}
		matchedTagList := matchedTagsFor(plan.Tags, doc)
		if len(matchedTagList) > 0 {
			score += 0.5 * float64(len(matchedTagList))
		}
		if !doc.Freshness.IsZero() {
			score += freshnessScore(doc.Freshness)
		}
		score += popularityScore(doc.Popularity)

		if snippet == "" {
			snippet = firstNonEmpty(doc.Summary, doc.Body, doc.Title)
		}
		if matchedField == "" {
			matchedField = "default"
		}
		_ = reasons

		key := doc.ObjectType + ":" + doc.ObjectID
		if _, dup := seen[key]; dup {
			continue
		}
		seen[key] = struct{}{}

		hits = append(hits, RetrieveHit{
			Target:       target,
			ObjectID:     doc.ObjectID,
			Title:        firstNonEmpty(doc.Title, doc.ObjectID),
			Snippet:      truncate(snippet, 180),
			Score:        score,
			MatchedTerms: matchedTerms,
			MatchedTags:  matchedTagList,
			Evidence:     []Evidence{{Field: matchedField, Snippet: truncate(snippet, 180)}},
			Payload:      fieldsToPayload(doc.Fields),
		})
		facetCounts[string(target)]++
	}

	sort.SliceStable(hits, func(i, j int) bool {
		if hits[i].Score == hits[j].Score {
			return hits[i].Title < hits[j].Title
		}
		return hits[i].Score > hits[j].Score
	})

	if plan.Offset > 0 {
		if plan.Offset >= len(hits) {
			hits = nil
		} else {
			hits = hits[plan.Offset:]
		}
	}
	if len(hits) > plan.Limit {
		hits = hits[:plan.Limit]
	}
	return hits, facetsFromCounts(facetCounts)
}

func fieldsToPayload(fields map[string]string) map[string]any {
	if len(fields) == 0 {
		return nil
	}
	out := make(map[string]any, len(fields))
	for k, v := range fields {
		out[k] = v
	}
	return out
}

func matchedTermsFor(plan RetrievePlan, doc Document) []string {
	out := []string{}
	haystack := normalize(strings.Join([]string{
		doc.Title, doc.Summary, doc.Body,
		strings.Join(doc.Tags, " "), strings.Join(doc.Entities, " "),
	}, " "))
	for _, term := range plan.Terms {
		if strings.Contains(haystack, normalize(term)) {
			out = append(out, term)
		}
	}
	return out
}

func matchedTagsFor(tags []string, doc Document) []string {
	if len(tags) == 0 {
		return nil
	}
	docTags := normalize(strings.Join(doc.Tags, " "))
	out := []string{}
	for _, tag := range tags {
		if strings.Contains(docTags, normalize(tag)) {
			out = append(out, tag)
		}
	}
	return out
}

func tagsPass(tags []string, doc Document) bool {
	if len(tags) == 0 {
		return true
	}
	return len(matchedTagsFor(tags, doc)) > 0
}

func timeRangePass(tr *TimeRange, doc Document) bool {
	if tr == nil {
		return true
	}
	if doc.Freshness.IsZero() {
		return false
	}
	if !tr.From.IsZero() && doc.Freshness.Before(tr.From) {
		return false
	}
	if !tr.To.IsZero() && doc.Freshness.After(tr.To) {
		return false
	}
	return true
}

// anchorMatch resolves flat ids/names against the document (id hit on the
// object itself, or anchor hit on a related object id/name) and returns a
// boost. This is where relationships are inferred without any caller-supplied
// type/relation.
func anchorMatch(plan RetrievePlan, doc Document) (bool, float64) {
	if len(plan.IDs) == 0 && len(plan.NormNames) == 0 {
		return false, 0
	}
	var boost float64
	matched := false

	for _, id := range plan.IDs {
		if id == "" {
			continue
		}
		if doc.ObjectID == id {
			matched = true
			boost += 5 // direct object id hit (detail read).
			continue
		}
		for _, v := range doc.Fields {
			if strings.TrimSpace(v) == id {
				matched = true
				boost += 3 // related-object id anchor.
				break
			}
		}
	}

	if len(plan.NormNames) > 0 {
		nameHaystacks := []string{
			normalize(doc.Title),
			normalize(doc.Fields["authorDisplayName"]),
			normalize(doc.Fields["authorName"]),
			normalize(doc.Fields["groupName"]),
			normalize(doc.Fields["entityName"]),
			normalize(doc.Fields["locationName"]),
		}
		for _, name := range plan.NormNames {
			if name == "" {
				continue
			}
			for i, h := range nameHaystacks {
				if h == "" {
					continue
				}
				if h == name {
					matched = true
					if i == 0 {
						boost += 3 // exact title/name hit.
					} else {
						boost += 2.5 // exact related-name anchor.
					}
					break
				}
				if strings.Contains(h, name) {
					matched = true
					boost += 1.5 // fuzzy/contains anchor.
					break
				}
			}
		}
	}
	return matched, boost
}

func permitted(viewer Viewer, doc Document) bool {
	if isPrivateVisibility(doc.Visibility) {
		if viewer.IncludePrivate {
			return true
		}
		// Chat objects require explicit viewer membership.
		if TargetForDocument(doc) == TargetChat {
			if viewer.AllowedChatIDs != nil {
				if viewer.AllowedChatIDs[doc.ObjectID] {
					return true
				}
				if conv := strings.TrimSpace(doc.Fields["conversationId"]); conv != "" && viewer.AllowedChatIDs[conv] {
					return true
				}
			}
		}
		return false
	}
	return true
}

func retrieveCitations(hits []RetrieveHit) []Citation {
	citations := make([]Citation, 0, len(hits))
	for _, hit := range hits {
		citations = append(citations, Citation{
			CitationID: citationID(string(hit.Target), hit.ObjectID),
			ObjectType: string(hit.Target),
			ObjectID:   hit.ObjectID,
			Title:      hit.Title,
			Snippet:    hit.Snippet,
			Score:      hit.Score,
		})
	}
	return citations
}

// HitMap renders a RetrieveHit to a JSON-ish map for tool/provider consumers.
func RetrieveHitMap(hit RetrieveHit) map[string]any {
	return map[string]any{
		"target":       string(hit.Target),
		"objectId":     hit.ObjectID,
		"title":        hit.Title,
		"snippet":      hit.Snippet,
		"score":        hit.Score,
		"matchedTerms": hit.MatchedTerms,
		"matchedTags":  hit.MatchedTags,
		"evidence":     evidenceToMaps(hit.Evidence),
		"payload":      hit.Payload,
	}
}
