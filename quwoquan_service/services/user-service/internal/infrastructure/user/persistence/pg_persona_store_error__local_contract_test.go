package persistence

import (
	"errors"
	"testing"

	"github.com/jackc/pgx/v5/pgconn"

	repository "quwoquan_service/services/user-service/internal/domain/user/ports"
)

func TestPersonaPersistenceMapsHandleConflictWithoutLeakingPgError(t *testing.T) {
	mapped := mapPersonaPersistenceError(&pgconn.PgError{
		Code:           "23505",
		ConstraintName: "uq_personas_user_handle",
	})

	if !errors.Is(mapped, repository.ErrPersonaHandleConflict) {
		t.Fatalf("expected persona handle conflict, got %v", mapped)
	}
	var pgErr *pgconn.PgError
	if errors.As(mapped, &pgErr) {
		t.Fatal("pgconn error must not cross the infrastructure boundary")
	}
}

func TestPersonaPersistenceMapsOtherPgErrorsToStableFailure(t *testing.T) {
	mapped := mapPersonaPersistenceError(&pgconn.PgError{
		Code:    "23503",
		Message: "foreign key violation",
	})

	if !errors.Is(mapped, repository.ErrPersonaPersistence) {
		t.Fatalf("expected stable persona persistence failure, got %v", mapped)
	}
	var pgErr *pgconn.PgError
	if errors.As(mapped, &pgErr) {
		t.Fatal("pgconn error must not cross the infrastructure boundary")
	}
}
