package recommendation

import (
	"testing"
)

// W8 embedding 写入管线契约（B5 S0 基建）：文本装配确定性 + 截断上限 +
// 幂等指纹稳定（documentSha 相同即跳过重写，控制 API 成本）。
func TestBuildEmbeddingTextAssemblyAndTruncation(t *testing.T) {
	text := buildEmbeddingText(
		"川西雪山拍摄路线",
		"从成都出发的三日环线……",
		[]string{"Topic/旅行/玩法/摄影旅拍", "Topic/旅行/目的地/川西"},
	)
	if text == "" {
		t.Fatal("assembled embedding text must not be empty")
	}
	if want := "川西雪山拍摄路线"; text[:len(want)] != want {
		t.Fatalf("title must lead the embedding text, got %q", text[:len(want)])
	}

	long := make([]rune, 0, embeddingTextMaxRunes*2)
	for i := 0; i < embeddingTextMaxRunes*2; i++ {
		long = append(long, '字')
	}
	truncated := buildEmbeddingText(string(long), "", nil)
	if got := len([]rune(truncated)); got > embeddingTextMaxRunes {
		t.Fatalf("embedding text must be truncated to %d runes, got %d", embeddingTextMaxRunes, got)
	}

	if buildEmbeddingText("", "", nil) != "" {
		t.Fatal("empty content must produce empty embedding text (skip)")
	}
}

func TestEmbeddingTextSHAIsStableFingerprint(t *testing.T) {
	a := embeddingTextSHA("同一段内容")
	b := embeddingTextSHA("同一段内容")
	c := embeddingTextSHA("另一段内容")
	if a != b {
		t.Fatalf("same text must yield same fingerprint: %s != %s", a, b)
	}
	if a == c {
		t.Fatal("different text must yield different fingerprint")
	}
	if len(a) != 64 {
		t.Fatalf("fingerprint must be sha256 hex (64 chars), got %d", len(a))
	}
}

func TestEmbeddingProjectorNilAndForeignEventsFailOpen(t *testing.T) {
	var nilProjector *EmbeddingProjector
	if err := nilProjector.Project(t.Context(), ProjectorEvent{Type: "PostPublished"}); err != nil {
		t.Fatalf("nil projector must fail open, err=%v", err)
	}

	projector := &EmbeddingProjector{}
	if err := projector.Project(t.Context(), ProjectorEvent{Type: "PostDeleted"}); err != nil {
		t.Fatalf("foreign event must be ignored, err=%v", err)
	}
	if written, err := projector.BackfillMissing(t.Context(), 0); err != nil || written != 0 {
		t.Fatalf("non-positive backfill limit must fail open, written=%d err=%v", written, err)
	}
}
