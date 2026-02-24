package repository

import (
	"context"
	"encoding/json"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

type mongoRepository struct {
	coll   *mongo.Collection
	pk     string
	fields []string
}

func newMongoRepository(f *Factory, entityName string) (*mongoRepository, error) {
	fieldDefs, err := f.reg.GetFieldPolicy(entityName)
	if err != nil {
		return nil, fmt.Errorf("get field policy for %q: %w", entityName, err)
	}

	pk := "_id"
	fields := make([]string, 0, len(fieldDefs))
	for _, fd := range fieldDefs {
		fields = append(fields, fd.Name)
		for _, c := range fd.Constraints {
			if c == "PK" {
				pk = fd.Name
			}
		}
	}

	collName := toSnakeCase(entityName) + "s"
	coll := f.mongoDB.Collection(collName)

	return &mongoRepository{
		coll:   coll,
		pk:     pk,
		fields: fields,
	}, nil
}

func (r *mongoRepository) FindByID(ctx context.Context, id string) (*map[string]any, error) {
	filter := bson.M{r.pk: id}
	result := r.coll.FindOne(ctx, filter)
	if result.Err() != nil {
		if result.Err() == mongo.ErrNoDocuments {
			return nil, nil
		}
		return nil, result.Err()
	}

	var doc map[string]any
	if err := result.Decode(&doc); err != nil {
		return nil, err
	}
	return &doc, nil
}

func (r *mongoRepository) FindAll(ctx context.Context, q Query) (*Page[map[string]any], error) {
	filter := buildMongoFilter(q.Filter)
	limit := q.Limit
	if limit <= 0 {
		limit = 20
	}

	opts := options.Find().SetLimit(int64(limit))
	if len(q.Sort) > 0 {
		sort := bson.D{}
		for _, s := range q.Sort {
			sort = append(sort, bson.E{Key: s.Field, Value: int(s.Direction)})
		}
		opts.SetSort(sort)
	}

	cursor, err := r.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, fmt.Errorf("find %s: %w", r.coll.Name(), err)
	}
	defer cursor.Close(ctx)

	var items []map[string]any
	if err := cursor.All(ctx, &items); err != nil {
		return nil, fmt.Errorf("decode results: %w", err)
	}

	var nextCursor string
	if len(items) == limit {
		last := items[len(items)-1]
		if pkVal, ok := last[r.pk]; ok {
			cursorBytes, _ := json.Marshal(pkVal)
			nextCursor = string(cursorBytes)
		}
	}

	return &Page[map[string]any]{
		Items:      items,
		NextCursor: nextCursor,
	}, nil
}

func (r *mongoRepository) Create(ctx context.Context, entity *map[string]any) error {
	_, err := r.coll.InsertOne(ctx, *entity)
	return err
}

func (r *mongoRepository) Update(ctx context.Context, id string, entity *map[string]any) error {
	filter := bson.M{r.pk: id}
	update := bson.M{"$set": *entity}
	_, err := r.coll.UpdateOne(ctx, filter, update)
	return err
}

func (r *mongoRepository) Delete(ctx context.Context, id string) error {
	filter := bson.M{r.pk: id}
	_, err := r.coll.DeleteOne(ctx, filter)
	return err
}

func (r *mongoRepository) Count(ctx context.Context, f Filter) (int64, error) {
	filter := buildMongoFilter(f)
	return r.coll.CountDocuments(ctx, filter)
}

func buildMongoFilter(f Filter) bson.M {
	if len(f.Conditions) == 0 {
		return bson.M{}
	}

	conditions := make([]bson.M, 0, len(f.Conditions))
	for _, c := range f.Conditions {
		conditions = append(conditions, bson.M{c.Field: bson.M{mongoOperator(c.Operator): c.Value}})
	}

	if f.Logic == Or {
		return bson.M{"$or": conditions}
	}
	return bson.M{"$and": conditions}
}

func mongoOperator(op Operator) string {
	switch op {
	case Eq:
		return "$eq"
	case Ne:
		return "$ne"
	case Gt:
		return "$gt"
	case Gte:
		return "$gte"
	case Lt:
		return "$lt"
	case Lte:
		return "$lte"
	case In:
		return "$in"
	case Regex:
		return "$regex"
	default:
		return "$eq"
	}
}
