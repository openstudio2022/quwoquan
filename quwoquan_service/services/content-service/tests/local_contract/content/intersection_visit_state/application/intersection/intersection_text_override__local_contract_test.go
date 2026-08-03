// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-006
package intersection_test

import (
	"strings"
	"testing"

	"quwoquan_service/runtime/controlplane"
	generated "quwoquan_service/services/content-service/generated/content/post"
	. "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

// 运营态覆盖：同一条 l10nKey 由控制面下发新文案后，渲染结果必须立即改变，
// 且未覆盖的条目仍走 registry codegen 基线。改一句话既不发端也不发服务。
func TestIntersectionTextOverrideReplacesBaselineByL10nKey(t *testing.T) {
	store := controlplane.NewHotConfigStore()
	form := generated.IntersectionStatementFormByKind["sharedFollowees"]
	if strings.TrimSpace(form.L10nKey) == "" {
		t.Fatalf("sharedFollowees statement template missing l10nKey")
	}
	store.Apply([]controlplane.ResolvedConfigValue{
		{
			Key:   controlplane.IntersectionTextOverrideKey(form.L10nKey, "zh"),
			Value: "{subject}同样在关注{object}",
		},
		{
			Key:   controlplane.IntersectionTextOverrideKey("intersection.action.follow_person", "zh"),
			Value: "关注这个人",
		},
	})
	SetTextResolver(controlplane.NewIntersectionTextResolver(store))
	t.Cleanup(func() { SetTextResolver(nil) })

	reason, anchor := sharedFolloweesFixture()
	text := ExplainPrimaryText(reason, anchor)
	if !strings.Contains(text, "同样在关注") {
		t.Fatalf("override template must win over codegen baseline, got %q", text)
	}
	// l10nKey 是覆盖的寻址口径，覆盖生效后不变：端与译文按同一 key 对齐。
	if got := ExplainPrimaryTextL10nKey(reason, anchor); got != form.L10nKey {
		t.Fatalf("l10nKey must stay stable under override: got %q want %q", got, form.L10nKey)
	}

	hydrated := HydrateInteractionContract(HydratePointSummary(reason))
	overriddenLabel := false
	for _, hint := range hydrated.ActionHints {
		if hint.ActionKey == "follow_person" {
			overriddenLabel = hint.Label == "关注这个人"
		}
	}
	if !overriddenLabel {
		t.Fatalf("action label override must reach ActionHints: %+v", hydrated.ActionHints)
	}
}

// fail-safe：控制面下发了引用未知槽位的坏模板时，回落契约基线继续出句，
// 而不是让整条交集因一次文案配置错误消失。
func TestIntersectionTextOverrideFallsBackOnUnrenderableTemplate(t *testing.T) {
	reason, anchor := sharedFolloweesFixture()
	baseline := ExplainPrimaryText(reason, anchor)
	if baseline == "" {
		t.Fatalf("baseline statement must render")
	}

	store := controlplane.NewHotConfigStore()
	form := generated.IntersectionStatementFormByKind["sharedFollowees"]
	store.Apply([]controlplane.ResolvedConfigValue{
		{
			Key:   controlplane.IntersectionTextOverrideKey(form.L10nKey, "zh"),
			Value: "{subject}和{unknown_slot}都关注了{object}",
		},
	})
	SetTextResolver(controlplane.NewIntersectionTextResolver(store))
	t.Cleanup(func() { SetTextResolver(nil) })

	if got := ExplainPrimaryText(reason, anchor); got != baseline {
		t.Fatalf("unrenderable override must fail-safe to baseline: got %q want %q", got, baseline)
	}
}

// 未注册解析器（控制面未接入 / 早于同步循环的第一帧）时必须是纯基线渲染。
func TestIntersectionTextWithoutResolverRendersBaseline(t *testing.T) {
	SetTextResolver(nil)
	reason, anchor := sharedFolloweesFixture()
	if text := ExplainPrimaryText(reason, anchor); !strings.Contains(text, "也关注了") {
		t.Fatalf("baseline rendering broke without resolver: %q", text)
	}
}

func sharedFolloweesFixture() (IntersectionReasonView, IntersectionPointView) {
	reason := IntersectionReasonView{
		IntersectionID:    "rel_shared_followees_override",
		IntersectionClass: "fact",
		Dimension:         "relationship",
		ObjectKind:        "person",
		ActionTargetID:    "u_other",
		DisplayName:       "陆衡",
		Strength:          0.9,
		IntersectionPoints: []IntersectionPointView{
			{
				PointID: "p_shared", PointClass: "fact", Dimension: "relationship",
				SourceRef: "sharedFollowees", Label: "共同关注", Count: 3,
				SampleText: "林清越", Visibility: "public",
			},
		},
	}
	return reason, reason.IntersectionPoints[0]
}
