package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
)

func TestHaversineMeters_UsesGeographicDistance(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	catalog := provider.NewMongoCatalogClient(integrationMongoDB)
	if err := catalog.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure location catalog indexes: %v", err)
	}
	if _, err := integrationMongoDB.Collection("location_pois").InsertOne(ctx, bson.D{
		{Key: "poiId", Value: "distance-target"},
		{Key: "name", Value: "Distance target"},
		{Key: "location", Value: bson.D{
			{Key: "type", Value: "Point"},
			{Key: "coordinates", Value: bson.A{120.1518, 30.2460}},
		}},
	}); err != nil {
		t.Fatalf("seed location catalog: %v", err)
	}

	items, err := catalog.Nearby(ctx, model.NearbyQuery{
		Lat:          30.2431,
		Lng:          120.1505,
		RadiusMeters: 1_000,
		Limit:        10,
	})
	if err != nil {
		t.Fatalf("query nearby catalog: %v", err)
	}
	if len(items) != 1 || items[0].DistanceMeters < 300 || items[0].DistanceMeters > 400 {
		t.Fatalf("nearby distance=%#v, want 300..400m", items)
	}
}

func TestHaversineMeters_SamePointIsZero(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	catalog := provider.NewMongoCatalogClient(integrationMongoDB)
	if err := catalog.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure location catalog indexes: %v", err)
	}
	if _, err := integrationMongoDB.Collection("location_pois").InsertOne(ctx, bson.D{
		{Key: "poiId", Value: "same-point"},
		{Key: "name", Value: "Same point"},
		{Key: "location", Value: bson.D{
			{Key: "type", Value: "Point"},
			{Key: "coordinates", Value: bson.A{120.1505, 30.2431}},
		}},
	}); err != nil {
		t.Fatalf("seed same point: %v", err)
	}

	items, err := catalog.Nearby(ctx, model.NearbyQuery{
		Lat:          30.2431,
		Lng:          120.1505,
		RadiusMeters: 100,
		Limit:        10,
	})
	if err != nil {
		t.Fatalf("query nearby catalog: %v", err)
	}
	if len(items) != 1 || items[0].DistanceMeters != 0 {
		t.Fatalf("same point distance=%#v, want 0", items)
	}
}
