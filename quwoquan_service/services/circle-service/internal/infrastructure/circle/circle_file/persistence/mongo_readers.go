package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	filemodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/model"
	fileports "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/ports"
)

type MongoReaders struct {
	circles           *mongo.Collection
	circleMemberships *mongo.Collection
	groupMemberships  *mongo.Collection
	files             *mongo.Collection
}

func NewMongoReaders(database *mongo.Database) *MongoReaders {
	if database == nil {
		panic("CircleFile MongoReaders requires database")
	}
	return &MongoReaders{
		circles: database.Collection("circles"), circleMemberships: database.Collection("circle_memberships"),
		groupMemberships: database.Collection("circle_group_memberships"), files: database.Collection(fileCollection),
	}
}

func (readers *MongoReaders) ReadCircleStoragePolicy(ctx context.Context, circleID string) (fileports.CircleStoragePolicySlice, bool, error) {
	var document struct {
		ID         string `bson:"_id"`
		State      string `bson:"status"`
		QuotaBytes int64  `bson:"storageQuotaBytes"`
	}
	err := readers.circles.FindOne(ctx, bson.M{"_id": strings.TrimSpace(circleID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return fileports.CircleStoragePolicySlice{}, false, nil
	}
	if err != nil {
		return fileports.CircleStoragePolicySlice{}, false, err
	}
	return fileports.CircleStoragePolicySlice{CircleID: document.ID, State: document.State, QuotaBytes: document.QuotaBytes}, true, nil
}

func (readers *MongoReaders) ReadCircleMembership(ctx context.Context, circleID, personaID string) (fileports.MembershipPolicySlice, bool, error) {
	return readers.readMembership(ctx, readers.circleMemberships, bson.M{
		"circleId": strings.TrimSpace(circleID), "personaId": strings.TrimSpace(personaID),
	})
}

func (readers *MongoReaders) ReadGroupMembership(ctx context.Context, groupID, personaID string) (fileports.MembershipPolicySlice, bool, error) {
	return readers.readMembership(ctx, readers.groupMemberships, bson.M{
		"groupId": strings.TrimSpace(groupID), "personaId": strings.TrimSpace(personaID),
	})
}

func (readers *MongoReaders) readMembership(ctx context.Context, collection *mongo.Collection, filter bson.M) (fileports.MembershipPolicySlice, bool, error) {
	var document struct {
		PersonaID string `bson:"personaId"`
		Role      string `bson:"role"`
		State     string `bson:"state"`
	}
	err := collection.FindOne(ctx, filter).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return fileports.MembershipPolicySlice{}, false, nil
	}
	if err != nil {
		return fileports.MembershipPolicySlice{}, false, err
	}
	return fileports.MembershipPolicySlice{PersonaID: document.PersonaID, Role: document.Role, State: document.State}, true, nil
}

func (readers *MongoReaders) ReadParentFolder(ctx context.Context, circleID, fileID string) (filemodel.CircleFile, bool, error) {
	return readers.ReadFile(ctx, circleID, fileID)
}

func (readers *MongoReaders) ParentChainContains(ctx context.Context, circleID, parentID, candidateID string) (bool, error) {
	seen := map[string]struct{}{}
	currentID := strings.TrimSpace(parentID)
	for depth := 0; depth < 64 && currentID != ""; depth++ {
		if currentID == strings.TrimSpace(candidateID) {
			return true, nil
		}
		if _, exists := seen[currentID]; exists {
			return true, nil
		}
		seen[currentID] = struct{}{}
		parent, found, err := readers.ReadFile(ctx, circleID, currentID)
		if err != nil {
			return false, err
		}
		if !found || parent.FileType != filemodel.CircleFileTypeFolder || parent.Status != filemodel.CircleFileStatusActive {
			return false, filemodel.ErrParentInvalid
		}
		currentID = strings.TrimSpace(parent.ParentFolderID)
	}
	if currentID != "" {
		return false, filemodel.ErrParentInvalid
	}
	return false, nil
}

func (readers *MongoReaders) ReadFile(ctx context.Context, circleID, fileID string) (filemodel.CircleFile, bool, error) {
	var file filemodel.CircleFile
	err := readers.files.FindOne(ctx, bson.M{
		"_id": strings.TrimSpace(fileID), "circleId": strings.TrimSpace(circleID), "status": filemodel.CircleFileStatusActive,
	}).Decode(&file)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return filemodel.CircleFile{}, false, nil
	}
	if err != nil {
		return filemodel.CircleFile{}, false, err
	}
	return file, true, nil
}

func (readers *MongoReaders) ListFiles(ctx context.Context, query fileports.ListQuery) (fileports.PageSlice, error) {
	limit := query.Limit
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	filter := bson.M{
		"circleId": strings.TrimSpace(query.CircleID), "groupId": strings.TrimSpace(query.GroupID),
		"parentFolderId": strings.TrimSpace(query.ParentFolderID), "status": filemodel.CircleFileStatusActive,
	}
	if cursor := strings.TrimSpace(query.Cursor); cursor != "" {
		filter["_id"] = bson.M{"$gt": cursor}
	}
	rows, err := readers.files.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit+1)))
	if err != nil {
		return fileports.PageSlice{}, fmt.Errorf("list CircleFiles: %w", err)
	}
	defer rows.Close(ctx)
	var files []filemodel.CircleFile
	if err := rows.All(ctx, &files); err != nil {
		return fileports.PageSlice{}, fmt.Errorf("decode CircleFiles: %w", err)
	}
	page := fileports.PageSlice{Items: files}
	if len(page.Items) > limit {
		page.Cursor = page.Items[limit-1].ID
		page.Items = page.Items[:limit]
	}
	return page, nil
}

var (
	_ fileports.PolicyReader = (*MongoReaders)(nil)
	_ fileports.Reader       = (*MongoReaders)(nil)
)
