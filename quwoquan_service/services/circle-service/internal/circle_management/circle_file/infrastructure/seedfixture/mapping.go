package seedfixture

import (
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	filemodel "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/model"
)

type CircleFile struct {
	ID                string `json:"id"`
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

type ContentPost struct {
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

func CircleFileFromFixture(fixture CircleFile) *filemodel.CircleFile {
	return &filemodel.CircleFile{
		ID: fixture.ID, Version: fixture.Version, CircleID: fixture.CircleID,
		GroupID: fixture.GroupID, ParentFolderID: fixture.ParentFolderID,
		Name: fixture.Name, FileType: filemodel.CircleFileType(fixture.FileType),
		AssetID: fixture.AssetID, MimeType: fixture.MimeType, SizeBytes: fixture.SizeBytes,
		UploaderPersonaID: fixture.UploaderPersonaID,
		Status:            filemodel.CircleFileStatus(fixture.Status),
		CreatedAt:         parseTime(fixture.CreatedAt), UpdatedAt: parseTime(fixture.UpdatedAt),
	}
}

func CirclePlacementDocFromFixture(post ContentPost, circleID string) (string, bson.M) {
	postID := strings.TrimSpace(post.PostID)
	if postID == "" {
		postID = strings.TrimSpace(post.ID)
	}
	circleID = strings.TrimSpace(circleID)
	placementID := fmt.Sprintf("fixture_placement_%s_%s", circleID, postID)
	createdAt := parseTime(post.CreatedAt)
	updatedAt := parseTime(post.UpdatedAt)
	return placementID, bson.M{
		"_id": placementID, "version": int64(1), "circleId": circleID,
		"postId": postID, "groupId": "", "state": "active", "pinned": false,
		"featured": false, "lastActiveAt": createdAt, "createdAt": createdAt,
		"updatedAt": updatedAt, "ownerPersonaId": "",
	}
}

func parseTime(value string) time.Time {
	if parsed, err := time.Parse(time.RFC3339, value); err == nil {
		return parsed
	}
	return time.Now().UTC()
}
