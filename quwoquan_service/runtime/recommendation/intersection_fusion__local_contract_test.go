package recommendation

import (
	"context"
	"math"
	"testing"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

// 交集信号在 socialPrior 单点注入：社交/交集来源候选按 viewer 揭示的同 kind 参与度
// 取得有界提升，非交集来源候选不受影响。
func TestRuleScorer_IntersectionSignalLiftsSocialOriginCandidates(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cands := []ContentCandidate{
		{ContentID: "friend", ContentType: "article", PublishedAt: now, RecallPath: "social_friend"},
		{ContentID: "circle", ContentType: "article", PublishedAt: now, RecallPath: "social_circle"},
		{ContentID: "hot", ContentType: "article", PublishedAt: now, RecallPath: "hot_recall"},
	}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
		User:          &UserFeatureVector{SharedFolloweesCount: 8, SharedCircleCount: 4},
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	byID := map[string]ScoredCandidate{}
	for _, s := range scored {
		byID[s.Candidate.ContentID] = s
	}
	friendSP := byID["friend"].Detail["socialPrior"]
	circleSP := byID["circle"].Detail["socialPrior"]
	hotSP := byID["hot"].Detail["socialPrior"]
	if !(friendSP > hotSP) {
		t.Fatalf("social_friend candidate must earn intersection socialPrior lift: friend=%.4f hot=%.4f", friendSP, hotSP)
	}
	if !(circleSP > hotSP) {
		t.Fatalf("social_circle candidate must earn intersection socialPrior lift: circle=%.4f hot=%.4f", circleSP, hotSP)
	}
	if math.Abs(hotSP) > 1e-12 {
		t.Fatalf("non-intersection candidate must not receive intersection lift, got socialPrior=%.6f", hotSP)
	}
	// SharedFolloweesCount(8) > SharedCircleCount(4) ⇒ friend 提升大于 circle。
	if !(friendSP > circleSP) {
		t.Fatalf("higher revealed engagement should yield larger lift: friend=%.4f circle=%.4f", friendSP, circleSP)
	}
}

func TestRuleScorer_IntersectionSignalDisabledWhenFactorZero(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cands := []ContentCandidate{{ContentID: "friend", ContentType: "article", PublishedAt: now, RecallPath: "social_friend"}}
	sc := recpolicy.Baseline().Scorer
	sc.IntersectionSignalFactor = 0 // 关闭融合
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        sc,
		Deterministic: true,
		User:          &UserFeatureVector{SharedFolloweesCount: 8},
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	if got := scored[0].Detail["socialPrior"]; math.Abs(got) > 1e-12 {
		t.Fatalf("zero factor must disable intersection lift, got socialPrior=%.6f", got)
	}
}

func TestRuleScorer_IntersectionSignalNoUserNoPanic(t *testing.T) {
	scorer := &RuleScorer{}
	cands := []ContentCandidate{{ContentID: "friend", ContentType: "article", PublishedAt: time.Now(), RecallPath: "social_friend"}}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
		User:          nil, // 游客 / 无特征
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	if got := scored[0].Detail["socialPrior"]; math.Abs(got) > 1e-12 {
		t.Fatalf("nil user must yield zero socialPrior, got %.6f", got)
	}
}

func TestRuleScorer_CandidateIntersectionFactOutranksAffinity(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cands := []ContentCandidate{
		{
			ContentID:         "fact",
			ContentType:       "article",
			AuthorID:          "u_author_fact",
			PublishedAt:       now,
			IntersectionClass: "fact",
		},
		{
			ContentID:                   "affinity",
			ContentType:                 "article",
			PublishedAt:                 now,
			AffinityIntersectionScore:   1,
			IntersectionConfidenceLabel: "high",
			IntersectionClass:           "affinity",
		},
	}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
		// 事实通道的输入是 viewer ↔ 对象的物化交集边，而不是候选自身的
		// 交集承载力：这里 viewer 与 fact 候选的作者之间有一条满权重的边。
		User: &UserFeatureVector{
			IntersectionEdges: map[string]IntersectionEdgeFeature{
				"u_author_fact": {Weight: 1, Freshness: 1, Kind: "commonFollower"},
			},
		},
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	byID := map[string]ScoredCandidate{}
	for _, s := range scored {
		byID[s.Candidate.ContentID] = s
	}
	if !(byID["fact"].Score > byID["affinity"].Score) {
		t.Fatalf("fact intersection must outrank affinity: fact=%.4f affinity=%.4f", byID["fact"].Score, byID["affinity"].Score)
	}
	if !(byID["fact"].Detail["intersectionFact"] > byID["affinity"].Detail["intersectionAffinity"]) {
		t.Fatalf("fact detail must be stronger than affinity: fact=%v affinity=%v", byID["fact"].Detail, byID["affinity"].Detail)
	}
}

// 内容侧的交集承载力（该 post 挂了几个 entity/tag 提示）与看的人无关，
// 不得进入事实通道：否则「这条内容能产生交集」会被当成「你和它有交集」，
// 违反诚实红线，也让所有挂满实体的内容对所有人普遍加权。
func TestRuleScorer_ContentSideIntersectionCapacityIsNotViewerFact(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cands := []ContentCandidate{{
		ContentID:                "capacity_only",
		ContentType:              "article",
		AuthorID:                 "u_author_unknown",
		PublishedAt:              now,
		IntersectionFactStrength: 12, // 内容挂了 12 个交集提示
		IntersectionFreshness:    1,
		IntersectionClass:        "fact",
	}}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
		// viewer 有交集边，但和这条候选的作者/实体都不相干。
		User: &UserFeatureVector{
			IntersectionEdges: map[string]IntersectionEdgeFeature{
				"u_someone_else": {Weight: 1, Freshness: 1, Kind: "commonFollower"},
			},
		},
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	if got := scored[0].Detail["intersectionFact"]; math.Abs(got) > 1e-12 {
		t.Fatalf("content-side capacity must not lift the fact channel, got %.6f", got)
	}
	if got := scored[0].Detail["intersectionEdgeWeight"]; math.Abs(got) > 1e-12 {
		t.Fatalf("unmatched viewer must yield zero edge weight, got %.6f", got)
	}
}

// 事实通道按真实边权单调：同一条内容，viewer 的交集边越强、越新，提升越大。
func TestRuleScorer_FactChannelScalesWithRealEdgeWeight(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cand := ContentCandidate{
		ContentID:   "post",
		ContentType: "article",
		AuthorID:    "u_author",
		PublishedAt: now,
		EntityRefs:  []string{"place_west_lake"},
	}
	score := func(edge IntersectionEdgeFeature, key string) float64 {
		features := &ScoringFeatures{
			Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
			Scorer:        recpolicy.Baseline().Scorer,
			Deterministic: true,
			User: &UserFeatureVector{
				IntersectionEdges: map[string]IntersectionEdgeFeature{key: edge},
			},
		}
		scored, err := scorer.ScoreBatch(context.Background(), features, []ContentCandidate{cand})
		if err != nil {
			t.Fatalf("score: %v", err)
		}
		return scored[0].Detail["intersectionFact"]
	}
	weak := score(IntersectionEdgeFeature{Weight: 0.2, Freshness: 0.3}, "u_author")
	strong := score(IntersectionEdgeFeature{Weight: 0.9, Freshness: 1}, "u_author")
	if !(strong > weak && weak > 0) {
		t.Fatalf("fact channel must scale with edge weight: weak=%.6f strong=%.6f", weak, strong)
	}
	// 地点交集通过 entityRefs 命中，与人对象交集同一套融合。
	viaEntity := score(IntersectionEdgeFeature{Weight: 0.9, Freshness: 1}, "place_west_lake")
	if math.Abs(viaEntity-strong) > 1e-12 {
		t.Fatalf("entity-side edge must fuse identically: entity=%.6f author=%.6f", viaEntity, strong)
	}
}

func TestRuleScorer_AffinityIntersectionRequiresConfidenceLabel(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	cands := []ContentCandidate{{
		ContentID:                 "affinity_without_label",
		ContentType:               "article",
		PublishedAt:               now,
		AffinityIntersectionScore: 1,
		IntersectionClass:         "affinity",
	}}
	features := &ScoringFeatures{
		Weights:       recpolicy.Baseline().WeightPresets[recpolicy.Baseline().DefaultPreset],
		Scorer:        recpolicy.Baseline().Scorer,
		Deterministic: true,
	}
	scored, err := scorer.ScoreBatch(context.Background(), features, cands)
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	if got := scored[0].Detail["intersectionAffinity"]; math.Abs(got) > 1e-12 {
		t.Fatalf("affinity without confidenceLabel must be ignored, got %.6f", got)
	}
}

func TestCandidateInputAtProjectsOneAuthorEntityMatchedEdgeSnapshot(t *testing.T) {
	user := &UserFeatureVector{
		IntersectionEdges: map[string]IntersectionEdgeFeature{
			"author":   {Weight: 0.4, Freshness: 0.9, Kind: "sharedFollowees"},
			"place-1":  {Weight: 0.8, Freshness: 0.7, Kind: "coVisitedEntity"},
			"entity-2": {Weight: 0.6, Freshness: 0.5, Kind: "sharedEntityAttention"},
		},
	}
	candidate := ContentCandidate{
		ContentID: "post", AuthorID: "author", EntityRefs: []string{"place-1", "entity-2"},
	}

	input := candidateInputAt(candidate, time.Now().UTC(), user)
	if input.IntersectionEdgeWeight != 0.8 ||
		input.IntersectionEdgeFreshness != 0.7 ||
		input.IntersectionEdgeKind != "coVisitedEntity" {
		t.Fatalf("strongest entity edge was not projected: %+v", input)
	}
	authorWinner := candidateInputAt(
		candidate,
		time.Now().UTC(),
		&UserFeatureVector{IntersectionEdges: map[string]IntersectionEdgeFeature{
			"author":  {Weight: 0.95, Freshness: 0.6, Kind: "sharedFollowees"},
			"place-1": {Weight: 0.8, Freshness: 0.7, Kind: "coVisitedEntity"},
		}},
	)
	if authorWinner.IntersectionEdgeWeight != 0.95 ||
		authorWinner.IntersectionEdgeKind != "sharedFollowees" {
		t.Fatalf("strongest author edge did not win entity competition: %+v", authorWinner)
	}

	// The immutable training sample reuses the already projected values.  A
	// later feature-store mutation must not make training select another edge.
	user.IntersectionEdges["author"] = IntersectionEdgeFeature{
		Weight: 1, Freshness: 1, Kind: "commonFollower",
	}
	snapshot := trainingUserFeatures(user, input)
	if snapshot["intersectionEdgeWeight"] != 0.8 ||
		snapshot["intersectionEdgeFreshness"] != 0.7 ||
		snapshot["intersectionEdgeKind"] != "coVisitedEntity" {
		t.Fatalf("training did not reuse the online matched-edge snapshot: %+v", snapshot)
	}
	if _, leaked := snapshot["intersectionEdges"]; leaked {
		t.Fatal("raw intersectionEdges map entered a per-candidate training sample")
	}

	modelUser := modelUserFeatures(user)
	if modelUser == nil || modelUser.IntersectionEdges != nil {
		t.Fatalf("raw edge map crossed the Python model boundary: %+v", modelUser)
	}
	if len(user.IntersectionEdges) == 0 {
		t.Fatal("model projection mutated the authoritative UserFeatureVector")
	}
}

func TestCandidateInputAtUsesZeroMatchedEdgeOnMiss(t *testing.T) {
	input := candidateInputAt(
		ContentCandidate{AuthorID: "unknown", EntityRefs: []string{"missing"}},
		time.Now().UTC(),
		&UserFeatureVector{IntersectionEdges: map[string]IntersectionEdgeFeature{
			"other": {Weight: 1, Freshness: 1, Kind: "sharedFollowees"},
		}},
	)
	if input.IntersectionEdgeWeight != 0 ||
		input.IntersectionEdgeFreshness != 0 ||
		input.IntersectionEdgeKind != "" {
		t.Fatalf("unmatched candidate must have an empty edge snapshot: %+v", input)
	}
}
