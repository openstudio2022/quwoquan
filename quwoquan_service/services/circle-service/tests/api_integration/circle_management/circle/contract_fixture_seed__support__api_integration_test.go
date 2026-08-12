package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	model "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
	filemodel "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/model"
	groupmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
	membershipmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
)

type contractSeedEvidence struct {
	SeedRefs          []string
	ResetScope        string
	TargetStore       string
	InsertedCount     int
	VerifiedEndpoints []string
}

type circleFixtureSeedSet struct {
	Circles []circleFixtureCircle            `json:"circles"`
	Groups  map[string][]circleFixtureGroup  `json:"groups"`
	Members map[string][]circleFixtureMember `json:"members"`
	Files   map[string][]circleFixtureFile   `json:"files"`
}

type circleFixtureCircle struct {
	ID                   string `json:"id"`
	Name                 string `json:"name"`
	Description          string `json:"description"`
	CoverURL             string `json:"coverUrl"`
	OwnerID              string `json:"ownerId"`
	OwnerDisplayName     string `json:"ownerDisplayNameSnapshot"`
	CategoryID           string `json:"categoryId"`
	SubCategory          string `json:"subCategory"`
	DomainID             string `json:"domainId"`
	MemberCount          int64  `json:"memberCount"`
	PostCount            int64  `json:"postCount"`
	WeeklyActiveCount    int64  `json:"weeklyActiveCount"`
	Visibility           string `json:"visibility"`
	JoinPolicy           string `json:"joinPolicy"`
	DefaultPublicGroupID string `json:"defaultPublicGroupId"`
	ConversationID       string `json:"conversationId"`
	AutoSyncChat         bool   `json:"autoSyncChat"`
	CreatedAt            string `json:"createdAt"`
	UpdatedAt            string `json:"updatedAt"`
}

// fixture 场景文件是存储 seed（bson 语义），标识键为 `_id`；
// 结构体标签必须与 circle_scenarios.json 的真实键名一致。
type circleFixtureGroup struct {
	ID                   string `json:"_id"` // 存储 seed 只认 bson `_id` 键，非 wire
	Version              int64  `json:"version"`
	CircleID             string `json:"circleId"`
	ParentGroupID        string `json:"parentGroupId"`
	GroupType            string `json:"groupType"`
	NodeType             string `json:"nodeType"`
	Name                 string `json:"name"`
	Description          string `json:"description"`
	Visibility           string `json:"visibility"`
	JoinPolicy           string `json:"joinPolicy"`
	CreatedByPersonaID   string `json:"ownerUserId"`
	ConversationID       string `json:"conversationId"`
	StorageEnabled       bool   `json:"storageEnabled"`
	NoticeEnabled        bool   `json:"noticeEnabled"`
	IsDefaultPublicGroup bool   `json:"isDefaultPublicGroup"`
	Status               string `json:"status"`
	CreatedAt            string `json:"createdAt"`
	UpdatedAt            string `json:"updatedAt"`
}

type circleFixtureMember struct {
	ID           string `json:"_id"` // 存储 seed 只认 bson `_id` 键，非 wire
	CircleID     string `json:"circleId"`
	PersonaID    string `json:"userId"`
	Role         string `json:"role"`
	JoinedAt     string `json:"joinedAt"`
	LastActiveAt string `json:"lastActiveAt"`
	Contribution int64  `json:"contribution"`
}

type circleFixtureFile struct {
	ID                string `json:"_id"` // 存储 seed 只认 bson `_id` 键，非 wire
	Version           int64  `json:"version"`
	CircleID          string `json:"circleId"`
	GroupID           string `json:"groupId"`
	ParentFolderID    string `json:"parentFolderId"`
	Name              string `json:"name"`
	FileType          string `json:"fileType"`
	AssetID           string `json:"assetId"`
	MimeType          string `json:"mimeType"`
	SizeBytes         int64  `json:"sizeBytes"`
	UploaderPersonaID string `json:"uploaderId"`
	Status            string `json:"status"`
	CreatedAt         string `json:"createdAt"`
	UpdatedAt         string `json:"updatedAt"`
}

