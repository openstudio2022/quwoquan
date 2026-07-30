package controlplane

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestIntersectionTextResolverOverrideHitMissAndMetric(t *testing.T) {
	store := NewHotConfigStore()
	const l10nKey = "intersection.relation.alumni"
	store.Apply([]ResolvedConfigValue{
		{Key: IntersectionTextOverrideKey(l10nKey, "zh"), Value: "同校的人"},
	})
	resolver := NewIntersectionTextResolver(store)

	hitBefore := testutil.ToFloat64(intersectionTextOverrideTotal.WithLabelValues("hit", "zh"))
	missBefore := testutil.ToFloat64(intersectionTextOverrideTotal.WithLabelValues("miss", "zh"))

	text, ok := resolver(l10nKey, "zh")
	if !ok || text != "同校的人" {
		t.Fatalf("expected override hit, got ok=%v text=%q", ok, text)
	}

	// 同 key 但 locale=en 未下发 -> 回落基线。
	if _, ok := resolver(l10nKey, "en"); ok {
		t.Fatalf("expected miss for en locale")
	}

	// 未登记 l10nKey -> 回落基线。
	if _, ok := resolver("intersection.relation.not_registered", "zh"); ok {
		t.Fatalf("expected miss for unknown l10nKey")
	}

	hitAfter := testutil.ToFloat64(intersectionTextOverrideTotal.WithLabelValues("hit", "zh"))
	missZhAfter := testutil.ToFloat64(intersectionTextOverrideTotal.WithLabelValues("miss", "zh"))
	if hitAfter-hitBefore != 1 {
		t.Fatalf("expected 1 hit increment, got %v", hitAfter-hitBefore)
	}
	if missZhAfter-missBefore != 1 {
		t.Fatalf("expected 1 zh miss increment, got %v", missZhAfter-missBefore)
	}
}

func TestIntersectionTextResolverFailSafe(t *testing.T) {
	if _, ok := NewIntersectionTextResolver(nil)("intersection.relation.alumni", ""); ok {
		t.Fatalf("nil store must fail-safe to baseline (ok=false)")
	}

	store := NewHotConfigStore()
	store.Apply([]ResolvedConfigValue{
		{Key: IntersectionTextOverrideKey("intersection.relation.alumni", "zh"), Value: "   "},
	})
	// 空白覆盖不得让文案变成空串：必须判为未命中并回落基线。
	if _, ok := NewIntersectionTextResolver(store)("intersection.relation.alumni", "zh"); ok {
		t.Fatalf("blank override must be treated as miss")
	}
	// 空 l10nKey（未登记文案项）不查表。
	if _, ok := NewIntersectionTextResolver(store)("", "zh"); ok {
		t.Fatalf("empty l10nKey must not resolve")
	}
}

func TestIntersectionTextOverrideKeyNamespace(t *testing.T) {
	got := IntersectionTextOverrideKey("intersection.action.follow_person", "")
	want := "sys.intersection_text.intersection.action.follow_person.zh"
	if got != want {
		t.Fatalf("key mismatch: got %q want %q", got, want)
	}
}
