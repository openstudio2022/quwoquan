package api_integration

import (
	"context"
	"testing"
	"time"

	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"
)

// TestHomepageLocationIsIndexableAndNearQueryable 用真实 Mongo 证明 location
// 的落库形状真的能被 idx_homepages_location（2dsphere）建键并被 $nearSphere 召回。
// 这是「附近」链路唯一无法用内存 double 证明的一段：domain GeoPoint 的
// {latitude, longitude} 嵌套文档会被 2dsphere 当作 legacy [x, y] 坐标对读取，
// 纬度落到 y 位置后越界，写入直接被拒。
func TestHomepageLocationIsIndexableAndNearQueryable(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	container, err := tryRunReviewMongoContainer(ctx)
	if err != nil {
		t.Fatalf("mongo testcontainer unavailable: %v", err)
	}
	defer func() { _ = container.Terminate(context.Background()) }()
	uri, err := container.ConnectionString(ctx)
	if err != nil {
		t.Fatalf("mongo connection string: %v", err)
	}
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(uri).SetDirect(true))
	if err != nil {
		t.Fatalf("mongo connect: %v", err)
	}
	defer func() { _ = client.Disconnect(context.Background()) }()
	database := client.Database("entity_homepage_geo_it")
	store := homepagepersistence.NewMongoHomepageStore(database, true)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure homepage indexes: %v", err)
	}
	commands, err := homepageapp.NewCommandFacade(store, store)
	if err != nil {
		t.Fatalf("new command facade: %v", err)
	}
	queries, err := homepageapp.NewQueryFacade(store, store)
	if err != nil {
		t.Fatalf("new query facade: %v", err)
	}

	// 西湖与九寨沟：同一集合内两点，相距约 1,100km，可区分半径召回。
	westLake := homepagemodel.GeoPoint{Latitude: 30.2447, Longitude: 120.1497}
	jiuzhaigou := homepagemodel.GeoPoint{Latitude: 33.2601, Longitude: 103.9182}
	created, err := commands.IntakeCandidate(
		ctx,
		homepageapp.CommandMeta{ActorID: "operator", IdempotencyKey: "geo-west-lake"},
		homepageapp.Input{
			Title: "西湖", HomepageType: "sight",
			CanonicalEntityID: "entity:sight:west_lake",
			City:              "杭州市",
			Location:          &westLake,
		},
		"official_seed",
	)
	if err != nil {
		t.Fatalf("intake west lake with location: %v", err)
	}
	if _, err := commands.IntakeCandidate(
		ctx,
		homepageapp.CommandMeta{ActorID: "operator", IdempotencyKey: "geo-jiuzhaigou"},
		homepageapp.Input{
			Title: "九寨沟", HomepageType: "sight",
			CanonicalEntityID: "entity:sight:jiuzhaigou",
			City:              "阿坝藏族羌族自治州",
			Location:          &jiuzhaigou,
		},
		"official_seed",
	); err != nil {
		t.Fatalf("intake jiuzhaigou with location: %v", err)
	}

	// 读回聚合：wire/domain 仍是 latitude/longitude，且不得轴交换。
	view, err := queries.Get(ctx, created.ID, "", true)
	if err != nil {
		t.Fatalf("get homepage: %v", err)
	}
	if view.Location == nil ||
		view.Location.Latitude != westLake.Latitude ||
		view.Location.Longitude != westLake.Longitude {
		t.Fatalf("location must round-trip through GeoJSON unchanged, got %+v", view.Location)
	}

	// 落库形状必须是 GeoJSON Point，coordinates 为 [longitude, latitude]。
	var raw struct {
		Location *struct {
			Type        string    `bson:"type"`
			Coordinates []float64 `bson:"coordinates"`
			Latitude    *float64  `bson:"latitude"`
			Longitude   *float64  `bson:"longitude"`
		} `bson:"location"`
	}
	if err := database.Collection("homepages").
		FindOne(ctx, bson.M{"_id": created.ID}).Decode(&raw); err != nil {
		t.Fatalf("read raw homepage document: %v", err)
	}
	if raw.Location == nil {
		t.Fatalf("location must persist on the document")
	}
	if raw.Location.Latitude != nil || raw.Location.Longitude != nil {
		t.Fatalf("location must not persist the legacy latitude/longitude pair, got %+v", *raw.Location)
	}
	if raw.Location.Type != "Point" || len(raw.Location.Coordinates) != 2 {
		t.Fatalf("location must persist as GeoJSON Point, got %+v", *raw.Location)
	}
	if raw.Location.Coordinates[0] != westLake.Longitude ||
		raw.Location.Coordinates[1] != westLake.Latitude {
		t.Fatalf("coordinates must be [longitude, latitude], got %v", raw.Location.Coordinates)
	}

	// 2dsphere 真检索：以西湖为中心 50km 内只应召回西湖。
	cursor, err := database.Collection("homepages").Find(ctx, bson.M{
		"location": bson.M{
			"$nearSphere": bson.M{
				"$geometry": bson.M{
					"type":        "Point",
					"coordinates": bson.A{westLake.Longitude, westLake.Latitude},
				},
				"$maxDistance": 50_000,
			},
		},
	})
	if err != nil {
		t.Fatalf("nearSphere query: %v", err)
	}
	var near []bson.M
	if err := cursor.All(ctx, &near); err != nil {
		t.Fatalf("decode nearSphere results: %v", err)
	}
	if len(near) != 1 || near[0]["_id"] != created.ID {
		ids := make([]any, 0, len(near))
		for _, row := range near {
			ids = append(ids, row["_id"])
		}
		t.Fatalf("50km radius around 西湖 must return only 西湖, got %v", ids)
	}
}
