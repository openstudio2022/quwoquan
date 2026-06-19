package recommendation

import (
	"math"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

// Helpers moved out of engine.go to keep file size within R03 budget.
// Same package, identical behavior: exposure budget, frequency/near-dup
// caps, MMR rerank and diversity metric helpers.

func applyDynamicExposureBudget(
	items []ScoredCandidate,
	limit int,
	cfg recpolicy.DynamicExposureBudgetConfig,
	bucket string,
) []ScoredCandidate {
	if !cfg.Enabled || strings.EqualFold(strings.TrimSpace(bucket), "disable_exposure_dynamic_budget") {
		return items
	}
	if len(items) == 0 {
		return items
	}
	if limit <= 0 || limit > len(items) {
		limit = len(items)
	}
	remaining := make([]ScoredCandidate, 0, len(items))
	selected := make([]ScoredCandidate, 0, limit)
	poolCounts := map[string]int{}

	// Quotas are exposure-share constraints, not rank replacement. We preserve
	// existing score order within every pool and only reserve small trial/rising
	// lanes so young/high-feedback content can earn measured exposure.
	quotas := dynamicBudgetQuotas(limit, cfg)
	for _, s := range items {
		pool := exposurePoolForCandidate(s.Candidate, cfg)
		if quota := quotas[pool]; quota > 0 && poolCounts[pool] < quota && len(selected) < limit {
			selected = append(selected, s)
			poolCounts[pool]++
			continue
		}
		remaining = append(remaining, s)
	}
	existing := make(map[string]struct{}, len(selected))
	for _, s := range selected {
		existing[s.Candidate.ContentID] = struct{}{}
	}
	for _, s := range remaining {
		if len(selected) >= limit {
			break
		}
		if _, ok := existing[s.Candidate.ContentID]; ok {
			continue
		}
		selected = append(selected, s)
		poolCounts[exposurePoolForCandidate(s.Candidate, cfg)]++
	}
	for pool, count := range poolCounts {
		RecordDynamicBudgetSelection(pool, bucket, count)
	}
	if len(selected) == 0 {
		return items
	}
	reordered := make([]ScoredCandidate, 0, len(items))
	reordered = append(reordered, selected...)
	for _, s := range items {
		if _, ok := existing[s.Candidate.ContentID]; ok {
			continue
		}
		reordered = append(reordered, s)
	}
	return reordered
}

func dynamicBudgetQuotas(limit int, cfg recpolicy.DynamicExposureBudgetConfig) map[string]int {
	trial := int(math.Ceil(float64(limit) * 0.2))
	rising := int(math.Ceil(float64(limit) * 0.3))
	if trial < 1 {
		trial = 1
	}
	if rising < 1 {
		rising = 1
	}
	if cfg.TrialMinServed > 0 && trial > cfg.TrialMinServed {
		trial = cfg.TrialMinServed
	}
	return map[string]int{
		"trial":  trial,
		"rising": rising,
	}
}

func exposurePoolForCandidate(c ContentCandidate, cfg recpolicy.DynamicExposureBudgetConfig) string {
	served := c.ViewCount
	ctr := rate(c.LikeCount+c.CommentCount+c.ShareCount, served)
	negativeRate := 0.0
	if c.ViewCount > 0 {
		// share/comment/like are the only available online aggregates in this
		// candidate shape. Negative-rate storage lands in rm_exposure_state; until
		// then, retired remains explicit future state and never inferred falsely.
		negativeRate = 0
	}
	switch {
	case cfg.RetirementNegativeRateThreshold > 0 && negativeRate >= cfg.RetirementNegativeRateThreshold:
		return "retired"
	case served < int64(cfg.TrialMinServed):
		return "trial"
	case ctr >= cfg.PromotionCTRThreshold:
		return "rising"
	case time.Since(c.PublishedAt) > 30*24*time.Hour && ctr > 0:
		return "evergreen"
	default:
		return "mature"
	}
}

func rate(numerator int64, denominator int64) float64 {
	if denominator <= 0 {
		return 0
	}
	return float64(numerator) / float64(denominator)
}

func applyFrequencyAndNearDupCaps(items []ScoredCandidate, limit int, cfg recpolicy.FrequencyAndNearDupConfig) []ScoredCandidate {
	if !cfg.Enabled || len(items) == 0 {
		return items
	}
	if limit <= 0 || limit > len(items) {
		limit = len(items)
	}
	minFill := limit * cfg.SoftFallbackMinFillPct / 100
	if minFill <= 0 {
		minFill = limit
	}
	selected := make([]ScoredCandidate, 0, limit)
	held := make([]ScoredCandidate, 0, len(items))
	reasonCounts := map[string]int{}
	authorCount := map[string]int{}
	tagCount := map[string]int{}
	topicCount := map[string]int{}
	selectedFeatures := make([]map[string]struct{}, 0, limit)

	for _, item := range items {
		if len(selected) >= limit {
			held = append(held, item)
			continue
		}
		if reason := frequencyOrNearDupViolation(item, authorCount, tagCount, topicCount, selectedFeatures, cfg); reason != "" {
			reasonCounts[reason]++
			held = append(held, item)
			continue
		}
		selected = append(selected, item)
		observeFrequency(item.Candidate, authorCount, tagCount, topicCount)
		selectedFeatures = append(selectedFeatures, candidateFeatureSet(item.Candidate))
	}

	// Soft fallback: caps must not empty or under-fill the feed. Refill by
	// original score order when the constrained pass cannot satisfy minFill.
	for _, item := range held {
		if len(selected) >= limit || len(selected) >= minFill {
			break
		}
		selected = append(selected, item)
	}
	if len(selected) == 0 {
		return items
	}
	for reason, count := range reasonCounts {
		if reason == "near_dup" {
			RecordNearDupFilter(count)
			continue
		}
		RecordFrequencyCapFilter(reason, count)
	}
	reordered := make([]ScoredCandidate, 0, len(items))
	reordered = append(reordered, selected...)
	seen := map[string]struct{}{}
	for _, item := range selected {
		seen[item.Candidate.ContentID] = struct{}{}
	}
	for _, item := range items {
		if _, ok := seen[item.Candidate.ContentID]; ok {
			continue
		}
		reordered = append(reordered, item)
	}
	return reordered
}

func frequencyOrNearDupViolation(
	item ScoredCandidate,
	authorCount map[string]int,
	tagCount map[string]int,
	topicCount map[string]int,
	selectedFeatures []map[string]struct{},
	cfg recpolicy.FrequencyAndNearDupConfig,
) string {
	c := item.Candidate
	if cfg.MaxSameAuthorPerWindow > 0 && c.AuthorID != "" && authorCount[c.AuthorID] >= cfg.MaxSameAuthorPerWindow {
		return "author"
	}
	if cfg.MaxSameTagPerWindow > 0 {
		for _, tag := range c.Tags {
			if tag != "" && tagCount[tag] >= cfg.MaxSameTagPerWindow {
				return "tag"
			}
		}
	}
	if cfg.MaxSameTopicPerWindow > 0 {
		for _, topic := range c.EntityRefs {
			if topic != "" && topicCount[topic] >= cfg.MaxSameTopicPerWindow {
				return "topic"
			}
		}
	}
	if cfg.NearDupJaccardMax > 0 {
		features := candidateFeatureSet(c)
		for _, existing := range selectedFeatures {
			if jaccardSimilarity(features, existing) >= cfg.NearDupJaccardMax {
				return "near_dup"
			}
		}
	}
	return ""
}

func observeFrequency(c ContentCandidate, authorCount map[string]int, tagCount map[string]int, topicCount map[string]int) {
	if c.AuthorID != "" {
		authorCount[c.AuthorID]++
	}
	for _, tag := range c.Tags {
		if tag != "" {
			tagCount[tag]++
		}
	}
	for _, topic := range c.EntityRefs {
		if topic != "" {
			topicCount[topic]++
		}
	}
}

// rerankMMR implements Maximal Marginal Relevance reranking: it iteratively
// selects the candidate maximizing λ·relevance − (1−λ)·maxSimilarityToSelected,
// where similarity is the Jaccard overlap of {author, type, tags, entityRefs}.
// This actively balances relevance against novelty (a DPP/MMR-class diversity
// objective) instead of the greedy path's post-hoc dedup, and is activated only
// when policy scorer.diversityStrategy == "mmr". Author/type caps from policy are
// honored as hard constraints, with a fill fallback so the surface is never
// under-filled. Relevance is min-max normalized over the candidate set.
func (e *Engine) rerankMMR(scored []ScoredCandidate, limit int, scorer recpolicy.ScorerConfig) []ScoredCandidate {
	if len(scored) == 0 {
		return scored
	}
	if limit <= 0 || limit > len(scored) {
		limit = len(scored)
	}
	lambda := scorer.DiversityLambda
	if lambda <= 0 || lambda > 1 {
		lambda = 0.7
	}
	maxPerAuthor := scorer.MaxAuthorPerFeed
	maxPerType := (limit / 3) + 1

	minS, maxS := scored[0].Score, scored[0].Score
	for _, s := range scored {
		if s.Score < minS {
			minS = s.Score
		}
		if s.Score > maxS {
			maxS = s.Score
		}
	}
	span := maxS - minS
	rel := func(s ScoredCandidate) float64 {
		if span <= 0 {
			return 1
		}
		return (s.Score - minS) / span
	}

	feats := make([]map[string]struct{}, len(scored))
	for i, s := range scored {
		feats[i] = candidateFeatureSet(s.Candidate)
	}

	selected := make([]ScoredCandidate, 0, limit)
	selectedFeats := make([]map[string]struct{}, 0, limit)
	used := make([]bool, len(scored))
	typeCount := make(map[string]int)
	authorCount := make(map[string]int)

	for len(selected) < limit {
		bestIdx := -1
		bestMMR := math.Inf(-1)
		for i, s := range scored {
			if used[i] {
				continue
			}
			ct := s.Candidate.ContentType
			author := s.Candidate.AuthorID
			if maxPerType > 0 && typeCount[ct] >= maxPerType {
				continue
			}
			if author != "" && maxPerAuthor > 0 && authorCount[author] >= maxPerAuthor {
				continue
			}
			maxSim := 0.0
			for _, sf := range selectedFeats {
				if sim := jaccardSimilarity(feats[i], sf); sim > maxSim {
					maxSim = sim
				}
			}
			mmr := lambda*rel(s) - (1-lambda)*maxSim
			if mmr > bestMMR {
				bestMMR = mmr
				bestIdx = i
			}
		}
		if bestIdx < 0 {
			// All remaining candidates blocked by caps: relax to avoid under-fill,
			// taking the highest-relevance unused candidate.
			for i := range scored {
				if !used[i] {
					bestIdx = i
					break
				}
			}
		}
		if bestIdx < 0 {
			break
		}
		s := scored[bestIdx]
		used[bestIdx] = true
		selected = append(selected, s)
		selectedFeats = append(selectedFeats, feats[bestIdx])
		typeCount[s.Candidate.ContentType]++
		if s.Candidate.AuthorID != "" {
			authorCount[s.Candidate.AuthorID]++
		}
	}
	return selected
}

// candidateFeatureSet is the diversity signature of a candidate: author, content
// type, tags and entity refs. Two candidates sharing more of these are more
// similar (used by the MMR novelty term).
func candidateFeatureSet(c ContentCandidate) map[string]struct{} {
	set := make(map[string]struct{}, 2+len(c.Tags)+len(c.EntityRefs))
	if c.AuthorID != "" {
		set["author:"+c.AuthorID] = struct{}{}
	}
	if c.ContentType != "" {
		set["type:"+c.ContentType] = struct{}{}
	}
	for _, t := range c.Tags {
		if t != "" {
			set["tag:"+t] = struct{}{}
		}
	}
	for _, ref := range c.EntityRefs {
		if ref != "" {
			set["entity:"+ref] = struct{}{}
		}
	}
	return set
}

// jaccardSimilarity returns |A∩B| / |A∪B| ∈ [0,1].
func jaccardSimilarity(a, b map[string]struct{}) float64 {
	if len(a) == 0 || len(b) == 0 {
		return 0
	}
	small, large := a, b
	if len(b) < len(a) {
		small, large = b, a
	}
	inter := 0
	for k := range small {
		if _, ok := large[k]; ok {
			inter++
		}
	}
	union := len(a) + len(b) - inter
	if union == 0 {
		return 0
	}
	return float64(inter) / float64(union)
}

// computeTopicEntropy calculates Shannon entropy of topic tag distribution.
// Higher entropy = more diverse; lower = more concentrated (potential filter bubble).
func computeTopicEntropy(items []ScoredCandidate) float64 {
	topicCounts := make(map[string]int)
	total := 0
	for _, item := range items {
		for _, tag := range item.Candidate.Tags {
			if ClassifyTagDimension(tag) == DimensionTopic {
				topicCounts[tag]++
				total++
			}
		}
	}
	if total == 0 {
		return 0
	}
	entropy := 0.0
	for _, count := range topicCounts {
		p := float64(count) / float64(total)
		if p > 0 {
			entropy -= p * math.Log2(p)
		}
	}
	return entropy
}

func computeAuthorDiversity(items []ScoredCandidate) (repeatRate float64, hhi float64, distinctAuthors int) {
	authorCounts := make(map[string]int)
	total := 0
	for _, item := range items {
		author := strings.TrimSpace(item.Candidate.AuthorID)
		if author == "" {
			continue
		}
		authorCounts[author]++
		total++
	}
	if total == 0 {
		return 0, 0, 0
	}
	distinctAuthors = len(authorCounts)
	repeatRate = 1 - float64(distinctAuthors)/float64(total)
	for _, count := range authorCounts {
		p := float64(count) / float64(total)
		hhi += p * p
	}
	return repeatRate, hhi, distinctAuthors
}

func computeGeoCoverage(items []ScoredCandidate) (coverage float64, distinctGeoBuckets int) {
	geoCounts := make(map[string]int)
	total := 0
	for _, item := range items {
		bucket := primaryGeoBucket(item.Candidate.Tags)
		if bucket == "" {
			continue
		}
		geoCounts[bucket]++
		total++
	}
	if total == 0 {
		return 0, 0
	}
	distinctGeoBuckets = len(geoCounts)
	return float64(distinctGeoBuckets) / float64(len(items)), distinctGeoBuckets
}

func computeDistinctTopicCount(items []ScoredCandidate) int {
	topics := make(map[string]struct{})
	for _, item := range items {
		for _, tag := range item.Candidate.Tags {
			if ClassifyTagDimension(tag) == DimensionTopic {
				topics[tag] = struct{}{}
			}
		}
	}
	return len(topics)
}

func primaryGeoBucket(tags []string) string {
	for _, tag := range tags {
		if strings.HasPrefix(tag, "Topic/地理/行政区/") {
			parts := strings.Split(tag, "/")
			if len(parts) >= 5 {
				return parts[4]
			}
		}
	}
	return ""
}

func topNTags(weights map[string]float64, n int) []string {
	type tw struct {
		tag    string
		weight float64
	}
	var pairs []tw
	for t, w := range weights {
		if w > 0 {
			pairs = append(pairs, tw{t, w})
		}
	}
	sort.Slice(pairs, func(i, j int) bool { return pairs[i].weight > pairs[j].weight })

	result := make([]string, 0, n)
	for i, p := range pairs {
		if i >= n {
			break
		}
		result = append(result, p.tag)
	}
	return result
}

func toSet(ss []string) map[string]bool {
	m := make(map[string]bool, len(ss))
	for _, s := range ss {
		m[s] = true
	}
	return m
}
