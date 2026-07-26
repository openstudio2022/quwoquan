// Package environmentseed maps immutable environment profile inputs to
// object-owned Persona seed commands.
package environmentseed

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"time"

	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

type PrimaryPersonaInput struct {
	UserID        string
	DisplayName   string
	AvatarURL     string
	AvatarVersion int
	Bio           string
}

func BuildPrimaryPersona(input PrimaryPersonaInput) *model.Persona {
	now := time.Date(2026, time.January, 1, 0, 0, 0, 0, time.UTC)
	return &model.Persona{
		SubAccountID:             input.UserID,
		UserID:                   input.UserID,
		DisplayName:              input.DisplayName,
		UserHandle:               input.UserID,
		Phone:                    deterministicSeedPhone(input.UserID),
		Bio:                      input.Bio,
		AvatarURL:                input.AvatarURL,
		AvatarVersion:            input.AvatarVersion,
		IsPrimary:                true,
		IsActive:                 true,
		IsolationLevel:           "open",
		Status:                   "active",
		InheritsProfileFromOwner: true,
		OverriddenProfileFields:  []string{},
		LastProfileSyncAt:        &now,
		LastProfileSyncSource:    "environment-seed",
		LastActivatedAt:          &now,
	}
}

func deterministicSeedPhone(userID string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(userID)))
	return "seed" + hex.EncodeToString(sum[:])[:16]
}
