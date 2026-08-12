package search

import (
	"context"
	"math"
	"net/url"
	"sort"
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
	// TargetLocation is the first-party place object (R-S05e). It reuses the
	// cross-object geo dimension; see ObjectTypeLocation.
	TargetLocation Target = "location"
)

// AllTargets is the allowlist of AI-facing targets.
var AllTargets = []Target{
	TargetArticle, TargetPhoto, TargetVideo, TargetUser,
	TargetEntity, TargetCircle, TargetGroup, TargetChat, TargetLocation,
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

// GeoNear expresses an "附近" (nearby) constraint: candidates within RadiusKm of
// the (Lat,Lng) pin. It is a CROSS-OBJECT filter — any Document that carries a
// Geo dimension participates regardless of its target (entity/content today,
// user/circle next). Semantics are a HARD radius filter: when Near is set with
// RadiusKm > 0, candidates without Geo are excluded and candidates outside the
// radius are dropped; survivors are proximity-weighted (closer ranks higher).
type GeoNear struct {
	Lat      float64 `json:"lat"`
	Lng      float64 `json:"lng"`
	RadiusKm float64 `json:"radiusKm"`
}

// Active reports whether the near filter should be applied. A zero/negative
// radius is treated as "no nearby constraint" so callers can pass an empty pin.
func (g *GeoNear) Active() bool { return g != nil && g.RadiusKm > 0 }

// RetrieveFilters is a fixed, named filter group. It is intentionally NOT a
// free-form where clause.
type RetrieveFilters struct {
	Tags      []string   `json:"tags,omitempty"`
	TimeRange *TimeRange `json:"timeRange,omitempty"`
	// Near is the optional geo radius ("附近") filter; it spans all targets with
	// a Geo dimension and is the single entry point for proximity retrieval.
	Near *GeoNear `json:"near,omitempty"`
}

// PageRequest controls pagination.
type PageRequest struct {
	Limit  int    `json:"limit,omitempty"`
	Cursor string `json:"cursor,omitempty"`
	// Offset is internal execution state decoded from an owner-sealed cursor.
	// It is never accepted from or serialized to an external caller.
	Offset int `json:"-"`
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
	Near        *GeoNear
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
	ObjectType   string         `json:"objectType"`
	ObjectID     string         `json:"objectId"`
	Title        string         `json:"title"`
	Snippet      string         `json:"snippet"`
	Score        float64        `json:"score"`
	MatchedTerms []string       `json:"matchedTerms,omitempty"`
	MatchedTags  []string       `json:"matchedTags,omitempty"`
	Evidence     []Evidence     `json:"evidence,omitempty"`
	Payload      map[string]any `json:"payload,omitempty"`
	// DeepLink / ThumbnailURL are internal flat-card projection inputs. They are
	// deliberately excluded from RetrieveHit JSON: the public REST wire remains
	// owned by search-service, while owner-query projection may expose only the
	// canonical DeepLink and the bounded thumbnail/cover fields.
	DeepLink     string `json:"-"`
	ThumbnailURL string `json:"-"`
	// Location dimension (cross-object): Geo/PlaceName surface the candidate's
	// structured place when present; DistanceKm is populated only under a Near
	// (附近) query as the haversine distance from the pin. All are zero/nil for
	// candidates without a location dimension and never synthesized client-side.
	Geo        *GeoPoint `json:"geo,omitempty"`
	DistanceKm float64   `json:"distanceKm,omitempty"`
	PlaceName  string    `json:"placeName,omitempty"`
	// ConnectionState / IntersectionReason are attached after recall by the
	// search-service from the unified intersection truth source (never inferred
	// on the client). They are nil/empty until the intersection-attach stage
	// populates them; the App must not synthesize them.
	ConnectionState    string                 `json:"connectionState,omitempty"`
	IntersectionReason *HitIntersectionReason `json:"intersectionReason,omitempty"`
	// RankReasons / RankPosition are the ranking-transparency fields declared in
	// the unified retrieve contract (_shared/search_contract.yaml hit_fields).
	// They are the single source of ranking explanation: the shared CrossTypeRanker
	// populates the base reasons (term/anchor/tag/freshness/popularity/geo) and the
	// 1-based RankPosition, so every backend and every caller sees the same truth.
	// The search-service may append additional reasons (e.g. search-term heat under
	// an AB treatment) and re-number RankPosition after a re-rank.
	RankReasons  []Reason `json:"rankReasons,omitempty"`
	RankPosition int      `json:"rankPosition,omitempty"`
}

// HitIntersectionReason mirrors the unified intersection contract's read-only
// shape consumed by search (primaryText + attribution). The search domain never
// generates primaryText; it only carries what the intersection service emits.
type HitIntersectionReason struct {
	PrimaryText    string `json:"primaryText,omitempty"`
	IntersectionID string `json:"intersectionId,omitempty"`
	Dimension      string `json:"dimension,omitempty"`
	Class          string `json:"class,omitempty"`
	SourceRef      string `json:"sourceRef,omitempty"`
}

// RetrieveResponse is the unified response envelope.
type RetrieveResponse struct {
	Hits           []RetrieveHit   `json:"hits"`
	Citations      []Citation      `json:"citations"`
	Facets         []Facet         `json:"facets,omitempty"`
	DegradeSignals []DegradeSignal `json:"degradeSignals,omitempty"`
	Provenance     Provenance      `json:"provenance"`
}

// RecallBackend abstracts a caller-owned recall engine. search-service binds
// this port to one Elasticsearch backend; domain-local readers may bind their
// own native store without creating a cross-backend fallback.
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
	case ObjectTypeLocation:
		return TargetLocation
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
		case TargetLocation:
			add(ObjectTypeLocation)
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
	offset := req.Page.Offset
	if offset < 0 {
		offset = 0
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
		Near:        req.Filters.Near,
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
		Provider:    provider,
		GeneratedAt: time.Now().UTC(),
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

// LimitResponse trims one over-fetched result after the canonical sort and
// refreshes citations so pagination never leaks a hit from the following page.
func LimitResponse(response RetrieveResponse, limit int) (RetrieveResponse, bool) {
	if limit <= 0 || len(response.Hits) <= limit {
		return response, false
	}
	response.Hits = append([]RetrieveHit{}, response.Hits[:limit]...)
	response.Citations = retrieveCitations(response.Hits)
	return response, true
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
		// Geo radius ("附近") hard filter: under a Near query, only candidates
		// with a Geo dimension inside the radius survive; survivors carry their
		// distance + a proximity weight (closer ranks higher).
		nearPass, distanceKm, nearBoost := nearMatch(plan.Near, doc)
		if !nearPass {
			continue
		}

		base := cand.BaseScore
		var matchedField, snippet string
		var termReasons []Reason
		var matchedTerms []string
		var termScore float64
		if len(plan.Terms) > 0 {
			termScore, matchedField, snippet, termReasons = scoreDocument(plan.Interpreted, doc)
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

		// rankReasons accumulates the transparent ranking explanation in the same
		// order the score is composed, so the published reasons and the final
		// score stay a single, consistent truth (no second derivation).
		rankReasons := make([]Reason, 0, 6)
		rankReasons = append(rankReasons, termReasons...)

		score := base + anchorBoost
		if anchorBoost > 0 {
			rankReasons = append(rankReasons, Reason{Code: "anchor_match", Label: "ID/名称锚定命中", Weight: anchorBoost})
		}
		if score <= 0 {
			// Discovery / anchor-only / no-condition path.
			score = 0.1 + popularityScore(doc.Popularity)
			rankReasons = append(rankReasons, Reason{Code: "default_discovery", Label: "默认发现", Weight: score})
		}
		matchedTagList := matchedTagsFor(plan.Tags, doc)
		if len(matchedTagList) > 0 {
			tagBoost := 0.5 * float64(len(matchedTagList))
			score += tagBoost
			rankReasons = append(rankReasons, Reason{Code: "tag_match", Label: "标签匹配：" + strings.Join(matchedTagList, "、"), Weight: tagBoost})
		}
		if !doc.Freshness.IsZero() {
			if fresh := freshnessScore(doc.Freshness); fresh > 0 {
				score += fresh
				rankReasons = append(rankReasons, Reason{Code: "freshness", Label: "内容较新", Weight: fresh})
			}
		}
		if pop := popularityScore(doc.Popularity); pop > 0 {
			score += pop
			rankReasons = append(rankReasons, Reason{Code: "popularity", Label: "热门度加权", Weight: pop})
		}
		if nearBoost > 0 {
			score += nearBoost
			rankReasons = append(rankReasons, Reason{Code: "geo_proximity", Label: "附近优先", Weight: nearBoost})
		}

		if snippet == "" {
			snippet = firstNonEmpty(doc.Summary, doc.Body, doc.Title)
		}
		if matchedField == "" {
			matchedField = "default"
		}

		key := doc.ObjectType + ":" + doc.ObjectID
		if _, dup := seen[key]; dup {
			continue
		}
		seen[key] = struct{}{}

		hits = append(hits, RetrieveHit{
			Target:       target,
			ObjectType:   doc.ObjectType,
			ObjectID:     doc.ObjectID,
			Title:        firstNonEmpty(doc.Title, doc.ObjectID),
			Snippet:      truncate(snippet, 180),
			Score:        score,
			MatchedTerms: matchedTerms,
			MatchedTags:  matchedTagList,
			Evidence:     []Evidence{{Field: matchedField, Snippet: truncate(snippet, 180)}},
			Payload:      fieldsToPayload(doc.Fields),
			DeepLink:     strings.TrimSpace(doc.DeepLink),
			ThumbnailURL: boundedFlatCardThumbnailURL(doc.Fields),
			Geo:          doc.Geo,
			DistanceKm:   distanceKm,
			PlaceName:    strings.TrimSpace(doc.Fields["placeName"]),
			RankReasons:  rankReasons,
		})
		facetCounts[string(target)]++
	}

	SortHitsStable(hits)

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
	// RankPosition is the 1-based final order within this page, assigned after the
	// page slice so the published position matches what the caller renders.
	for i := range hits {
		hits[i].RankPosition = plan.Offset + i + 1
	}
	return hits, facetsFromCounts(facetCounts)
}

// LessHitStable is the total-order comparator that makes ranking repeatable:
// identical inputs always produce the identical order, independent of recall /
// candidate arrival order (ES `_score` ties, segment merges, replica differences,
// multi-threaded indexing). Order:
//
//	Score desc -> Title asc -> Target(objectType) asc -> ObjectID asc.
//
// The last two keys are stable external identifiers, so equal-score equal-title
// ties never fall back to a non-deterministic internal/doc order (the classic
// Lucene "same query jumps between refreshes/replicas" pitfall).
func LessHitStable(a, b RetrieveHit) bool {
	if a.Score != b.Score {
		return a.Score > b.Score
	}
	if a.Title != b.Title {
		return a.Title < b.Title
	}
	if a.Target != b.Target {
		return a.Target < b.Target
	}
	return a.ObjectID < b.ObjectID
}

// SortHitsStable sorts hits in place using the repeatable total order. It is the
// single ranking-order truth source shared by the recall merge and the
// search-service re-rank decorator, so both produce the same deterministic page.
func SortHitsStable(hits []RetrieveHit) {
	sort.SliceStable(hits, func(i, j int) bool { return LessHitStable(hits[i], hits[j]) })
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

const maxFlatCardThumbnailURLBytes = 2048

func boundedFlatCardThumbnailURL(fields map[string]string) string {
	for _, key := range []string{"thumbnailUrl", "coverUrl"} {
		value := strings.TrimSpace(fields[key])
		if value == "" || len(value) > maxFlatCardThumbnailURLBytes {
			continue
		}
		parsed, err := url.ParseRequestURI(value)
		if err != nil || parsed.Host == "" || (parsed.Scheme != "https" && parsed.Scheme != "http") {
			continue
		}
		return value
	}
	return ""
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

// nearMatch applies the cross-object 附近 radius filter. When Near is inactive
// every candidate passes with no distance/boost. When active it is a HARD filter:
// candidates without Geo are excluded (a nearby query is inherently spatial), and
// candidates beyond RadiusKm are dropped. Survivors return their haversine
// distance and a proximity boost that scales linearly from +nearMaxBoost at the
// pin down to 0 at the radius edge, so closer objects rank higher.
func nearMatch(near *GeoNear, doc Document) (pass bool, distanceKm float64, boost float64) {
	if !near.Active() {
		return true, 0, 0
	}
	if doc.Geo == nil {
		return false, 0, 0
	}
	d := haversineKm(near.Lat, near.Lng, doc.Geo.Lat, doc.Geo.Lng)
	if d > near.RadiusKm {
		return false, d, 0
	}
	return true, d, nearMaxBoost * (1 - d/near.RadiusKm)
}

// nearMaxBoost caps the proximity weight added at the pin. It is comparable to a
// strong term hit so "附近" meaningfully reorders without drowning text relevance.
const nearMaxBoost = 3.0

// earthRadiusKm is the mean Earth radius used by the haversine distance.
const earthRadiusKm = 6371.0

// haversineKm returns the great-circle distance in kilometers between two
// lat/lng points. It is the native-path counterpart to the ES geo_distance
// filter so proximity scoring stays identical across backends (single ranker).
func haversineKm(lat1, lng1, lat2, lng2 float64) float64 {
	rad := func(deg float64) float64 { return deg * math.Pi / 180 }
	dLat := rad(lat2 - lat1)
	dLng := rad(lng2 - lng1)
	a := math.Sin(dLat/2)*math.Sin(dLat/2) +
		math.Cos(rad(lat1))*math.Cos(rad(lat2))*math.Sin(dLng/2)*math.Sin(dLng/2)
	return earthRadiusKm * 2 * math.Atan2(math.Sqrt(a), math.Sqrt(1-a))
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
			normalize(doc.Fields["placeName"]),
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
		objectType := strings.TrimSpace(hit.ObjectType)
		if objectType == "" {
			// 文档投影漏掉 canonical type 时不产生 citation，避免向端侧泄露
			// target alias 并让未知目标错误地打开默认内容页。
			continue
		}
		citations = append(citations, Citation{
			CitationID: citationID(objectType, hit.ObjectID),
			ObjectType: objectType,
			ObjectID:   hit.ObjectID,
			Title:      hit.Title,
			Snippet:    hit.Snippet,
			DeepLink:   hit.DeepLink,
			Score:      hit.Score,
		})
	}
	return citations
}

// HitMap renders a RetrieveHit to a JSON-ish map for tool/provider consumers.
func RetrieveHitMap(hit RetrieveHit) map[string]any {
	m := map[string]any{
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
	// Location dimension is included only when present so non-geo hits stay clean.
	if hit.Geo != nil {
		m["geo"] = map[string]any{"lat": hit.Geo.Lat, "lng": hit.Geo.Lng}
	}
	if hit.DistanceKm > 0 {
		m["distanceKm"] = hit.DistanceKm
	}
	if strings.TrimSpace(hit.PlaceName) != "" {
		m["placeName"] = hit.PlaceName
	}
	// Ranking transparency (contract hit_fields): present only when computed so
	// tool/provider consumers see the same ranking truth as the HTTP envelope.
	if len(hit.RankReasons) > 0 {
		m["rankReasons"] = reasonsToMaps(hit.RankReasons)
	}
	if hit.RankPosition > 0 {
		m["rankPosition"] = hit.RankPosition
	}
	return m
}
