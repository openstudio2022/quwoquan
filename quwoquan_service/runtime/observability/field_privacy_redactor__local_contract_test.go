package runtimeobservability

import "testing"

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#open-011
func TestCatalogFieldPrivacyRedactorEnforcesEveryAuthoredAction(t *testing.T) {
	previous := CatalogFieldPrivacyPolicies()
	t.Cleanup(func() { registerCatalogFieldPrivacyPolicies(previous) })
	registerCatalogFieldPrivacyPolicies([]CatalogFieldPrivacyPolicy{
		{ObjectID: "content.post", Field: "location", Action: "mask", MaskStrategy: "city_level_only", Explicit: true},
		{ObjectID: "content.post", Field: "title", Action: "truncate", TruncateChars: 4, Explicit: true},
		{ObjectID: "content.post", Field: "embedding", Action: "drop", Explicit: true},
		{ObjectID: "content.post", Field: "mediaUrls", Action: "count_only", Explicit: true},
		{ObjectID: "user.user_account", Field: "bio", Action: "drop_if_gt_100chars", Explicit: true},
	})

	location, keep := redactCatalogFieldPrivacyAttribute("content.post", "location", map[string]any{
		"provinceName": "四川", "cityName": "成都", "detail": "精确门牌", "latitude": 30.1,
	})
	if !keep {
		t.Fatal("city-level location was dropped")
	}
	coarse := location.(map[string]any)
	if coarse["provinceName"] != "四川" || coarse["cityName"] != "成都" || len(coarse) != 2 {
		t.Fatalf("coarse location = %#v", coarse)
	}

	title, keep := redactCatalogFieldPrivacyAttribute("content.post", "title", "abcdef")
	if !keep || title != "abcd…" {
		t.Fatalf("truncated title = %#v keep=%v", title, keep)
	}
	if _, keep := redactCatalogFieldPrivacyAttribute("content.post", "embedding", []float64{1}); keep {
		t.Fatal("drop policy retained embedding")
	}
	count, keep := redactCatalogFieldPrivacyAttribute("content.post", "mediaUrls", []string{"a", "b"})
	if !keep || count != 2 {
		t.Fatalf("count-only value = %#v keep=%v", count, keep)
	}
	attributes, err := runtimeLogAttributes(
		map[string]any{"title": "abcdef", "embedding": []float64{1}},
		[]string{"title", "embedding"},
		"content.post",
	)
	if err != nil {
		t.Fatal(err)
	}
	if attributes["title"] != "abcd…" {
		t.Fatalf("runtime attribute title = %q, want generated truncation", attributes["title"])
	}
	if _, exists := attributes["embedding"]; exists {
		t.Fatal("runtime attribute path retained a generated drop field")
	}
	if _, keep := redactCatalogFieldPrivacyAttribute("user.user_account", "bio", string(make([]byte, 101))); keep {
		t.Fatal("over-budget bio was retained")
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#open-011
func TestCatalogFieldPrivacyRedactorUsesObjectPolicyAndFailsClosedForUnknownAction(t *testing.T) {
	previous := CatalogFieldPrivacyPolicies()
	t.Cleanup(func() { registerCatalogFieldPrivacyPolicies(previous) })
	registerCatalogFieldPrivacyPolicies([]CatalogFieldPrivacyPolicy{
		{ObjectID: "content.post", Field: "title", Action: "allow", Explicit: true},
		{ObjectID: "assistant.turn", Field: "title", Action: "drop", Explicit: true},
		{ObjectID: "user.user_account", Field: "region", Action: "future_action", Explicit: true},
		{ObjectID: "content.post", Field: "internalNote", Action: "drop"},
	})

	if _, keep := redactCatalogFieldPrivacyAttribute("content.post", "title", "safe"); !keep {
		t.Fatal("exact object policy was not selected")
	}
	if _, keep := redactCatalogFieldPrivacyAttribute("", "title", "ambiguous"); keep {
		t.Fatal("unscoped duplicate field did not select the strictest policy")
	}
	if _, keep := redactCatalogFieldPrivacyAttribute("user.user_account", "region", "成都"); keep {
		t.Fatal("unknown generated action did not fail closed")
	}
	if _, keep := redactCatalogFieldPrivacyAttribute("content.post", "internalNote", "secret"); keep {
		t.Fatal("object-scoped undeclared field was not default-denied")
	}
	if value, keep := redactCatalogFieldPrivacyAttribute("", "internalNote", "runtime"); !keep || value != "runtime" {
		t.Fatal("unscoped runtime log incorrectly inherited an object's default deny")
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#req-013
func TestCatalogFieldPrivacyRedactorRequiresFirstPartyServiceAudience(t *testing.T) {
	previous := CatalogFieldPrivacyPolicies()
	t.Cleanup(func() { registerCatalogFieldPrivacyPolicies(previous) })
	registerCatalogFieldPrivacyPolicies([]CatalogFieldPrivacyPolicy{
		{
			ObjectID: "content.post", Field: "moderationStatus", Action: "allow", Explicit: true,
			Visibility: []string{"first_party_service_internal", "platform-ops"},
		},
		{ObjectID: "content.post", Field: "appOnly", Action: "allow", Explicit: true, Visibility: []string{"app"}},
		{ObjectID: "content.post", Field: "publicState", Action: "allow", Explicit: true, Visibility: []string{"all"}},
		{ObjectID: "content.post", Field: "unscopedState", Action: "allow", Explicit: true},
	})

	if value, keep := redactCatalogFieldPrivacyAttribute(
		"content.post", "moderationStatus", "approved",
	); !keep || value != "approved" {
		t.Fatalf("first-party service field = %#v keep=%v", value, keep)
	}
	if _, keep := redactCatalogFieldPrivacyAttribute(
		"content.post", "appOnly", "visible-in-app",
	); keep {
		t.Fatal("service runtime retained an app-only field")
	}
	if value, keep := redactCatalogFieldPrivacyAttribute(
		"content.post", "publicState", "published",
	); !keep || value != "published" {
		t.Fatalf("all-audience field = %#v keep=%v", value, keep)
	}
	if value, keep := redactCatalogFieldPrivacyAttribute(
		"content.post", "unscopedState", "legacy-policy",
	); !keep || value != "legacy-policy" {
		t.Fatalf("field without an extra visibility policy = %#v keep=%v", value, keep)
	}

	attributes, err := runtimeLogAttributes(
		map[string]any{
			"moderationStatus": "approved",
			"appOnly":          "not-for-service",
		},
		[]string{"moderationStatus", "appOnly"},
		"content.post",
	)
	if err != nil {
		t.Fatal(err)
	}
	if attributes["moderationStatus"] != "approved" {
		t.Fatalf("runtime path lost first-party field: %#v", attributes)
	}
	if _, exists := attributes["appOnly"]; exists {
		t.Fatalf("runtime path retained app-only field: %#v", attributes)
	}

	snapshot := CatalogFieldPrivacyPolicies()
	for index := range snapshot {
		if snapshot[index].Field == "moderationStatus" {
			snapshot[index].Visibility[0] = "app"
		}
	}
	for _, policy := range CatalogFieldPrivacyPolicies() {
		if policy.Field == "moderationStatus" && policy.Visibility[0] != "first_party_service_internal" {
			t.Fatalf("runtime policy snapshot mutated registry visibility: %q", policy.Visibility[0])
		}
	}
}
