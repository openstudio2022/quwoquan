package publicweb

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
)

const webBudgetReservationTTL = 2 * time.Minute

type mongoBudgetReservation struct {
	ID           string    `bson:"id"`
	AllowedBytes int64     `bson:"allowedBytes"`
	ExpiresAt    time.Time `bson:"expiresAt"`
}

type mongoBudgetDocument struct {
	ID           string                   `bson:"_id"`
	Revision     int64                    `bson:"revision"`
	UsedPages    int                      `bson:"usedPages"`
	UsedBytes    int64                    `bson:"usedBytes"`
	Reservations []mongoBudgetReservation `bson:"reservations"`
	UpdatedAt    time.Time                `bson:"updatedAt"`
}

type MongoRunBudgetGate struct {
	collection *mongo.Collection
	limits     application.RunBudgetLimits
	now        func() time.Time
}

func NewMongoRunBudgetGate(
	database *mongo.Database,
	limits application.RunBudgetLimits,
) *MongoRunBudgetGate {
	if database == nil || limits.MaxPages <= 0 || limits.MaxBytes <= 0 {
		panic("public web durable budget dependencies are required")
	}
	return &MongoRunBudgetGate{
		collection: database.Collection("assistant_run_web_budgets"),
		limits:     limits,
		now:        time.Now,
	}
}

func (g *MongoRunBudgetGate) EnsureIndexes(ctx context.Context) error {
	_, err := g.collection.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "updatedAt", Value: -1}},
		Options: options.Index().SetName("idx_web_budgets_updated"),
	})
	if err != nil {
		return fmt.Errorf("create public web budget indexes: %w", err)
	}
	return nil
}

func (g *MongoRunBudgetGate) ReserveFetch(
	ctx context.Context,
	runID string,
	requestedBytes int64,
) (application.BudgetReservation, error) {
	runID = strings.TrimSpace(runID)
	if runID == "" || requestedBytes <= 0 {
		return nil, application.ErrBudgetExhausted
	}
	now := g.now().UTC()
	if err := g.ensure(ctx, runID, now); err != nil {
		return nil, err
	}
	if err := g.reclaimExpired(ctx, runID, now); err != nil {
		return nil, err
	}
	for attempt := 0; attempt < 8; attempt++ {
		current, err := g.read(ctx, runID)
		if err != nil {
			return nil, err
		}
		reservedBytes := int64(0)
		for _, reservation := range current.Reservations {
			reservedBytes += reservation.AllowedBytes
		}
		if current.UsedPages+len(current.Reservations) >= g.limits.MaxPages {
			return nil, application.ErrBudgetExhausted
		}
		remaining := g.limits.MaxBytes - current.UsedBytes - reservedBytes
		if remaining <= 0 {
			return nil, application.ErrBudgetExhausted
		}
		if requestedBytes < remaining {
			remaining = requestedBytes
		}
		id, err := budgetReservationID()
		if err != nil {
			return nil, err
		}
		reservation := mongoBudgetReservation{
			ID:           id,
			AllowedBytes: remaining,
			ExpiresAt:    now.Add(webBudgetReservationTTL),
		}
		result, err := g.collection.UpdateOne(ctx, bson.M{
			"_id": runID, "revision": current.Revision,
		}, bson.M{
			"$inc":  bson.M{"revision": 1},
			"$push": bson.M{"reservations": reservation},
			"$set":  bson.M{"updatedAt": now},
		})
		if err != nil {
			return nil, err
		}
		if result.MatchedCount == 1 {
			return &mongoBudgetLease{
				gate: g, runID: runID, reservation: reservation, ctx: ctx,
			}, nil
		}
	}
	return nil, fmt.Errorf("%w: reservation CAS contention", application.ErrBudgetUnavailable)
}

func (g *MongoRunBudgetGate) ensure(ctx context.Context, runID string, now time.Time) error {
	_, err := g.collection.UpdateOne(ctx, bson.M{"_id": runID}, bson.M{
		"$setOnInsert": bson.M{
			"revision": 0, "usedPages": 0, "usedBytes": int64(0),
			"reservations": bson.A{}, "updatedAt": now,
		},
	}, options.UpdateOne().SetUpsert(true))
	return err
}

func (g *MongoRunBudgetGate) reclaimExpired(
	ctx context.Context,
	runID string,
	now time.Time,
) error {
	_, err := g.collection.UpdateOne(ctx, bson.M{"_id": runID}, bson.M{
		"$pull": bson.M{"reservations": bson.M{"expiresAt": bson.M{"$lte": now}}},
		"$inc":  bson.M{"revision": 1},
		"$set":  bson.M{"updatedAt": now},
	})
	return err
}

func (g *MongoRunBudgetGate) read(
	ctx context.Context,
	runID string,
) (mongoBudgetDocument, error) {
	var current mongoBudgetDocument
	err := g.collection.FindOne(ctx, bson.M{"_id": runID}).Decode(&current)
	return current, err
}

type mongoBudgetLease struct {
	gate        *MongoRunBudgetGate
	runID       string
	reservation mongoBudgetReservation
	ctx         context.Context
	done        bool
}

func (r *mongoBudgetLease) AllowedBytes() int64 { return r.reservation.AllowedBytes }

func (r *mongoBudgetLease) Commit(actualBytes int64) error {
	if r.done || actualBytes < 0 || actualBytes > r.reservation.AllowedBytes {
		return application.ErrBudgetExhausted
	}
	now := r.gate.now().UTC()
	result, err := r.gate.collection.UpdateOne(r.ctx, bson.M{
		"_id": r.runID,
		"reservations": bson.M{"$elemMatch": bson.M{
			"id":        r.reservation.ID,
			"expiresAt": bson.M{"$gt": now},
		}},
	}, bson.M{
		"$pull": bson.M{"reservations": bson.M{"id": r.reservation.ID}},
		"$inc": bson.M{
			"revision": 1, "usedPages": 1, "usedBytes": actualBytes,
		},
		"$set": bson.M{"updatedAt": now},
	})
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return application.ErrBudgetExhausted
	}
	r.done = true
	return nil
}

func (r *mongoBudgetLease) Release() {
	if r.done {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_, _ = r.gate.collection.UpdateOne(ctx, bson.M{
		"_id": r.runID, "reservations.id": r.reservation.ID,
	}, bson.M{
		"$pull": bson.M{"reservations": bson.M{"id": r.reservation.ID}},
		"$inc":  bson.M{"revision": 1},
		"$set":  bson.M{"updatedAt": r.gate.now().UTC()},
	})
	r.done = true
}

func budgetReservationID() (string, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return "web_budget_" + hex.EncodeToString(raw[:]), nil
}
