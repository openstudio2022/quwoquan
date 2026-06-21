package persistence

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
)

const commentReactionsCollection = "comment_reactions"

// commentReactionDoc is the authoritative per-user comment reaction record.
type commentReactionDoc struct {
	ID        string    `bson:"_id"`
	CommentID string    `bson:"commentId"`
	UserID    string    `bson:"userId"`
	Reaction  string    `bson:"reaction"`
	UpdatedAt time.Time `bson:"updatedAt"`
}

func commentReactionID(commentID, userID string) string {
	return strings.TrimSpace(commentID) + "|" + strings.TrimSpace(userID)
}

// MongoCommentReactionStore is the authoritative MongoDB store for three-state
// comment reactions. Counts are derived from membership so they never drift.
type MongoCommentReactionStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewMongoCommentReactionStore(db *mongo.Database, logger *slog.Logger) *MongoCommentReactionStore {
	if logger == nil {
		logger = slog.Default()
	}
	s := &MongoCommentReactionStore{coll: db.Collection(commentReactionsCollection), logger: logger}
	s.ensureIndexes()
	return s
}

var _ commentdomain.ReactionStore = (*MongoCommentReactionStore)(nil)

func (s *MongoCommentReactionStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	indexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "commentId", Value: 1}, {Key: "reaction", Value: 1}}, Options: options.Index().SetName("idx_comment_reactions_comment")},
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "commentId", Value: 1}}, Options: options.Index().SetName("idx_comment_reactions_user")},
	}
	for _, idx := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
			s.logger.Warn("comment_reaction_store: index creation failed", slog.String("error", err.Error()))
		}
	}
}

func (s *MongoCommentReactionStore) Set(ctx context.Context, commentID, userID string, reaction commentdomain.Reaction) error {
	commentID = strings.TrimSpace(commentID)
	userID = strings.TrimSpace(userID)
	id := commentReactionID(commentID, userID)
	if reaction == commentdomain.ReactionNone {
		_, err := s.coll.DeleteOne(ctx, bson.M{"_id": id})
		return err
	}
	_, err := s.coll.ReplaceOne(
		ctx,
		bson.M{"_id": id},
		commentReactionDoc{
			ID:        id,
			CommentID: commentID,
			UserID:    userID,
			Reaction:  string(reaction),
			UpdatedAt: time.Now().UTC(),
		},
		options.Replace().SetUpsert(true),
	)
	return err
}

func (s *MongoCommentReactionStore) Get(ctx context.Context, commentID, userID string) (commentdomain.Reaction, error) {
	var doc commentReactionDoc
	err := s.coll.FindOne(ctx, bson.M{"_id": commentReactionID(commentID, userID)}).Decode(&doc)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return commentdomain.ReactionNone, nil
		}
		return commentdomain.ReactionNone, err
	}
	r, _ := commentdomain.NormalizeReaction(doc.Reaction)
	return r, nil
}

func (s *MongoCommentReactionStore) Counts(ctx context.Context, commentID string) (int64, int64, error) {
	commentID = strings.TrimSpace(commentID)
	like, err := s.coll.CountDocuments(ctx, bson.M{"commentId": commentID, "reaction": string(commentdomain.ReactionLike)})
	if err != nil {
		return 0, 0, err
	}
	dislike, err := s.coll.CountDocuments(ctx, bson.M{"commentId": commentID, "reaction": string(commentdomain.ReactionDislike)})
	if err != nil {
		return 0, 0, err
	}
	return like, dislike, nil
}

func (s *MongoCommentReactionStore) ReactionsForUser(
	ctx context.Context, userID string, commentIDs []string,
) (map[string]commentdomain.Reaction, error) {
	out := map[string]commentdomain.Reaction{}
	if len(commentIDs) == 0 {
		return out, nil
	}
	cur, err := s.coll.Find(ctx, bson.M{"userId": strings.TrimSpace(userID), "commentId": bson.M{"$in": commentIDs}})
	if err != nil {
		return nil, err
	}
	var docs []commentReactionDoc
	if err := cur.All(ctx, &docs); err != nil {
		return nil, err
	}
	for _, d := range docs {
		if r, ok := commentdomain.NormalizeReaction(d.Reaction); ok && r != commentdomain.ReactionNone {
			out[d.CommentID] = r
		}
	}
	return out, nil
}

func (s *MongoCommentReactionStore) PurgeComment(ctx context.Context, commentID string) error {
	_, err := s.coll.DeleteMany(ctx, bson.M{"commentId": strings.TrimSpace(commentID)})
	return err
}
