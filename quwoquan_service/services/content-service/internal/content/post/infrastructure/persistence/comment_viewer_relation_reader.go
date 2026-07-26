package persistence

import (
	"context"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
)

// CommentViewerRelationMongoReader 从 persona_follow_projection（user 域关注事实
// 在 content 域的只读事件投影）批量判定 viewer 对评论作者的 following/friend 关系。
// 该投影由 recommendation 基础设施的 PersonaRelationshipProjection 消费
// PersonaFollowStateChanged 事实维护，这里只读，不写。
type CommentViewerRelationMongoReader struct {
	relationships *mongo.Collection
}

func NewCommentViewerRelationMongoReader(db *mongo.Database) *CommentViewerRelationMongoReader {
	return &CommentViewerRelationMongoReader{
		relationships: db.Collection("persona_follow_projection"),
	}
}

// ReadViewerRelations 单次 $or 查询取回 viewer↔authors 双向关注事实：
// following = viewer→author；friend = 双向均 following。
func (r *CommentViewerRelationMongoReader) ReadViewerRelations(
	ctx context.Context,
	viewerPersonaID string,
	authorPersonaIDs []string,
) (map[string]commentmodel.ViewerRelation, error) {
	relations := map[string]commentmodel.ViewerRelation{}
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	authors := uniqueNonEmptyStrings(authorPersonaIDs)
	if viewerPersonaID == "" || len(authors) == 0 {
		return relations, nil
	}
	cursor, err := r.relationships.Find(
		ctx,
		bson.M{
			"following": true,
			"$or": bson.A{
				bson.M{"sourcePersonaId": viewerPersonaID, "targetPersonaId": bson.M{"$in": authors}},
				bson.M{"sourcePersonaId": bson.M{"$in": authors}, "targetPersonaId": viewerPersonaID},
			},
		},
		options.Find().SetProjection(bson.M{"sourcePersonaId": 1, "targetPersonaId": 1}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	viewerFollows := map[string]bool{}
	followsViewer := map[string]bool{}
	for cursor.Next(ctx) {
		var row struct {
			SourcePersonaID string `bson:"sourcePersonaId"`
			TargetPersonaID string `bson:"targetPersonaId"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, err
		}
		if row.SourcePersonaID == viewerPersonaID {
			viewerFollows[row.TargetPersonaID] = true
		} else if row.TargetPersonaID == viewerPersonaID {
			followsViewer[row.SourcePersonaID] = true
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	for _, author := range authors {
		switch {
		case viewerFollows[author] && followsViewer[author]:
			relations[author] = commentmodel.ViewerRelationFriend
		case viewerFollows[author]:
			relations[author] = commentmodel.ViewerRelationFollowing
		}
	}
	return relations, nil
}
