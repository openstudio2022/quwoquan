// source-init由受管环境创建器调用，复用User唯一迁移机制，不开放HTTP。
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	if err := run(ctx); err != nil {
		fmt.Fprintln(os.Stderr, "source initialization rejected")
		os.Exit(1)
	}
}
func acceptedSourceInitIdentity(env, target, dsn string) error {
	if dsn == "" {
		return fmt.Errorf("managed nonproduction inputs required")
	}
	switch env {
	case "alpha", "beta", "gamma":
		if target != "" && target != env+"-local" {
			return fmt.Errorf("managed nonproduction inputs required")
		}
		return nil
	case "prod":
		if target != "prod-sim" {
			return fmt.Errorf("managed nonproduction inputs required")
		}
		return nil
	default:
		return fmt.Errorf("managed nonproduction inputs required")
	}
}

func run(ctx context.Context) error {
	if err := acceptedSourceInitIdentity(
		os.Getenv("QWQ_SOURCE_INIT_ENV"),
		os.Getenv("QWQ_SOURCE_INIT_TARGET"),
		os.Getenv("QWQ_SOURCE_INIT_DSN"),
	); err != nil {
		return err
	}
	pool, err := pgxpool.New(ctx, os.Getenv("QWQ_SOURCE_INIT_DSN"))
	if err != nil {
		return err
	}
	defer pool.Close()
	var count int
	if err := pool.QueryRow(ctx, "SELECT count(*) FROM pg_tables WHERE schemaname='public'").Scan(&count); err != nil {
		return err
	}
	if count != 0 {
		return fmt.Errorf("existing owner tables")
	}
	return persistence.RunManagedMigrations(ctx, pool)
}
