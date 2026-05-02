package tests

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/contractfixture"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

type contractSeedEvidence struct {
	SeedRefs          []string
	ResetScope        string
	TargetStore       string
	InsertedCount     int
	VerifiedEndpoints []string
}

type circleFixturePack struct {
	SeedSets map[string]circleFixtureSeedSet `json:"seedSets"`
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

type circleFixtureGroup struct {
	ID                   string `json:"_id"`
	CircleID             string `json:"circleId"`
	GroupType            string `json:"groupType"`
	Name                 string `json:"name"`
	Description          string `json:"description"`
	Visibility           string `json:"visibility"`
	JoinPolicy           string `json:"joinPolicy"`
	OwnerUserID          string `json:"ownerUserId"`
	MemberCount          int64  `json:"memberCount"`
	ConversationID       string `json:"conversationId"`
	StorageEnabled       bool   `json:"storageEnabled"`
	NoticeEnabled        bool   `json:"noticeEnabled"`
	IsDefaultPublicGroup bool   `json:"isDefaultPublicGroup"`
	Status               string `json:"status"`
	CreatedAt            string `json:"createdAt"`
	UpdatedAt            string `json:"updatedAt"`
}

type circleFixtureMember struct {
	ID           string `json:"_id"`
	CircleID     string `json:"circleId"`
	UserID       string `json:"userId"`
	Role         string `json:"role"`
	JoinedAt     string `json:"joinedAt"`
	LastActiveAt string `json:"lastActiveAt"`
	Contribution int64  `json:"contribution"`
}

type circleFixtureFile struct {
	ID         string `json:"_id"`
	CircleID   string `json:"circleId"`
	GroupID    string `json:"groupId"`
	Name       string `json:"name"`
	FileType   string `json:"fileType"`
	MimeType   string `json:"mimeType"`
	SizeBytes  int64  `json:"sizeBytes"`
	ObjectKey  string `json:"objectKey"`
	UploaderID string `json:"uploaderId"`
	Status     string `json:"status"`
	CreatedAt  string `json:"createdAt"`
	UpdatedAt  string `json:"updatedAt"`
}

func seedCircleContractFixture(t *testing.T, seedRef string) contractSeedEvidence {
	t.Helper()
	ctx := context.Background()
	pack, err := contractfixture.LoadMetadataJSON[circleFixturePack](
		"social/circle/test_fixtures/scenarios/circle_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load circle fixture: %v", err)
	}
	seedSet, ok := pack.SeedSets[seedRef]
	if !ok {
		t.Fatalf("circle seed ref not found: %s", seedRef)
	}

	resetCircleFixtureNamespace(t)
	inserted := 0
	for _, fc := range seedSet.Circles {
		circle := circleFromFixture(fc)
		if _, err := mongoDB.Collection("circles").InsertOne(ctx, circle); err != nil {
			t.Fatalf("seed circle %s: %v", circle.ID, err)
		}
		inserted++
	}
	for _, members := range seedSet.Members {
		for _, fm := range members {
			member := circleMemberFromFixture(fm)
			if _, err := mongoDB.Collection("circle_members").InsertOne(ctx, member); err != nil {
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
		ResetScope:    "fixture_* circles/groups/members/files in circle_test",
		TargetStore:   "mongodb:circle_test",
		InsertedCount: inserted,
		VerifiedEndpoints: []string{
			"/v1/circles",
			"/v1/circles/fixture_circle_photo",
			"/v1/circles/fixture_circle_photo/members",
			"/v1/circles/fixture_circle_photo/files",
		},
	}
}

func resetCircleFixtureNamespace(t *testing.T) {
	t.Helper()
	for _, coll := range []string{"circles", "circle_members", "circle_files", "circle_groups", "posts"} {
		_, err := mongoDB.Collection(coll).DeleteMany(context.Background(), bson.M{
			"$or": []bson.M{
				{"_id": bson.M{"$regex": "^fixture_"}},
				{"circleId": bson.M{"$regex": "^fixture_"}},
				{"groupId": bson.M{"$regex": "^fixture_"}},
				{"userId": bson.M{"$regex": "^fixture_"}},
			},
		})
		if err != nil {
			t.Fatalf("reset circle fixture namespace %s: %v", coll, err)
		}
	}
	mr.FlushAll()
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
		ID:                   fc.ID,
		Name:                 fc.Name,
		Description:          fc.Description,
		CoverUrl:             fc.CoverURL,
		OwnerID:              fc.OwnerID,
		Category:             fc.CategoryID,
		SubCategory:          fc.SubCategory,
		MemberCount:          fc.MemberCount,
		PostCount:            fc.PostCount,
		WeeklyActiveCount:    fc.WeeklyActiveCount,
		Status:               model.CircleStatusActive,
		Visibility:           visibility,
		JoinPolicy:           joinPolicy,
		Kind:                 model.CircleKindInterest,
		DisplaySubjectType:   model.CircleDisplaySubjectTypeCircle,
		FollowEnabled:        true,
		DefaultPublicGroupID: fc.DefaultPublicGroupID,
		ConversationID:       fc.ConversationID,
		AutoSyncChat:         fc.AutoSyncChat,
		SectionConfig: []model.CircleSectionConfig{
			{SectionType: model.CircleSectionTypeWorks, Visible: true, Order: 0},
			{SectionType: model.CircleSectionTypeChat, Visible: true, Order: 1},
			{SectionType: model.CircleSectionTypeStorage, Visible: true, Order: 2},
			{SectionType: model.CircleSectionTypeInteraction, Visible: true, Order: 3},
		},
		StorageQuotaBytes: 1024 * 1024 * 1024,
		DomainID:          fc.DomainID,
		CreatedAt:         createdAt,
		UpdatedAt:         parseFixtureTime(fc.UpdatedAt),
	}
}

func circleMemberFromFixture(fm circleFixtureMember) *model.CircleMember {
	return &model.CircleMember{
		ID:           fm.ID,
		CircleID:     fm.CircleID,
		UserID:       fm.UserID,
		Role:         model.CircleMemberRole(fm.Role),
		JoinedAt:     parseFixtureTime(fm.JoinedAt),
		LastActiveAt: parseFixtureTime(fm.LastActiveAt),
		Contribution: fm.Contribution,
	}
}

func circleGroupFromFixture(fg circleFixtureGroup) *model.CircleGroup {
	return &model.CircleGroup{
		ID:                   fg.ID,
		CircleID:             fg.CircleID,
		GroupType:            model.CircleGroupType(fg.GroupType),
		Name:                 fg.Name,
		Description:          fg.Description,
		Visibility:           model.CircleGroupVisibility(fg.Visibility),
		JoinPolicy:           model.CircleGroupJoinPolicy(fg.JoinPolicy),
		OwnerUserID:          fg.OwnerUserID,
		MemberCount:          fg.MemberCount,
		ConversationID:       fg.ConversationID,
		StorageEnabled:       fg.StorageEnabled,
		NoticeEnabled:        fg.NoticeEnabled,
		IsDefaultPublicGroup: fg.IsDefaultPublicGroup,
		LastActiveAt:         parseFixtureTime(fg.UpdatedAt),
		Status:               model.CircleGroupStatus(fg.Status),
		CreatedAt:            parseFixtureTime(fg.CreatedAt),
		UpdatedAt:            parseFixtureTime(fg.UpdatedAt),
	}
}

func circleFileFromFixture(ff circleFixtureFile) *model.CircleFile {
	return &model.CircleFile{
		ID:         ff.ID,
		CircleID:   ff.CircleID,
		GroupID:    ff.GroupID,
		Name:       ff.Name,
		FileType:   model.CircleFileType(ff.FileType),
		MimeType:   ff.MimeType,
		SizeBytes:  ff.SizeBytes,
		ObjectKey:  ff.ObjectKey,
		UploaderID: ff.UploaderID,
		Status:     model.CircleFileStatus(ff.Status),
		CreatedAt:  parseFixtureTime(ff.CreatedAt),
		UpdatedAt:  parseFixtureTime(ff.UpdatedAt),
	}
}

func parseFixtureTime(value string) time.Time {
	if parsed, err := time.Parse(time.RFC3339, value); err == nil {
		return parsed
	}
	return time.Now().UTC()
}
