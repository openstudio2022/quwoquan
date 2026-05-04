package redis

import (
	"testing"
	"time"
)

func TestNormalizeXReadGroupBlock(t *testing.T) {
	t.Run("non-blocking when zero", func(t *testing.T) {
		if got := normalizeXReadGroupBlock(0); got >= 0 {
			t.Fatalf("normalizeXReadGroupBlock(0) = %v, want negative non-blocking sentinel", got)
		}
	})

	t.Run("non-blocking when negative", func(t *testing.T) {
		if got := normalizeXReadGroupBlock(-5 * time.Millisecond); got >= 0 {
			t.Fatalf("normalizeXReadGroupBlock(-5ms) = %v, want negative non-blocking sentinel", got)
		}
	})

	t.Run("preserve positive timeout", func(t *testing.T) {
		const block = 25 * time.Millisecond
		if got := normalizeXReadGroupBlock(block); got != block {
			t.Fatalf("normalizeXReadGroupBlock(%v) = %v, want %v", block, got, block)
		}
	})
}