func seedCircleContractFixture(t *testing.T, seedRef string) contractSeedEvidence {
	t.Helper()
	ctx := context.Background()
	seedSet, ok := buildCircleContractSeed(seedRef)
	if !ok {
		t.Fatalf("circle seed ref not found: %s", seedRef)
	}

	resetCircleFixtureNamespace(t)
	inserted := 0
	seenMembers := make(map[string]struct{})
	for _, fc := range seedSet.Circles {
		circle := circleFromFixture(fc)
		if _, err := mongoDB.Collection("circles").InsertOne(ctx, circle); err != nil {
			t.Fatalf("seed circle %s: %v", circle.ID, err)
		}
		inserted++
	}
	for _, members := range seedSet.Members {
		for _, fm := range members {
			member := circleMembershipFromFixture(fm)
			if _, exists := seenMembers[member.ID]; exists {
				continue
			}
			seenMembers[member.ID] = struct{}{}
			if _, err := mongoDB.Collection("circle_memberships").InsertOne(ctx, member); err != nil {
				t.Fatalf("seed circle member %s: %v", member.ID, err)
			}
			inserted++
		}
	}
	for _, groups := range seedSet.Groups {
		for _, fg := range groups {
			group := circleGroupFromFixture(fg)
			if _, err := mongoDB.Collection("circle_groups").InsertOne(ctx, group); err != nil {
				t.Fatalf("seed circle group %s: %v", group.ID, err)
			}
			inserted++
			if _, err := mongoDB.Collection("circle_group_memberships").InsertOne(ctx, bson.M{
				"_id":     "fixture_group_membership_" + group.ID,
				"version": 1, "circleId": group.CircleID, "groupId": group.ID,
				"personaId": group.CreatedByPersonaID, "role": "owner", "state": "active",
				"createdAt": group.CreatedAt, "updatedAt": group.UpdatedAt,
			}); err != nil {
				t.Fatalf("seed CircleGroupMembership %s: %v", group.ID, err)
			}
			inserted++
		}
	}
	for _, files := range seedSet.Files {
		for _, ff := range files {
			file := circleFileFromFixture(ff)
			if _, err := mongoDB.Collection("circle_files").InsertOne(ctx, file); err != nil {
				t.Fatalf("seed circle file %s: %v", file.ID, err)
			}
			inserted++
		}
	}

	return contractSeedEvidence{
		SeedRefs:      []string{seedRef},
		ResetScope:    "fixture_* circles/groups/memberships/files in circle_test",
		TargetStore:   "mongodb:circle_test",
		InsertedCount: inserted,
		VerifiedEndpoints: []string{
			"/circles",
			"/circles/fixture_circle_photo",
			"/circles/fixture_circle_photo/impact",
			"/circles/fixture_circle_photo/memberships",
			"/circles/fixture_circle_photo/files",
		},
	}
}

