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

	rtmongo "quwoquan_service/internal/platform/mongodb"
	"quwoquan_service/runtime/contractfixture"
	filemodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/model"
	groupmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_group/model"
	membershipmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/model"
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

type circleFixtureGroup struct {
	ID                   string `json:"_id"`
	Version              int64  `json:"version"`
	CircleID             string `json:"circleId"`
	ParentGroupID        string `json:"parentGroupId"`
	GroupType            string `json:"groupType"`
	NodeType             string `json:"nodeType"`
	Name                 string `json:"name"`
	Description          string `json:"description"`
	Visibility           string `json:"visibility"`
	JoinPolicy           string `json:"joinPolicy"`
	CreatedByPersonaID   string `json:"createdByPersonaId"`
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
	PersonaID    string `json:"personaId"`
	Role         string `json:"role"`
	JoinedAt     string `json:"joinedAt"`
	LastActiveAt string `json:"lastActiveAt"`
	Contribution int64  `json:"contribution"`
}

type circleFixtureFile struct {
	ID                string `json:"_id"`
	Version           int64  `json:"version"`
	CircleID          string `json:"circleId"`
	GroupID           string `json:"groupId"`
	ParentFolderID    string `json:"parentFolderId"`
	Name              string `json:"name"`
	FileType          string `json:"fileType"`
	AssetID           string `json:"assetId"`
	MimeType          string `json:"mimeType"`
	SizeBytes         int64  `json:"sizeBytes"`
	UploaderPersonaID string `json:"uploaderPersonaId"`
	Status            string `json:"status"`
	CreatedAt         string `json:"createdAt"`
	UpdatedAt         string `json:"updatedAt"`
}

type contentFixturePack struct {
	SeedSets map[string]contentFixtureSeedSet `json:"seedSets"`
}

type contentFixtureSeedSet struct {
	Posts []contentFixturePost `json:"posts"`
}

type contentFixturePost struct {
	ID          string   `json:"id"`
	PostID      string   `json:"postId"`
	Title       string   `json:"title"`
	Summary     string   `json:"summary"`
	ContentType string   `json:"contentType"`
	CoverURL    string   `json:"coverUrl"`
	CircleID    string   `json:"circleId"`
	CircleIDs   []string `json:"circleIds"`
	LikeCount   int64    `json:"likeCount"`
	CreatedAt   string   `json:"createdAt"`
	UpdatedAt   string   `json:"updatedAt"`
	PublishedAt string   `json:"publishedAt"`
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
	return &groupmodel.CircleGroup{
		ID:                   fg.ID,
		Version:              fg.Version,
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
		ID:                ff.ID,
		Version:           ff.Version,
		CircleID:          ff.CircleID,
		GroupID:           ff.GroupID,
		ParentFolderID:    ff.ParentFolderID,
		Name:              ff.Name,
		FileType:          filemodel.CircleFileType(ff.FileType),
		AssetID:           ff.AssetID,
		MimeType:          ff.MimeType,
		SizeBytes:         ff.SizeBytes,
		UploaderPersonaID: ff.UploaderPersonaID,
		Status:            filemodel.CircleFileStatus(ff.Status),
		CreatedAt:         parseFixtureTime(ff.CreatedAt),
		UpdatedAt:         parseFixtureTime(ff.UpdatedAt),
	}
}

func circleIDsFromContentPost(post contentFixturePost) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, 1+len(post.CircleIDs))
	if id := strings.TrimSpace(post.CircleID); id != "" {
		seen[id] = struct{}{}
		out = append(out, id)
	}
	for _, raw := range post.CircleIDs {
		id := strings.TrimSpace(raw)
		if id == "" {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		out = append(out, id)
	}
	return out
}

func circleFeedDocFromFixture(post contentFixturePost) bson.M {
	postID := strings.TrimSpace(post.PostID)
	if postID == "" {
		postID = strings.TrimSpace(post.ID)
	}
	title := strings.TrimSpace(post.Title)
	if title == "" {
		title = postID
	}
	createdAt := parseFixtureTime(post.CreatedAt)
	updatedAt := parseFixtureTime(post.UpdatedAt)
	publishedAt := parseFixtureTime(post.PublishedAt)
	return bson.M{
		"_id":         postID,
		"postId":      postID,
		"title":       title,
		"summary":     strings.TrimSpace(post.Summary),
		"contentType": strings.TrimSpace(post.ContentType),
		"coverUrl":    strings.TrimSpace(post.CoverURL),
		"circleIds":   circleIDsFromContentPost(post),
		"likeCount":   post.LikeCount,
		"status":      "published",
		"createdAt":   createdAt,
		"updatedAt":   updatedAt,
		"publishedAt": publishedAt,
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
	contentFixtureRel := flag.String(
		"content-fixture",
		"content/test_fixtures/scenarios/content_scenarios.gamma-curated.json",
		"metadata-relative content fixture path for circle feed posts",
	)
	contentRefsCSV := flag.String("content-refs", "content_discovery_core", "comma-separated content seed refs")
	flag.Parse()

	pack, err := contractfixture.LoadMetadataJSON[circleFixturePack](*fixtureRel)
	if err != nil {
		log.Fatalf("load circle fixture %s: %v", *fixtureRel, err)
	}
	contentPack, err := contractfixture.LoadMetadataJSON[contentFixturePack](*contentFixtureRel)
	if err != nil {
		log.Fatalf("load content fixture %s: %v", *contentFixtureRel, err)
	}

	ctx := context.Background()
	client := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: *mongoURI}, "circle-seed")
	defer client.Disconnect(ctx)
	db := client.Database(*database)

	// Reset previously seeded fixture rows so reseeding stays deterministic.
	for _, coll := range []string{"circles", "circle_memberships", "circle_groups", "circle_files", "posts"} {
		if _, err := db.Collection(coll).DeleteMany(ctx, bson.M{
			"$or": []bson.M{
				{"_id": bson.M{"$regex": "^fixture_"}},
				{"circleId": bson.M{"$regex": "^fixture_"}},
				{"circleIds": bson.M{"$regex": "^fixture_"}},
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
	seededCircleIDs := map[string]struct{}{}
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
			seededCircleIDs[c.ID] = struct{}{}
			inserted++
		}
		for _, members := range seedSet.Members {
			for _, fm := range members {
				m := circleMembershipFromFixture(fm)
				upsert("circle_memberships", m.ID, m)
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
	for _, ref := range strings.Split(*contentRefsCSV, ",") {
		ref = strings.TrimSpace(ref)
		seedSet, ok := contentPack.SeedSets[ref]
		if !ok {
			log.Printf("WARN: content seed ref not found: %s", ref)
			continue
		}
		for _, post := range seedSet.Posts {
			circleIDs := circleIDsFromContentPost(post)
			keep := false
			for _, circleID := range circleIDs {
				if _, ok := seededCircleIDs[circleID]; ok {
					keep = true
					break
				}
			}
			if !keep {
				continue
			}
			doc := circleFeedDocFromFixture(post)
			postID := strings.TrimSpace(post.PostID)
			if postID == "" {
				postID = strings.TrimSpace(post.ID)
			}
			upsert("posts", postID, doc)
			inserted++
		}
	}

	out, _ := json.Marshal(map[string]any{"insertedCount": inserted, "database": *database})
	log.Printf("circle seed done: %s", string(out))
}
