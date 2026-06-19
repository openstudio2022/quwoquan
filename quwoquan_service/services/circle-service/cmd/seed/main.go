// Command seed loads circle contract fixtures into a live MongoDB so the
// local-gamma mirror can serve real circle reads for T3.
//
// It reuses the circle domain model + the shared contract fixture loader, so
// the persisted document shape stays single-sourced with the service (no
// second hand-shaped representation). Run from the quwoquan_service module:
//
//	go run ./services/circle-service/cmd/seed \
//	  --mongo-uri mongodb://localhost:19410 --database quwoquan_circle \
//	  --fixture social/circle/test_fixtures/scenarios/circle_scenarios.gamma-curated.json \
//	  --refs circle_core,circle_group_chat_link_core
package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/contractfixture"
	rtmongo "quwoquan_service/runtime/mongodb"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

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

func parseFixtureTime(value string) time.Time {
	if parsed, err := time.Parse(time.RFC3339, value); err == nil {
		return parsed
	}
	return time.Now().UTC()
}

func circleFromFixture(fc circleFixtureCircle) *model.Circle {
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
		CreatedAt:         parseFixtureTime(fc.CreatedAt),
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

func main() {
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "MongoDB connection URI")
	database := flag.String("database", "quwoquan_circle", "circle MongoDB database name")
	fixtureRel := flag.String(
		"fixture",
		"social/circle/test_fixtures/scenarios/circle_scenarios.gamma-curated.json",
		"metadata-relative circle fixture path",
	)
	refsCSV := flag.String("refs", "circle_core,circle_group_chat_link_core", "comma-separated seed refs")
	flag.Parse()

	pack, err := contractfixture.LoadMetadataJSON[circleFixturePack](*fixtureRel)
	if err != nil {
		log.Fatalf("load circle fixture %s: %v", *fixtureRel, err)
	}

	ctx := context.Background()
	client := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: *mongoURI}, "circle-seed")
	defer client.Disconnect(ctx)
	db := client.Database(*database)

	// Reset previously seeded fixture rows so reseeding stays deterministic.
	for _, coll := range []string{"circles", "circle_members", "circle_groups", "circle_files"} {
		if _, err := db.Collection(coll).DeleteMany(ctx, bson.M{
			"$or": []bson.M{
				{"_id": bson.M{"$regex": "^fixture_"}},
				{"circleId": bson.M{"$regex": "^fixture_"}},
			},
		}); err != nil {
			log.Fatalf("reset %s: %v", coll, err)
		}
	}

	upsert := func(coll, id string, doc any) {
		if strings.TrimSpace(id) == "" {
			return
		}
		if _, err := db.Collection(coll).ReplaceOne(
			ctx, bson.M{"_id": id}, doc, options.Replace().SetUpsert(true),
		); err != nil {
			log.Fatalf("upsert %s/%s: %v", coll, id, err)
		}
	}

	inserted := 0
	for _, ref := range strings.Split(*refsCSV, ",") {
		ref = strings.TrimSpace(ref)
		seedSet, ok := pack.SeedSets[ref]
		if !ok {
			log.Printf("WARN: seed ref not found: %s", ref)
			continue
		}
		for _, fc := range seedSet.Circles {
			c := circleFromFixture(fc)
			upsert("circles", c.ID, c)
			inserted++
		}
		for _, members := range seedSet.Members {
			for _, fm := range members {
				m := circleMemberFromFixture(fm)
				upsert("circle_members", m.ID, m)
				inserted++
			}
		}
		for _, groups := range seedSet.Groups {
			for _, fg := range groups {
				g := circleGroupFromFixture(fg)
				upsert("circle_groups", g.ID, g)
				inserted++
			}
		}
		for _, files := range seedSet.Files {
			for _, ff := range files {
				f := circleFileFromFixture(ff)
				upsert("circle_files", f.ID, f)
				inserted++
			}
		}
	}

	out, _ := json.Marshal(map[string]any{"insertedCount": inserted, "database": *database})
	log.Printf("circle seed done: %s", string(out))
}
