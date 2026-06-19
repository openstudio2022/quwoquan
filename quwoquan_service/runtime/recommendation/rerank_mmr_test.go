package recommendation

import (
	"testing"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

func sc(id, author, ctype string, tag string, score float64) ScoredCandidate {
	return ScoredCandidate{
		Candidate: ContentCandidate{
			ContentID:   id,
			AuthorID:    author,
			ContentType: ctype,
			Tags:        []string{tag},
			PublishedAt: time.Now(),
		},
		Score: score,
	}
}

func TestRerankMMR_BreaksUpHomogeneousRun(t *testing.T) {
	eng := &Engine{}
	// 同作者 + 同标签的高分串 + 一个新颖的次高分项。
	// 纯贪心按分排序会把 A 作者连排；MMR 应在前列插入新颖项 div。
	scored := []ScoredCandidate{
		sc("a1", "authorA", "article", "travel", 10.0),
		sc("a2", "authorA", "article", "travel", 9.8),
		sc("a3", "authorA", "article", "travel", 9.6),
		sc("div", "authorB", "video", "food", 9.0),
	}
	scorer := recpolicy.Baseline().Scorer
	scorer.DiversityStrategy = "mmr"
	scorer.DiversityLambda = 0.5
	scorer.MaxAuthorPerFeed = 100 // 关闭硬上限，单测 MMR 新颖性效果本身

	out := eng.rerankMMR(scored, 3, scorer)
	if len(out) != 3 {
		t.Fatalf("expected 3 results, got %d", len(out))
	}
	if out[0].Candidate.ContentID != "a1" {
		t.Fatalf("highest relevance must lead, got %s", out[0].Candidate.ContentID)
	}
	// 第二位应是新颖项 div（与 a1 无作者/标签/类型重合），而非近似重复的 a2。
	if out[1].Candidate.ContentID != "div" {
		t.Fatalf("MMR should surface the novel item second, got %s", out[1].Candidate.ContentID)
	}
}

func TestRerankMMR_GreedyDefaultUnaffected(t *testing.T) {
	eng := &Engine{}
	scored := []ScoredCandidate{
		sc("a1", "authorA", "article", "travel", 10.0),
		sc("div", "authorB", "video", "food", 9.0),
		sc("a2", "authorA", "article", "travel", 8.0),
	}
	scorer := recpolicy.Baseline().Scorer
	// baseline diversityStrategy 默认应为 greedy（非 mmr）。
	if scorer.DiversityStrategy == "mmr" {
		t.Fatalf("baseline must default to greedy, got %q", scorer.DiversityStrategy)
	}
	out := eng.rerank(scored, 3, scorer)
	if len(out) == 0 {
		t.Fatalf("greedy rerank returned empty")
	}
}

func TestJaccardSimilarity(t *testing.T) {
	a := candidateFeatureSet(ContentCandidate{AuthorID: "x", ContentType: "article", Tags: []string{"travel"}})
	b := candidateFeatureSet(ContentCandidate{AuthorID: "x", ContentType: "article", Tags: []string{"travel"}})
	if got := jaccardSimilarity(a, b); got != 1.0 {
		t.Fatalf("identical sets must be 1.0, got %.4f", got)
	}
	c := candidateFeatureSet(ContentCandidate{AuthorID: "y", ContentType: "video", Tags: []string{"food"}})
	if got := jaccardSimilarity(a, c); got != 0.0 {
		t.Fatalf("disjoint sets must be 0.0, got %.4f", got)
	}
}
