// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006.t3
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006.t6
package local_contract

import (
	"context"
	"errors"
	"fmt"
	"testing"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

func TestProfileCareerInterestTagValidation(t *testing.T) {
	validator := application.PathProfileTagValidator{}
	if err := validator.ValidateProfileTags(
		context.Background(),
		"taxonomy-release-test",
		"Audience/用户/职业/产品运营/产品经理",
		[]string{
			"Audience/用户/兴趣偏好/旅行摄影/旅行",
			"Audience/用户/兴趣偏好/校园/图书馆",
		},
	); err != nil {
		t.Fatalf("valid profile tags rejected: %v", err)
	}

	if err := validator.ValidateProfileTags(context.Background(), "taxonomy-release-test", "Audience/用户/职业/产品运营", nil); err == nil {
		t.Fatalf("category occupation tag should be rejected")
	}
	if err := validator.ValidateProfileTags(context.Background(), "taxonomy-release-test", "Audience/用户/职业/旧分类/产品经理", nil); err == nil {
		t.Fatalf("unknown occupation category should be rejected")
	}
	if err := validator.ValidateProfileTags(context.Background(), "taxonomy-release-test", "", []string{"Topic/兴趣/旅行"}); err == nil {
		t.Fatalf("Topic root interest tag should be rejected")
	}

	tooMany := make([]string, 0, application.MaxProfileInterestTagRefs+1)
	for i := 0; i <= application.MaxProfileInterestTagRefs; i++ {
		tooMany = append(tooMany, fmt.Sprintf("Audience/用户/兴趣偏好/科技/AI%d", i))
	}
	if err := validator.ValidateProfileTags(context.Background(), "taxonomy-release-test", "", tooMany); err == nil {
		t.Fatalf("interest count above %d should be rejected", application.MaxProfileInterestTagRefs)
	}
	if err := validator.ValidateProfileTags(context.Background(), "", "", nil); !errors.Is(err, application.ErrProfileTaxonomyReleaseConflict) {
		t.Fatalf("missing taxonomy release should fail with conflict, got %v", err)
	}
}

func TestProfileIdentityTagsUpdateDedupeAndDropsOldRoots(t *testing.T) {
	current := []string{
		"existing_identity",
		"Audience/用户/职业/学生/大学生",
		"Audience/用户/兴趣偏好/生活/咖啡",
		"Topic/兴趣/旅行",
	}
	occupation := "Audience/用户/职业/产品运营/产品经理"
	next, ok := application.ProfileIdentityTagsFromUpdate(application.ProfileUpdateCommand{
		OccupationTagRef: &occupation,
		InterestTagRefs: []string{
			"Audience/用户/兴趣偏好/旅行摄影/旅行",
			"Audience/用户/兴趣偏好/旅行摄影/旅行",
			"Audience/用户/兴趣偏好/校园/图书馆",
		},
	}, current)
	if !ok {
		t.Fatalf("expected profile tags to be touched")
	}
	want := []string{
		"existing_identity",
		"Audience/用户/职业/产品运营/产品经理",
		"Audience/用户/兴趣偏好/旅行摄影/旅行",
		"Audience/用户/兴趣偏好/校园/图书馆",
	}
	if fmt.Sprint(next) != fmt.Sprint(want) {
		t.Fatalf("next tags mismatch\nwant=%v\n got=%v", want, next)
	}
	if err := application.ValidateProfileTagRefs(next); err != nil {
		t.Fatalf("deduped profile tags should validate: %v", err)
	}
	if err := application.ValidateProfileTagRefs([]string{"Topic/兴趣/旅行"}); err == nil {
		t.Fatalf("Topic root interest should be invalid at save boundary")
	}
}

func TestProfileIdentityTagsUpdatePreservesUntouchedCareerInterestFields(t *testing.T) {
	current := []string{
		"existing_identity",
		"Audience/用户/职业/学生/大学生",
		"Audience/用户/兴趣偏好/生活/咖啡",
	}

	next, ok := application.ProfileIdentityTagsFromUpdate(application.ProfileUpdateCommand{
		InterestTagRefs: []string{"Audience/用户/兴趣偏好/旅行摄影/旅行"},
	}, current)
	if !ok {
		t.Fatalf("expected profile tags to be touched")
	}
	want := []string{
		"existing_identity",
		"Audience/用户/职业/学生/大学生",
		"Audience/用户/兴趣偏好/旅行摄影/旅行",
	}
	if fmt.Sprint(next) != fmt.Sprint(want) {
		t.Fatalf("interest-only update should preserve occupation\nwant=%v\n got=%v", want, next)
	}

	occupation := "Audience/用户/职业/产品运营/产品经理"
	next, ok = application.ProfileIdentityTagsFromUpdate(application.ProfileUpdateCommand{
		OccupationTagRef: &occupation,
	}, current)
	if !ok {
		t.Fatalf("expected profile tags to be touched")
	}
	want = []string{
		"existing_identity",
		"Audience/用户/兴趣偏好/生活/咖啡",
		"Audience/用户/职业/产品运营/产品经理",
	}
	if fmt.Sprint(next) != fmt.Sprint(want) {
		t.Fatalf("occupation-only update should preserve interests\nwant=%v\n got=%v", want, next)
	}
}
