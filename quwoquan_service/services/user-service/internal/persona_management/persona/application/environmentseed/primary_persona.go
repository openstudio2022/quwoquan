// Package environmentseed maps immutable environment profile inputs to
// object-owned Persona seed commands.
package environmentseed

import (
	"time"

	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

type PrimaryPersonaInput struct {
	UserID             string
	DisplayName        string
	AvatarMediaAssetID string
	AvatarURL          string
	AvatarVersion      int
	Bio                string
	Gender             string
	Region             string
}

func BuildPrimaryPersona(input PrimaryPersonaInput) *model.Persona {
	now := time.Date(2026, time.January, 1, 0, 0, 0, 0, time.UTC)
	return &model.Persona{
		PersonaID:                input.UserID,
		UserID:                   input.UserID,
		DisplayName:              input.DisplayName,
		NicknameCustomized:       false,
		UserHandle:               input.UserID,
		Bio:                      input.Bio,
		Gender:                   input.Gender,
		Region:                   input.Region,
		AvatarMediaAssetID:       input.AvatarMediaAssetID,
		AvatarURL:                input.AvatarURL,
		AvatarVersion:            input.AvatarVersion,
		IsPrimary:                true,
		IsActive:                 true,
		IsolationLevel:           "open",
		Status:                   "active",
		InheritsProfileFromOwner: false,
		OverriddenProfileFields:  []string{},
		LastProfileSyncAt:        &now,
		LastProfileSyncSource:    "initial_inherit",
		LastActivatedAt:          &now,
	}
}
