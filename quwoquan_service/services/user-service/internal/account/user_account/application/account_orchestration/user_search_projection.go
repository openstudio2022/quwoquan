package application

import (
	"strconv"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// UserProfileSearchEligible defines the discoverable user set from the canonical
// account lifecycle state. Anonymous / suspended / deleted accounts are not
// searchable, so the ES index must contain exactly this set.
func UserProfileSearchEligible(profile model.UserProfile) bool {
	return strings.EqualFold(strings.TrimSpace(profile.AccountState), "active")
}

// ProjectUserProfileToSearchDocument projects a user profile into the unified
// search Document (objectType user.profile, target derived as "user"). It is the
// single source of truth for profile→Document mapping, used by the ES search-index
// projector and backfill. authorId/authorName/authorDisplayName are the anchor
// fields the ES indexer flattens for reverse lookup; identity tags become the
// document tags. Only fields that exist on the profile read model are mapped.
func ProjectUserProfileToSearchDocument(profile model.UserProfile) rtsearch.Document {
	return rtsearch.Document{
		ObjectType:   rtsearch.ObjectTypeUserProfile,
		ObjectID:     profile.UserID,
		Title:        profile.Nickname,
		Summary:      profile.Bio,
		SourceDomain: "user",
		Visibility:   "public",
		BadgeLabel:   "用户",
		Tags:         parsePgTextArray(profile.IdentityTags),
		Popularity:   float64(profile.FollowerCount + profile.PostCount),
		Freshness:    profile.UpdatedAt,
		Fields: map[string]string{
			"authorId":          profile.UserID,
			"authorName":        profile.Nickname,
			"authorDisplayName": profile.Nickname,
			"avatarUrl":         profile.AvatarURL,
			"followerCount":     strconv.FormatInt(profile.FollowerCount, 10),
			"postCount":         strconv.FormatInt(profile.PostCount, 10),
		},
	}
}
