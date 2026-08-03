package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	activityports "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/ports"
)

type MongoProjectionSourceReader struct {
	posts    *mongo.Collection
	comments *mongo.Collection
}

func NewMongoProjectionSourceReader(db *mongo.Database) *MongoProjectionSourceReader {
	if db == nil {
		panic("ProfileInteraction projection source reader requires database")
	}
	return &MongoProjectionSourceReader{
		posts:    db.Collection("posts"),
		comments: db.Collection("comments"),
	}
}

func (r *MongoProjectionSourceReader) FindPost(
	ctx context.Context,
	postID string,
) (activityports.PostSlice, bool, error) {
	var document struct {
		ID                        string    `bson:"_id"`
		Version                   int64     `bson:"version"`
		AuthorPersonaID           string    `bson:"authorId"`
		AuthorDisplayNameSnapshot string    `bson:"authorDisplayNameSnapshot"`
		AuthorAvatarURLSnapshot   string    `bson:"authorAvatarUrlSnapshot"`
		ContentType               string    `bson:"contentType"`
		Title                     string    `bson:"title"`
		Body                      string    `bson:"body"`
		Summary                   string    `bson:"summary"`
		CoverURL                  string    `bson:"coverUrl"`
		MediaURLs                 []string  `bson:"mediaUrls"`
		Status                    string    `bson:"status"`
		Visibility                string    `bson:"visibility"`
		DeletedAt                 time.Time `bson:"deletedAt"`
	}
	err := r.posts.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(postID)},
		options.FindOne().SetProjection(bson.M{
			"_id":                       1,
			"version":                   1,
			"authorId":                  1,
			"authorDisplayNameSnapshot": 1,
			"authorAvatarUrlSnapshot":   1,
			"contentType":               1,
			"title":                     1,
			"body":                      1,
			"summary":                   1,
			"coverUrl":                  1,
			"mediaUrls":                 1,
			"status":                    1,
			"visibility":                1,
			"deletedAt":                 1,
		}),
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return activityports.PostSlice{}, false, nil
	}
	if err != nil {
		return activityports.PostSlice{}, false, fmt.Errorf("read Post projection source: %w", err)
	}
	return activityports.PostSlice{
		ID:                        document.ID,
		Version:                   document.Version,
		AuthorPersonaID:           document.AuthorPersonaID,
		AuthorDisplayNameSnapshot: document.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   document.AuthorAvatarURLSnapshot,
		ContentType:               document.ContentType,
		Title:                     document.Title,
		Body:                      document.Body,
		Summary:                   document.Summary,
		CoverURL:                  document.CoverURL,
		MediaURLs:                 document.MediaURLs,
		Status:                    document.Status,
		Visibility:                document.Visibility,
		DeletedAt:                 document.DeletedAt,
	}, true, nil
}

func (r *MongoProjectionSourceReader) FindComment(
	ctx context.Context,
	commentID string,
) (activityports.CommentSlice, bool, error) {
	var document struct {
		ID                        string    `bson:"_id"`
		Version                   int64     `bson:"version"`
		PostID                    string    `bson:"postId"`
		AuthorPersonaID           string    `bson:"authorId"`
		AuthorDisplayNameSnapshot string    `bson:"authorDisplayNameSnapshot"`
		AuthorAvatarURLSnapshot   string    `bson:"authorAvatarUrlSnapshot"`
		Content                   string    `bson:"content"`
		ReplyToCommentID          string    `bson:"replyToCommentId"`
		ReplyToPersonaID          string    `bson:"replyToUserId"`
		ParentCommentID           string    `bson:"parentCommentId"`
		Status                    string    `bson:"status"`
		CreatedAt                 time.Time `bson:"createdAt"`
	}
	err := r.comments.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(commentID)},
		options.FindOne().SetProjection(bson.M{
			"_id":                       1,
			"version":                   1,
			"postId":                    1,
			"authorId":                  1,
			"authorDisplayNameSnapshot": 1,
			"authorAvatarUrlSnapshot":   1,
			"content":                   1,
			"replyToCommentId":          1,
			"replyToUserId":             1,
			"parentCommentId":           1,
			"status":                    1,
			"createdAt":                 1,
		}),
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return activityports.CommentSlice{}, false, nil
	}
	if err != nil {
		return activityports.CommentSlice{}, false, fmt.Errorf("read Comment projection source: %w", err)
	}
	return activityports.CommentSlice{
		ID:                        document.ID,
		Version:                   document.Version,
		PostID:                    document.PostID,
		AuthorPersonaID:           document.AuthorPersonaID,
		AuthorDisplayNameSnapshot: document.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   document.AuthorAvatarURLSnapshot,
		Content:                   document.Content,
		ReplyToCommentID:          document.ReplyToCommentID,
		ReplyToPersonaID:          document.ReplyToPersonaID,
		ParentCommentID:           document.ParentCommentID,
		Status:                    document.Status,
		CreatedAt:                 document.CreatedAt,
	}, true, nil
}

var _ activityports.ProjectionSourceReader = (*MongoProjectionSourceReader)(nil)
