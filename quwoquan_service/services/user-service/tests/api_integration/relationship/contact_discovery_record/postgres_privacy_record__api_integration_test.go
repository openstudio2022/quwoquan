package api_integration

import (
	"context"
	"crypto/sha256"
	"fmt"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	contactmodel "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
	contactpersistence "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestContactDiscoveryRecordPostgresPersistsOnlyHashesAndExpires(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := contactpersistence.NewPgContactDiscoveryStore(pool)
		hashedPhone := fmt.Sprintf(
			"sha256:%x",
			sha256.Sum256([]byte("+8613800000001")),
		)
		record := &contactmodel.ContactDiscoveryRecord{
			ID: "contact-discovery-1", OwnerAccountID: "contact-owner",
			HashedPhones: []string{hashedPhone}, Status: "pending",
			ExpireAt: time.Now().UTC().Add(time.Hour), CreatedAt: time.Now().UTC(),
		}
		if err := store.Create(ctx, record); err != nil {
			t.Fatal(err)
		}
		if err := store.Complete(ctx, record.ID, []string{"matched-persona"}); err != nil {
			t.Fatal(err)
		}
		stored, err := store.FindByID(ctx, record.ID)
		if err != nil || stored.Status != "completed" || stored.MatchCount != 1 || len(stored.HashedPhones) != 1 {
			t.Fatalf("ContactDiscoveryRecord drift: value=%+v err=%v", stored, err)
		}
	})
}
