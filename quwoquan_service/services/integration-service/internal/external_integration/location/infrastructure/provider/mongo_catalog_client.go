package provider

import (
	"context"
	"fmt"
	"math"
	"regexp"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
)

const locationCatalogCollection = "location_pois"

type MongoCatalogClient struct {
	collection *mongo.Collection
}

var _ ports.LocationProvider = (*MongoCatalogClient)(nil)

type catalogPOIDocument struct {
	POIID          string `bson:"poiId"`
	Name           string `bson:"name"`
	Address        string `bson:"address"`
	CityCode       string `bson:"cityCode"`
	AdCode         string `bson:"adCode"`
	DistanceMeters int    `bson:"distanceMeters"`
	Location       struct {
		Type        string    `bson:"type"`
		Coordinates []float64 `bson:"coordinates"`
	} `bson:"location"`
}

func NewMongoCatalogClient(database *mongo.Database) *MongoCatalogClient {
	return &MongoCatalogClient{
		collection: database.Collection(locationCatalogCollection),
	}
}

func (c *MongoCatalogClient) EnsureIndexes(ctx context.Context) error {
	_, err := c.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "poiId", Value: 1}},
			Options: options.Index().SetName("uq_location_poi_id").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "location", Value: "2dsphere"}},
			Options: options.Index().SetName("idx_location_poi_geo"),
		},
		{
			Keys: bson.D{
				{Key: "cityCode", Value: 1},
				{Key: "name", Value: 1},
			},
			Options: options.Index().SetName("idx_location_poi_city_name"),
		},
	})
	if err != nil {
		return fmt.Errorf("create location catalog indexes: %w", err)
	}
	return nil
}

func (c *MongoCatalogClient) Nearby(
	ctx context.Context,
	query model.NearbyQuery,
) ([]model.POI, error) {
	filter := bson.D{{
		Key: "location",
		Value: bson.D{{
			Key: "$near",
			Value: bson.D{
				{
					Key: "$geometry",
					Value: bson.D{
						{Key: "type", Value: "Point"},
						{Key: "coordinates", Value: bson.A{query.Lng, query.Lat}},
					},
				},
				{Key: "$maxDistance", Value: query.RadiusMeters},
			},
		}},
	}}
	return c.find(ctx, filter, query.Limit, &query)
}

func (c *MongoCatalogClient) Search(
	ctx context.Context,
	query model.SearchRequestFact,
) ([]model.POI, error) {
	normalized := strings.TrimSpace(query.Query)
	if normalized == "" {
		return []model.POI{}, nil
	}
	pattern := bson.Regex{Pattern: regexp.QuoteMeta(normalized), Options: "i"}
	filter := bson.D{{
		Key: "$or",
		Value: bson.A{
			bson.D{{Key: "name", Value: pattern}},
			bson.D{{Key: "address", Value: pattern}},
		},
	}}
	if cityCode := strings.TrimSpace(query.CityCode); cityCode != "" {
		filter = append(filter, bson.E{Key: "cityCode", Value: cityCode})
	}
	return c.find(ctx, filter, query.Limit, nil)
}

func (c *MongoCatalogClient) find(
	ctx context.Context,
	filter bson.D,
	limit int,
	nearby *model.NearbyQuery,
) ([]model.POI, error) {
	findOptions := options.Find().SetLimit(int64(limit))
	cursor, err := c.collection.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, fmt.Errorf("query location catalog: %w", err)
	}
	defer cursor.Close(ctx)

	var documents []catalogPOIDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, fmt.Errorf("decode location catalog: %w", err)
	}
	items := make([]model.POI, 0, len(documents))
	for _, document := range documents {
		if strings.TrimSpace(document.POIID) == "" ||
			strings.TrimSpace(document.Name) == "" ||
			len(document.Location.Coordinates) != 2 {
			continue
		}
		longitude := document.Location.Coordinates[0]
		latitude := document.Location.Coordinates[1]
		distanceMeters := document.DistanceMeters
		if nearby != nil {
			distanceMeters = haversineMeters(
				nearby.Lat,
				nearby.Lng,
				latitude,
				longitude,
			)
		}
		items = append(items, model.POI{
			ID:             document.POIID,
			Name:           document.Name,
			Address:        document.Address,
			Latitude:       latitude,
			Longitude:      longitude,
			DistanceMeters: distanceMeters,
			CityCode:       document.CityCode,
			AdCode:         document.AdCode,
		})
	}
	return items, nil
}

func haversineMeters(latA, lngA, latB, lngB float64) int {
	const earthRadiusMeters = 6_371_000
	toRadians := func(degrees float64) float64 {
		return degrees * math.Pi / 180
	}
	latARadians := toRadians(latA)
	latBRadians := toRadians(latB)
	latDelta := toRadians(latB - latA)
	lngDelta := toRadians(lngB - lngA)
	a := math.Sin(latDelta/2)*math.Sin(latDelta/2) +
		math.Cos(latARadians)*math.Cos(latBRadians)*
			math.Sin(lngDelta/2)*math.Sin(lngDelta/2)
	return int(math.Round(earthRadiusMeters * 2 * math.Atan2(math.Sqrt(a), math.Sqrt(1-a))))
}
