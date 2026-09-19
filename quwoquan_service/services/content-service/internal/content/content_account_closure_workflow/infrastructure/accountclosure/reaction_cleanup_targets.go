package accountclosure

import (
	"context"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

func (store *MongoStore) ReactionCleanupTargets(ctx context.Context, event UserAccountClosedEvent) ([]ReactionCleanupTarget, error) {
	targets := make([]ReactionCleanupTarget, 0)
	postCursor, err := store.db.Collection("posts").Find(ctx, bson.M{"authorId": bson.M{"$in": event.SubjectIDs()}}, options.Find().SetProjection(bson.M{"_id": 1, "version": 1}))
	if err != nil {
		return nil, fmt.Errorf("collect closed-account reaction Post targets: %w", err)
	}
	defer postCursor.Close(ctx)
	var posts []struct {
		ID      string `bson:"_id"`
		Version int64  `bson:"version"`
	}
	if err := postCursor.All(ctx, &posts); err != nil {
		return nil, err
	}
	postIDs := make([]string, 0, len(posts))
	for _, post := range posts {
		if post.Version <= 0 {
			return nil, fmt.Errorf("closed-account Post %s has no positive lifecycle version", post.ID)
		}
		postIDs = append(postIDs, post.ID)
		targets = append(targets, ReactionCleanupTarget{Kind: "post", ID: post.ID, SourceVersion: post.Version + 1})
	}
	commentFilter := bson.A{bson.M{"authorId": bson.M{"$in": event.SubjectIDs()}}}
	if len(postIDs) > 0 {
		commentFilter = append(commentFilter, bson.M{"postId": bson.M{"$in": postIDs}})
	}
	commentCursor, err := store.db.Collection("comments").Find(ctx, bson.M{"$or": commentFilter}, options.Find().SetProjection(bson.M{"_id": 1, "version": 1}))
	if err != nil {
		return nil, fmt.Errorf("collect closed-account reaction Comment targets: %w", err)
	}
	defer commentCursor.Close(ctx)
	var comments []struct {
		ID      string `bson:"_id"`
		Version int64  `bson:"version"`
	}
	if err := commentCursor.All(ctx, &comments); err != nil {
		return nil, err
	}
	for _, comment := range comments {
		if comment.Version <= 0 {
			return nil, fmt.Errorf("closed-account Comment %s has no positive lifecycle version", comment.ID)
		}
		targets = append(targets, ReactionCleanupTarget{Kind: "comment", ID: comment.ID, SourceVersion: comment.Version + 1})
	}
	return targets, nil
}