// buildCircleContractSeed 构造对象级最小前置状态。边界数量由测试内 builder
// 生成，不再从跨环境 scenario dump 反序列化整包业务数据。
func buildCircleContractSeed(seedRef string) (circleFixtureSeedSet, bool) {
	if seedRef != "circle_core" {
		return circleFixtureSeedSet{}, false
	}
	const at = "2026-05-06T00:00:00Z"
	photo := circleFixtureCircle{
		ID: "fixture_circle_photo", Name: "契约摄影社", Description: "摄影对象级契约圈子。",
		CoverURL: "media/image/s/archived-image/circle/fixture_circle_photo/v1/cover.png",
		OwnerID:  "fixture_user_owner", OwnerDisplayName: "契约摄影社主理人",
		CategoryID: "humanity", SubCategory: "影像", DomainID: "culture_arts",
		MemberCount: 3, PostCount: 18, WeeklyActiveCount: 3,
		Visibility: "public", JoinPolicy: "approval",
		DefaultPublicGroupID: "fixture_group_photo_public",
		ConversationID:       "fixture_conv_circle_photo", AutoSyncChat: true,
		CreatedAt: at, UpdatedAt: at,
	}
	travel := circleFixtureCircle{
		ID: "fixture_circle_travel", Name: "契约旅行手账", Description: "旅行对象级契约圈子。",
		CoverURL: "media/image/s/archived-image/circle/fixture_circle_travel/v1/cover.png",
		OwnerID:  "fixture_user_travel_owner", OwnerDisplayName: "契约旅行圈主",
		CategoryID: "travel", SubCategory: "攻略", DomainID: "culture_arts",
		MemberCount: 1, PostCount: 3, WeeklyActiveCount: 1,
		Visibility: "public", JoinPolicy: "open",
		DefaultPublicGroupID: "fixture_group_travel_public",
		ConversationID:       "fixture_conv_circle_travel", AutoSyncChat: true,
		CreatedAt: at, UpdatedAt: at,
	}
	return circleFixtureSeedSet{
		Circles: []circleFixtureCircle{photo, travel},
		Groups: map[string][]circleFixtureGroup{
			photo.ID: {{
				ID: "fixture_group_photo_public", Version: 1, CircleID: photo.ID,
				GroupType: "public_group", Name: "契约摄影社公开群",
				Description: "契约摄影社默认公开群。", Visibility: "public",
				JoinPolicy: "apply_only", CreatedByPersonaID: photo.OwnerID,
				ConversationID: photo.ConversationID, StorageEnabled: true,
				NoticeEnabled: true, IsDefaultPublicGroup: true, Status: "active",
				CreatedAt: at, UpdatedAt: at,
			}},
		},
		Members: map[string][]circleFixtureMember{
			photo.ID: {
				{ID: "fixture_member_photo_fixture_user_owner", CircleID: photo.ID, PersonaID: photo.OwnerID, Role: "owner", JoinedAt: at, LastActiveAt: at, Contribution: 10},
				{ID: "fixture_member_photo_fixture_user_photo", CircleID: photo.ID, PersonaID: "fixture_user_photo", Role: "member", JoinedAt: at, LastActiveAt: at, Contribution: 3},
				{ID: "fixture_member_photo_fixture_user_photography_01", CircleID: photo.ID, PersonaID: "fixture_user_photography_01", Role: "member", JoinedAt: at, LastActiveAt: at, Contribution: 3},
			},
		},
		Files: map[string][]circleFixtureFile{
			photo.ID: {{
				ID: "fixture_file_photo_guide", Version: 1, CircleID: photo.ID,
				GroupID: "fixture_group_photo_public", Name: "摄影路线指南.png",
				FileType: "image", MimeType: "image/png", SizeBytes: 4096,
				UploaderPersonaID: photo.OwnerID, Status: "active",
				CreatedAt: at, UpdatedAt: at,
			}},
		},
	}, true
}

func resetCircleFixtureNamespace(t *testing.T) {
	t.Helper()
	for _, coll := range []string{"circles", "circle_memberships", "circle_group_memberships", "circle_files", "circle_groups", "circle_feed_items"} {
		_, err := mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{
			"$or": []bson.M{
				{"_id": bson.M{"$regex": "^fixture_"}},
				{"circleId": bson.M{"$regex": "^fixture_"}},
				{"groupId": bson.M{"$regex": "^fixture_"}},
				{"personaId": bson.M{"$regex": "^fixture_"}},
			},
		})
		if err != nil {
			t.Fatalf("reset circle fixture namespace %s: %v", coll, err)
		}
	}
	if err := integrationRedis.FlushDBs(context.Background(), 0); err != nil {
		t.Fatalf("flush circle fixture Redis: %v", err)
	}
	eventSpy.Reset()
}

