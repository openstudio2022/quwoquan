package repository

import (
	"context"
	"database/sql"
	"fmt"
)

type contextKey string

const txKey contextKey = "repository.tx"

// PGUnitOfWork implements UnitOfWork using PostgreSQL transactions.
type PGUnitOfWork struct {
	db *sql.DB
}

func NewPGUnitOfWork(db *sql.DB) *PGUnitOfWork {
	return &PGUnitOfWork{db: db}
}

func (u *PGUnitOfWork) Begin(ctx context.Context) (context.Context, error) {
	tx, err := u.db.BeginTx(ctx, nil)
	if err != nil {
		return ctx, fmt.Errorf("begin tx: %w", err)
	}
	return context.WithValue(ctx, txKey, tx), nil
}

func (u *PGUnitOfWork) Commit(ctx context.Context) error {
	tx, ok := TxFromContext(ctx)
	if !ok {
		return fmt.Errorf("no transaction in context")
	}
	return tx.Commit()
}

func (u *PGUnitOfWork) Rollback(ctx context.Context) error {
	tx, ok := TxFromContext(ctx)
	if !ok {
		return fmt.Errorf("no transaction in context")
	}
	return tx.Rollback()
}

// TxFromContext extracts the SQL transaction from context.
func TxFromContext(ctx context.Context) (*sql.Tx, bool) {
	tx, ok := ctx.Value(txKey).(*sql.Tx)
	return tx, ok
}
