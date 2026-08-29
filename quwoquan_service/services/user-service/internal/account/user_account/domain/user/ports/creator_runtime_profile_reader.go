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
	CreatorID   string
	PersonaID   string
	Handle      string
	DisplayName string
	Headline    string
	Bio         string
	AvatarURL   string
	// AvatarAssetID 是头像的媒体资产标识（DEC-033，契约
	// creator_runtime_profile/fields.yaml avatarAssetId）。signed_grant 交付时
	// App 以它换取短签；空串表示缺席（读面按契约 NULLABLE 出 null），
	// 禁止以 personaId 冒充媒体资产标识。
	AvatarAssetID string
	// AvatarAccessMode 是头像交付访问模式（契约 PersonaProfileView
	// avatarAccessMode，enum 唯一真相源 contracts/metadata/_shared/types.yaml
	// MediaDeliveryAccessMode: public|signed_grant）。由 composition 层依据
	// 导入时按 release authority 断言写入的存储事实单点派生；空串表示缺席。
	AvatarAccessMode     string
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