func circleFromFixture(fc circleFixtureCircle) *model.Circle {
	createdAt := parseFixtureTime(fc.CreatedAt)
	visibility := model.CircleVisibility(fc.Visibility)
	if visibility == "" {
		visibility = model.CircleVisibilityPublic
	}
	joinPolicy := model.CircleJoinPolicy(fc.JoinPolicy)
	if joinPolicy == "" {
		joinPolicy = model.CircleJoinPolicyOpen
	}
	return &model.Circle{
		ID:                       fc.ID,
		Name:                     fc.Name,
		Description:              fc.Description,
		CoverUrl:                 fc.CoverURL,
		OwnerID:                  fc.OwnerID,
		OwnerDisplayNameSnapshot: fc.OwnerDisplayName,
		Category:                 fc.CategoryID,
		SubCategory:              fc.SubCategory,
		MemberCount:              fc.MemberCount,
		PostCount:                fc.PostCount,
		WeeklyActiveCount:        fc.WeeklyActiveCount,
		Status:                   model.CircleStatusActive,
		Visibility:               visibility,
		JoinPolicy:               joinPolicy,
		Kind:                     model.CircleKindInterest,
		DisplaySubjectType:       model.CircleDisplaySubjectTypeCircle,
		FollowEnabled:            true,
		DefaultPublicGroupID:     fc.DefaultPublicGroupID,
		ConversationID:           fc.ConversationID,
		AutoSyncChat:             fc.AutoSyncChat,
		SectionConfig: []model.CircleSectionConfig{
			{SectionType: model.CircleSectionTypeWorks, Visible: true, Order: 0},
			{SectionType: model.CircleSectionTypeMembers, Visible: true, Order: 1},
			{SectionType: model.CircleSectionTypeChat, Visible: true, Order: 2},
			{SectionType: model.CircleSectionTypeStorage, Visible: true, Order: 3},
		},
		StorageQuotaBytes: 1024 * 1024 * 1024,
		DomainID:          fc.DomainID,
		CreatedAt:         createdAt,
		UpdatedAt:         parseFixtureTime(fc.UpdatedAt),
	}
}

func circleMembershipFromFixture(fm circleFixtureMember) *membershipmodel.CircleMembership {
	joinedAt := parseFixtureTime(fm.JoinedAt)
	lastActiveAt := parseFixtureTime(fm.LastActiveAt)
	return &membershipmodel.CircleMembership{
		ID:           fm.ID,
		Version:      1,
		CircleID:     fm.CircleID,
		PersonaID:    fm.PersonaID,
		Role:         membershipmodel.CircleMemberRole(fm.Role),
		State:        membershipmodel.CircleMembershipStateActive,
		JoinedAt:     joinedAt,
		LastActiveAt: lastActiveAt,
		Contribution: fm.Contribution,
		CreatedAt:    joinedAt,
		UpdatedAt:    lastActiveAt,
	}
}

func circleGroupFromFixture(fg circleFixtureGroup) *groupmodel.CircleGroup {
	version := fg.Version
	if version <= 0 {
		version = 1
	}
	return &groupmodel.CircleGroup{
		ID:                   fg.ID,
		Version:              version,
		CircleID:             fg.CircleID,
		ParentGroupID:        fg.ParentGroupID,
		GroupType:            groupmodel.CircleGroupType(fg.GroupType),
		NodeType:             groupmodel.OrganizationNodeType(fg.NodeType),
		Name:                 fg.Name,
		Description:          fg.Description,
		Visibility:           groupmodel.CircleGroupVisibility(fg.Visibility),
		JoinPolicy:           groupmodel.CircleGroupJoinPolicy(fg.JoinPolicy),
		CreatedByPersonaID:   fg.CreatedByPersonaID,
		ConversationID:       fg.ConversationID,
		StorageEnabled:       fg.StorageEnabled,
		NoticeEnabled:        fg.NoticeEnabled,
		IsDefaultPublicGroup: fg.IsDefaultPublicGroup,
		Status:               groupmodel.CircleGroupStatus(fg.Status),
		CreatedAt:            parseFixtureTime(fg.CreatedAt),
		UpdatedAt:            parseFixtureTime(fg.UpdatedAt),
	}
}

func circleFileFromFixture(ff circleFixtureFile) *filemodel.CircleFile {
	return &filemodel.CircleFile{
		ID: ff.ID, Version: max(ff.Version, 1), CircleID: ff.CircleID, GroupID: ff.GroupID,
		ParentFolderID: ff.ParentFolderID, Name: ff.Name,
		FileType: filemodel.CircleFileType(ff.FileType), AssetID: ff.AssetID,
		MimeType: ff.MimeType, SizeBytes: ff.SizeBytes,
		UploaderPersonaID: ff.UploaderPersonaID,
		Status:            filemodel.CircleFileStatus(ff.Status),
		CreatedAt:         parseFixtureTime(ff.CreatedAt),
		UpdatedAt:         parseFixtureTime(ff.UpdatedAt),
	}
}

func parseFixtureTime(value string) time.Time {
	if parsed, err := time.Parse(time.RFC3339, value); err == nil {
		return parsed
	}
	return time.Now().UTC()
}
