package model

import (
	"fmt"
	"strings"
	"time"
)

type Tombstone struct {
	PostID    string    `bson:"postId"`
	AuthorID  string    `bson:"authorId"`
	Reason    string    `bson:"reason"`
	DeletedAt time.Time `bson:"deletedAt"`
	ExpireAt  time.Time `bson:"expireAt"`
}

func (tombstone Tombstone) Validate() error {
	if strings.TrimSpace(tombstone.PostID) == "" ||
		strings.TrimSpace(tombstone.Reason) == "" ||
		tombstone.DeletedAt.IsZero() ||
		tombstone.ExpireAt.IsZero() {
		return fmt.Errorf("DeletedPostTombstone requires post identity, reason, deletedAt and expireAt")
	}
	if !tombstone.ExpireAt.After(tombstone.DeletedAt) {
		return fmt.Errorf("DeletedPostTombstone expireAt must follow deletedAt")
	}
	return nil
}
