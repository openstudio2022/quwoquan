package ports

import (
	"context"
	"time"
)

type CreatorDisclosureView struct {
	Type        string `json:"type"`
	DisplayText string `json:"displayText"`
	Visible     bool   `json:"visible"`
}

type CreatorWorkView struct {
	Ref       string
	Title     string
	CoverURL  string
	WorkType  string
	SortOrder int
}

// CreatorRuntimeProfileView is UserAccount's consumer-owned public profile
// port. Full release/import state remains private to CreatorRuntimeProfile.
type CreatorRuntimeProfileView struct {
	CreatorID            string
	PersonaID            string
	Handle               string
	DisplayName          string
	Headline             string
	Bio                  string
	AvatarURL            string
	AvatarVersion        int64
	CoverURL             string
	PublicProfileTagRefs []string
	Roles                []string
	Verticals            []string
	ExpertiseClaims      []string
	Disclosure           CreatorDisclosureView
	Works                []CreatorWorkView
	UpdatedAt            time.Time
}

// CreatorRuntimeProfileReader 提供系统 creator 的运行时只读投影。
// 公共身份只认 immutable release authority 的 personaId，以及内容契约
// creatorProfileId 对应的 CreatorRuntimeProfile.creatorId；不接受 handle 或旧别名。
type CreatorRuntimeProfileReader interface {
	FindActiveByPublicIdentity(ctx context.Context, identity string) (*CreatorRuntimeProfileView, bool, error)
	ListActiveWorks(ctx context.Context, identity string) ([]CreatorWorkView, bool, error)
}
