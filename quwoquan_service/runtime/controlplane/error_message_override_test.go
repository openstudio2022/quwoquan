package controlplane

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestErrorMessageResolverOverrideHitMissAndMetric(t *testing.T) {
	store := NewHotConfigStore()
	const code = "USER.AUTH.otp_mismatch"
	store.Apply([]ResolvedConfigValue{
		{Key: ErrorMessageOverrideKey(code, "zh"), Value: "验证码错啦，再核对一下吧"},
	})
	resolver := NewErrorMessageResolver(store)

	hitBefore := testutil.ToFloat64(errorMessageOverrideTotal.WithLabelValues("hit", "zh"))
	missBefore := testutil.ToFloat64(errorMessageOverrideTotal.WithLabelValues("miss", "zh"))

	// 命中：locale=zh，存在 override。
	msg, ok := resolver(code, "zh")
	if !ok || msg != "验证码错啦，再核对一下吧" {
		t.Fatalf("expected override hit, got ok=%v msg=%q", ok, msg)
	}

	// 未命中：同 code 但 locale=en 无 override -> fail-safe 回退。
	if _, ok := resolver(code, "en"); ok {
		t.Fatalf("expected miss for en locale")
	}

	// 未命中：未知 code -> 回退 baseline。
	if _, ok := resolver("USER.AUTH.unknown_reason", "zh"); ok {
		t.Fatalf("expected miss for unknown code")
	}

	hitAfter := testutil.ToFloat64(errorMessageOverrideTotal.WithLabelValues("hit", "zh"))
	missZhAfter := testutil.ToFloat64(errorMessageOverrideTotal.WithLabelValues("miss", "zh"))

	if hitAfter-hitBefore != 1 {
		t.Fatalf("expected 1 hit increment, got %v", hitAfter-hitBefore)
	}
	// zh miss +1（未知 code），en miss 走 "en" 标签不计入 zh。
	if missZhAfter-missBefore != 1 {
		t.Fatalf("expected 1 zh miss increment, got %v", missZhAfter-missBefore)
	}
}

func TestErrorMessageResolverNilStoreFailSafe(t *testing.T) {
	resolver := NewErrorMessageResolver(nil)
	if _, ok := resolver("USER.AUTH.otp_mismatch", ""); ok {
		t.Fatalf("nil store must fail-safe to baseline (ok=false)")
	}
	// 空 locale 归一为 zh 标签计 miss。
	if got := testutil.ToFloat64(errorMessageOverrideTotal.WithLabelValues("miss", "zh")); got < 1 {
		t.Fatalf("expected miss metric recorded for nil store, got %v", got)
	}
}
