package persistence

import (
	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/circle-service/internal/application"
)

type ObjectIDGenerator struct{}

var _ application.EntityIDGenerator = ObjectIDGenerator{}

func (ObjectIDGenerator) NewID() string {
	return bson.NewObjectID().Hex()
}
