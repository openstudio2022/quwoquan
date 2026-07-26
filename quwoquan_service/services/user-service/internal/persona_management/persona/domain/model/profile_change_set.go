package model

import (
	"fmt"
	"sort"
	"strings"
)

// ProfileChangeSet is the Persona bounded-context value object shared by the
// Persona aggregate and ProfileUpdateProposal. Domain/application code never
// receives a dynamic map; JSON exists only at transport/persistence edges.
type ProfileChangeSet struct {
	DisplayName            *string `json:"displayName,omitempty"`
	Bio                    *string `json:"bio,omitempty"`
	AvatarMediaAssetID     *string `json:"avatarMediaAssetId,omitempty"`
	BackgroundMediaAssetID *string `json:"backgroundMediaAssetId,omitempty"`
	IsPrivate              *bool   `json:"isPrivate,omitempty"`
	IsolationLevel         *string `json:"isolationLevel,omitempty"`
	PurposeHint            *string `json:"purposeHint,omitempty"`
}

func (c ProfileChangeSet) Validate() error {
	if c.DisplayName == nil && c.Bio == nil && c.AvatarMediaAssetID == nil &&
		c.BackgroundMediaAssetID == nil && c.IsPrivate == nil &&
		c.IsolationLevel == nil && c.PurposeHint == nil {
		return fmt.Errorf("%w: profile change set must contain at least one field", ErrInvalidArgument)
	}
	if c.DisplayName != nil {
		value := strings.TrimSpace(*c.DisplayName)
		if value == "" || len([]rune(value)) > 64 {
			return fmt.Errorf("%w: displayName must contain 1..64 characters", ErrInvalidArgument)
		}
	}
	if c.Bio != nil && len([]rune(strings.TrimSpace(*c.Bio))) > 500 {
		return fmt.Errorf("%w: bio cannot exceed 500 characters", ErrInvalidArgument)
	}
	for name, value := range map[string]*string{
		"avatarMediaAssetId":     c.AvatarMediaAssetID,
		"backgroundMediaAssetId": c.BackgroundMediaAssetID,
	} {
		if value != nil && strings.TrimSpace(*value) == "" {
			return fmt.Errorf("%w: %s cannot be empty", ErrInvalidArgument, name)
		}
	}
	if c.IsolationLevel != nil {
		switch strings.TrimSpace(*c.IsolationLevel) {
		case "open", "semi", "strict":
		default:
			return fmt.Errorf("%w: isolationLevel must be open, semi, or strict", ErrInvalidArgument)
		}
	}
	if c.PurposeHint != nil && len([]rune(strings.TrimSpace(*c.PurposeHint))) > 120 {
		return fmt.Errorf("%w: purposeHint cannot exceed 120 characters", ErrInvalidArgument)
	}
	return nil
}

// ChangedFields is the canonical, stable impact scope for this typed change.
func (c ProfileChangeSet) ChangedFields() []string {
	fields := make([]string, 0, 7)
	for name, present := range map[string]bool{
		"avatarMediaAssetId":     c.AvatarMediaAssetID != nil,
		"backgroundMediaAssetId": c.BackgroundMediaAssetID != nil,
		"bio":                    c.Bio != nil,
		"displayName":            c.DisplayName != nil,
		"isPrivate":              c.IsPrivate != nil,
		"isolationLevel":         c.IsolationLevel != nil,
		"purposeHint":            c.PurposeHint != nil,
	} {
		if present {
			fields = append(fields, name)
		}
	}
	sort.Strings(fields)
	return fields
}
