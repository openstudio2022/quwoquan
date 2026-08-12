package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

var ErrUserProfileSearchProjectionConflict = errors.New(
	"search UserProfile projection identity conflict",
)

type UserProfileSearchProjectionEvent struct {
	EventID        string    `json:"eventId"`
	UserID         string    `json:"userId"`
	ProfileVersion int64     `json:"profileVersion"`
	Operation      string    `json:"operation"`
	Nickname       string    `json:"nickname"`
	AvatarURL      string    `json:"avatarUrl"`
	Bio            string    `json:"bio"`
	IdentityTags   []string  `json:"identityTags"`
	FollowerCount  int64     `json:"followerCount"`
	PostCount      int64     `json:"postCount"`
	UpdatedAt      time.Time `json:"updatedAt"`
}

func (event UserProfileSearchProjectionEvent) Validate() error {
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.UserID) == "" ||
		event.ProfileVersion <= 0 || event.UpdatedAt.IsZero() ||
		(event.Operation != "upsert" && event.Operation != "delete") ||
		event.FollowerCount < 0 || event.PostCount < 0 || event.IdentityTags == nil {
		return errors.New("UserProfile search projection payload is invalid")
	}
	if event.Operation == "delete" &&
		(strings.TrimSpace(event.Nickname) != "" || strings.TrimSpace(event.AvatarURL) != "" ||
			strings.TrimSpace(event.Bio) != "" || len(event.IdentityTags) != 0 ||
			event.FollowerCount != 0 || event.PostCount != 0) {
		return errors.New("UserProfile delete projection must not retain public profile data")
	}
	return nil
}

// Digest excludes EventID so the profile and avatar coordinates emitted for
// the same committed version converge to one Search watermark.
func (event UserProfileSearchProjectionEvent) Digest() string {
	canonical := struct {
		UserID         string    `json:"userId"`
		ProfileVersion int64     `json:"profileVersion"`
		Operation      string    `json:"operation"`
		Nickname       string    `json:"nickname"`
		AvatarURL      string    `json:"avatarUrl"`
		Bio            string    `json:"bio"`
		IdentityTags   []string  `json:"identityTags"`
		FollowerCount  int64     `json:"followerCount"`
		PostCount      int64     `json:"postCount"`
		UpdatedAt      time.Time `json:"updatedAt"`
	}{
		UserID: event.UserID, ProfileVersion: event.ProfileVersion,
		Operation: event.Operation, Nickname: event.Nickname, AvatarURL: event.AvatarURL,
		Bio: event.Bio, IdentityTags: event.IdentityTags,
		FollowerCount: event.FollowerCount, PostCount: event.PostCount,
		UpdatedAt: event.UpdatedAt.UTC(),
	}
	raw, _ := json.Marshal(canonical)
	digest := sha256.Sum256(raw)
	return hex.EncodeToString(digest[:])
}

func (event UserProfileSearchProjectionEvent) Document() rtsearch.Document {
	if event.Operation == "delete" {
		return rtsearch.Document{
			ObjectType: rtsearch.ObjectTypeUserProfile,
			ObjectID:   event.UserID,
		}
	}
	return rtsearch.Document{
		ObjectType:   rtsearch.ObjectTypeUserProfile,
		ObjectID:     event.UserID,
		Title:        event.Nickname,
		Summary:      event.Bio,
		SourceDomain: "user",
		Visibility:   "public",
		BadgeLabel:   "用户",
		Tags:         append([]string(nil), event.IdentityTags...),
		Popularity:   float64(event.FollowerCount + event.PostCount),
		Freshness:    event.UpdatedAt.UTC(),
		Fields: map[string]string{
			"authorId":          event.UserID,
			"authorName":        event.Nickname,
			"authorDisplayName": event.Nickname,
			"avatarUrl":         event.AvatarURL,
			"followerCount":     strconv.FormatInt(event.FollowerCount, 10),
			"postCount":         strconv.FormatInt(event.PostCount, 10),
		},
	}
}

type UserProfileSearchProjectionResult struct {
	Replayed bool
	Stale    bool
	Deleted  bool
}

type UserProfileSearchProjection interface {
	Apply(
		context.Context,
		UserProfileSearchProjectionEvent,
	) (UserProfileSearchProjectionResult, error)
}
