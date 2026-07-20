package application

import (
	"context"
	"fmt"
	"strings"
	"time"
)

const chinaAdminRegionRootTagRef = "Topic/地理/行政区/中国"
const profileOccupationRootTagRef = "Audience/用户/职业"
const profileInterestRootTagRef = "Audience/用户/兴趣偏好"
const maxProfileInterestTagRefs = 30
const MaxProfileInterestTagRefs = maxProfileInterestTagRefs

var profileOccupationCategoryRefs = map[string]struct{}{
	"Audience/用户/职业/产品运营": {},
	"Audience/用户/职业/研发技术": {},
	"Audience/用户/职业/设计创意": {},
	"Audience/用户/职业/学生":   {},
	"Audience/用户/职业/自由职业": {},
}

var profileInterestCategoryRefs = map[string]struct{}{
	"Audience/用户/兴趣偏好/旅行摄影": {},
	"Audience/用户/兴趣偏好/校园":   {},
	"Audience/用户/兴趣偏好/生活":   {},
	"Audience/用户/兴趣偏好/艺术":   {},
	"Audience/用户/兴趣偏好/科技":   {},
}

type RegionTagResolver interface {
	ResolveRegionTag(ctx context.Context, regionTagRef string) (string, error)
}

type ProfileTagValidator interface {
	ValidateProfileTags(ctx context.Context, occupationTagRef string, interestTagRefs []string) error
}

type PathRegionTagResolver struct{}

type PathProfileTagValidator struct{}

func (PathRegionTagResolver) ResolveRegionTag(_ context.Context, regionTagRef string) (string, error) {
	ref := strings.TrimSpace(regionTagRef)
	if ref == "" {
		return "", nil
	}
	if !strings.HasPrefix(ref, chinaAdminRegionRootTagRef+"/") {
		return "", fmt.Errorf("regionTagRef must be under %s", chinaAdminRegionRootTagRef)
	}
	parts := strings.Split(ref, "/")
	if len(parts) != 6 {
		return "", fmt.Errorf("regionTagRef must point to a direct province child")
	}
	province := shortAdminRegionLabel(parts[4])
	child := shortAdminRegionLabel(parts[5])
	if province == "" || child == "" {
		return "", fmt.Errorf("regionTagRef contains empty segment")
	}
	if province == child {
		return province, nil
	}
	return province + " " + child, nil
}

func shortAdminRegionLabel(label string) string {
	trimmed := strings.TrimSpace(label)
	if trimmed == "" {
		return ""
	}
	replacements := map[string]string{
		"广西壮族自治区":  "广西",
		"宁夏回族自治区":  "宁夏",
		"新疆维吾尔自治区": "新疆",
		"内蒙古自治区":   "内蒙古",
		"西藏自治区":    "西藏",
		"香港特别行政区":  "香港",
		"澳门特别行政区":  "澳门",
	}
	if value, ok := replacements[trimmed]; ok {
		return value
	}
	for _, suffix := range []string{
		"朝鲜族自治州",
		"蒙古自治州",
		"藏族自治州",
		"回族自治州",
		"哈尼族彝族自治州",
		"壮族苗族自治州",
		"土家族苗族自治州",
		"傣族自治州",
		"白族自治州",
		"傈僳族自治州",
		"自治州",
		"地区",
		"盟",
		"特别行政区",
		"自治区",
		"省",
		"市",
		"区",
		"县",
	} {
		if strings.HasSuffix(trimmed, suffix) && len([]rune(trimmed)) > len([]rune(suffix)) {
			return strings.TrimSuffix(trimmed, suffix)
		}
	}
	return trimmed
}

func (PathProfileTagValidator) ValidateProfileTags(_ context.Context, occupationTagRef string, interestTagRefs []string) error {
	if occupation := strings.TrimSpace(occupationTagRef); occupation != "" {
		if err := validateProfileLeafTagRef(occupation, profileOccupationRootTagRef, profileOccupationCategoryRefs, "occupationTagRef"); err != nil {
			return err
		}
	}
	if len(interestTagRefs) > maxProfileInterestTagRefs {
		return fmt.Errorf("interestTagRefs exceeds %d", maxProfileInterestTagRefs)
	}
	for _, tag := range interestTagRefs {
		if err := validateProfileLeafTagRef(tag, profileInterestRootTagRef, profileInterestCategoryRefs, "interestTagRefs"); err != nil {
			return err
		}
	}
	return nil
}

func validateProfileLeafTagRef(tagRef, root string, allowedParents map[string]struct{}, field string) error {
	trimmed := strings.TrimSpace(tagRef)
	if trimmed == "" {
		return nil
	}
	if !strings.HasPrefix(trimmed, root+"/") {
		return fmt.Errorf("%s must be under %s", field, root)
	}
	parts := strings.Split(trimmed, "/")
	if len(parts) != len(strings.Split(root, "/"))+2 {
		return fmt.Errorf("%s must point to a leaf tag under %s", field, root)
	}
	parent := strings.Join(parts[:len(parts)-1], "/")
	if _, ok := allowedParents[parent]; !ok {
		return fmt.Errorf("%s parent is not enabled for profile editing: %s", field, parent)
	}
	if strings.TrimSpace(parts[len(parts)-1]) == "" {
		return fmt.Errorf("%s contains empty leaf segment", field)
	}
	return nil
}

func isValidProfileGender(gender string) bool {
	switch strings.TrimSpace(gender) {
	case "", "male", "female", "other", "unspecified":
		return true
	default:
		return false
	}
}

func normalizeProfileBirthDate(value string, now time.Time) (string, error) {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return "", nil
	}
	parsed, err := time.Parse("2006-01-02", trimmed)
	if err != nil {
		return "", fmt.Errorf("birthDate must use YYYY-MM-DD")
	}
	min := time.Date(1900, 1, 1, 0, 0, 0, 0, time.UTC)
	today := time.Date(now.UTC().Year(), now.UTC().Month(), now.UTC().Day(), 0, 0, 0, 0, time.UTC)
	if parsed.Before(min) || parsed.After(today) {
		return "", fmt.Errorf("birthDate out of supported range")
	}
	return parsed.Format("2006-01-02"), nil
}

func validateProfileTagRefs(tags []string) error {
	occupationCount := 0
	interestCount := 0
	for _, tag := range tags {
		trimmed := strings.TrimSpace(tag)
		if trimmed == "" {
			continue
		}
		if strings.HasPrefix(trimmed, profileOccupationRootTagRef+"/") {
			occupationCount++
			if occupationCount > 1 {
				return fmt.Errorf("occupationTagRef must be single select")
			}
			continue
		}
		if strings.HasPrefix(trimmed, profileInterestRootTagRef+"/") {
			interestCount++
			if interestCount > maxProfileInterestTagRefs {
				return fmt.Errorf("interestTagRefs exceeds %d", maxProfileInterestTagRefs)
			}
			continue
		}
		if strings.HasPrefix(trimmed, "Topic/兴趣/") {
			return fmt.Errorf("interestTagRefs must be under %s", profileInterestRootTagRef)
		}
		if !strings.Contains(trimmed, "/") {
			continue
		}
		return fmt.Errorf("invalid profile tag root: %s", trimmed)
	}
	return nil
}

func ProfileIdentityTagsFromUpdate(command ProfileUpdateCommand, current []string) ([]string, bool) {
	return profileIdentityTagsFromUpdate(command, current)
}

func ValidateProfileTagRefs(tags []string) error {
	return validateProfileTagRefs(tags)
}
