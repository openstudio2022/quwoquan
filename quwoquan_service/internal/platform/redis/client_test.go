package redis

import (
	"testing"
	"time"
)

func TestNormalizeXReadGroupBlock(t *testing.T) {
	t.Run("zero_is_non_blocking", func(t *testing.T) {
		if got := normalizeXReadGroupBlock(0); got >= 0 {
			t.Fatalf("normalizeXReadGroupBlock(0)=%v, want negative sentinel", got)
		}
	})
	t.Run("negative_is_non_blocking", func(t *testing.T) {
		if got := normalizeXReadGroupBlock(-5 * time.Millisecond); got >= 0 {
			t.Fatalf("normalizeXReadGroupBlock(-5ms)=%v, want negative sentinel", got)
		}
	})
	t.Run("positive_timeout_is_preserved", func(t *testing.T) {
		const block = 25 * time.Millisecond
		if got := normalizeXReadGroupBlock(block); got != block {
			t.Fatalf("normalizeXReadGroupBlock(%v)=%v", block, got)
		}
	})
}
