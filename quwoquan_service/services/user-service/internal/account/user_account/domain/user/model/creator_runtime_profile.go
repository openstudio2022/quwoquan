package model

import "time"

// CreatorRuntimeProfile 是 immutable release 中 canonical creator package
// 在 user-service 的只读运行时投影。它补充系统 creator 的公开资料与作品引用，
// 不创建可登录账号，也不复制作品正文。
type CreatorRuntimeProfile struct {
	CreatorID             string                 `json:"creatorId" bson:"creatorId"`
	SubAccountID          string                 `json:"subAccountId" bson:"subAccountId"`
	Handle                string                 `json:"handle" bson:"handle"`
	DisplayName           string                 `json:"displayName" bson:"displayName"`
	Headline              string                 `json:"headline" bson:"headline"`
	Bio                   string                 `json:"bio" bson:"bio"`
	Slogan                string                 `json:"slogan" bson:"slogan"`
	AvatarURL             string                 `json:"avatarUrl" bson:"avatarUrl"`
	AvatarAssetID         string                 `json:"avatarAssetId" bson:"avatarAssetId"`
	AvatarVersion         int64                  `json:"avatarVersion" bson:"avatarVersion"`
	AvatarPublicSliceKey  string                 `json:"avatarPublicSliceKey" bson:"avatarPublicSliceKey"`
	AvatarSHA256          string                 `json:"avatarSha256" bson:"avatarSha256"`
	CoverURL              string                 `json:"coverUrl" bson:"coverUrl"`
	CoverObjectKey        string                 `json:"coverObjectKey" bson:"coverObjectKey"`
	CoverSHA256           string                 `json:"coverSha256" bson:"coverSha256"`
	TagRefs               []string               `json:"tagRefs" bson:"tagRefs"`
	PublicProfileTagRefs  []string               `json:"publicProfileTagRefs" bson:"publicProfileTagRefs"`
	Roles                 []string               `json:"roles" bson:"roles"`
	Verticals             []string               `json:"verticals" bson:"verticals"`
	Segment               string                 `json:"segment" bson:"segment"`
	PreferredContentTypes []string               `json:"preferredContentTypes" bson:"preferredContentTypes"`
	CreatorArchetype      string                 `json:"creatorArchetype" bson:"creatorArchetype"`
	CarrierAffinity       CreatorCarrierAffinity `json:"carrierAffinity" bson:"carrierAffinity"`
	PreferredBlueprintIDs []string               `json:"preferredBlueprintIds" bson:"preferredBlueprintIds"`
	CoverageScope         CreatorCoverageScope   `json:"coverageScope" bson:"coverageScope"`
	ClaimPolicy           CreatorClaimPolicy     `json:"claimPolicy" bson:"claimPolicy"`
	ExpertiseClaims       []string               `json:"expertiseClaims" bson:"expertiseClaims"`
	MustNotClaim          []string               `json:"mustNotClaim" bson:"mustNotClaim"`
	Disclosure            CreatorDisclosure      `json:"disclosure" bson:"disclosure"`
	EntityRefs            []string               `json:"entityRefs" bson:"entityRefs"`
	CircleRefs            []string               `json:"circleRefs" bson:"circleRefs"`
	SourceStatus          string                 `json:"sourceStatus" bson:"sourceStatus"`
	Works                 []CreatorWorkRef       `json:"works" bson:"works"`
	PackageDigest         string                 `json:"packageDigest" bson:"packageDigest"`
	ReleaseID             string                 `json:"releaseId" bson:"releaseId"`
	Status                string                 `json:"status" bson:"status"`
	ManagedBy             string                 `json:"managedBy" bson:"managedBy"`
	ImportedAt            time.Time              `json:"importedAt" bson:"importedAt"`
	UpdatedAt             time.Time              `json:"updatedAt" bson:"updatedAt"`
	TombstonedAt          *time.Time             `json:"tombstonedAt,omitempty" bson:"tombstonedAt,omitempty"`
}

type CreatorCarrierAffinity struct {
	Article float64 `json:"article" bson:"article"`
	Image   float64 `json:"image" bson:"image"`
	Video   float64 `json:"video" bson:"video"`
}

type CreatorCoverageScope struct {
	Kind       string   `json:"kind" bson:"kind"`
	Label      string   `json:"label,omitempty" bson:"label,omitempty"`
	RegionRefs []string `json:"regionRefs" bson:"regionRefs"`
	TopicRefs  []string `json:"topicRefs" bson:"topicRefs"`
}

type CreatorClaimPolicy struct {
	ExperienceClaimMode       string   `json:"experienceClaimMode" bson:"experienceClaimMode"`
	MayUseFirstPerson         bool     `json:"mayUseFirstPerson" bson:"mayUseFirstPerson"`
	MustCiteEvidenceForClaims bool     `json:"mustCiteEvidenceForClaims" bson:"mustCiteEvidenceForClaims"`
	ForbiddenClaims           []string `json:"forbiddenClaims" bson:"forbiddenClaims"`
}

type CreatorDisclosure struct {
	Type        string `json:"type" bson:"type"`
	DisplayText string `json:"displayText" bson:"displayText"`
	Visible     bool   `json:"visible" bson:"visible"`
}

// CreatorWorkRef 只保存 canonical post 引用与列表展示投影，不复制作品正文。
type CreatorWorkRef struct {
	Ref       string `json:"ref" bson:"ref"`
	Title     string `json:"title" bson:"title"`
	CoverURL  string `json:"coverUrl" bson:"coverUrl"`
	WorkType  string `json:"workType" bson:"workType"`
	SortOrder int    `json:"sortOrder" bson:"sortOrder"`
}
