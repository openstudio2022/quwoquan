package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	migrationLedgerTable     = "service_schema_migrations"
	migrationLedgerService   = "user-service"
	migrationAdvisoryLockKey = int64(86421091354722161)
	migrationLedgerEnsureSQL = `
CREATE TABLE IF NOT EXISTS service_schema_migrations (
    service_name TEXT NOT NULL,
    filename TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (service_name, filename)
)`
	migrationLedgerSelectSQL = `
SELECT filename, checksum
FROM service_schema_migrations
WHERE service_name = $1`
	migrationLedgerInsertSQL = `
INSERT INTO service_schema_migrations (service_name, filename, checksum)
VALUES ($1, $2, $3)`
)

type migrationFile struct {
	Name     string
	SQL      string
	Checksum string
}

// RunManagedMigrations serializes startup migrations and records applied files,
// so restart/rollout can safely preserve an existing Postgres volume.
func RunManagedMigrations(ctx context.Context, pool *pgxpool.Pool) error {
	migrationDir := resolveManagedMigrationDir()
	if migrationDir == "" {
		return fmt.Errorf("migration directory not found")
	}

	files, err := readMigrationFiles(migrationDir)
	if err != nil {
		return err
	}

	conn, err := pool.Acquire(ctx)
	if err != nil {
		return fmt.Errorf("acquire migration connection: %w", err)
	}
	defer conn.Release()

	tx, err := conn.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin migration transaction: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	if _, err := tx.Exec(ctx, migrationLedgerEnsureSQL); err != nil {
		return fmt.Errorf("ensure migration ledger: %w", err)
	}
	if err := acquireMigrationLock(ctx, tx); err != nil {
		return err
	}

	appliedChecksums, err := loadAppliedMigrationChecksums(ctx, tx)
	if err != nil {
		return err
	}

	for _, file := range files {
		appliedChecksum, alreadyApplied := appliedChecksums[file.Name]
		if alreadyApplied {
			if appliedChecksum != file.Checksum {
				return fmt.Errorf(
					"migration checksum drift for %s: applied=%s current=%s",
					file.Name,
					appliedChecksum,
					file.Checksum,
				)
			}
			continue
		}
		if _, err := tx.Exec(ctx, file.SQL); err != nil {
			return fmt.Errorf("exec %s: %w", file.Name, err)
		}
		if _, err := tx.Exec(ctx, migrationLedgerInsertSQL, migrationLedgerService, file.Name, file.Checksum); err != nil {
			return fmt.Errorf("record %s: %w", file.Name, err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit migrations: %w", err)
	}
	committed = true
	return nil
}

// ManagedMigrationFilenames returns the sorted managed migration filenames
// discovered on disk (the same set RunManagedMigrations applies). Exposed so
// idempotency tests assert the ledger row count against the real migration set
// instead of hardcoding a number that goes stale whenever a migration is added.
func ManagedMigrationFilenames() ([]string, error) {
	dir := resolveManagedMigrationDir()
	if dir == "" {
		return nil, fmt.Errorf("migration directory not found")
	}
	files, err := readMigrationFiles(dir)
	if err != nil {
		return nil, err
	}
	names := make([]string, 0, len(files))
	for _, file := range files {
		names = append(names, file.Name)
	}
	return names, nil
}

func resolveManagedMigrationDir() string {
	candidates := []string{
		findMigrationDir(),
		filepath.Join("..", "internal", "infrastructure", "migration"),
		filepath.Join("services", "user-service", "internal", "infrastructure", "migration"),
		filepath.Join("..", "services", "user-service", "internal", "infrastructure", "migration"),
	}
	if _, currentFile, _, ok := runtime.Caller(0); ok {
		candidates = append(candidates, filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", "migration")))
	}
	for _, candidate := range candidates {
		candidate = strings.TrimSpace(candidate)
		if candidate == "" {
			continue
		}
		if info, err := os.Stat(candidate); err == nil && info.IsDir() {
			return candidate
		}
	}
	return ""
}

func readMigrationFiles(migrationDir string) ([]migrationFile, error) {
	entries, err := os.ReadDir(migrationDir)
	if err != nil {
		return nil, fmt.Errorf("read migration dir: %w", err)
	}

	files := make([]string, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".up.sql") {
			files = append(files, entry.Name())
		}
	}
	sort.Strings(files)

	result := make([]migrationFile, 0, len(files))
	for _, name := range files {
		content, err := os.ReadFile(filepath.Join(migrationDir, name))
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", name, err)
		}
		sql := string(content)
		result = append(result, migrationFile{
			Name:     name,
			SQL:      sql,
			Checksum: migrationChecksum(sql),
		})
	}
	return result, nil
}

func migrationChecksum(sql string) string {
	sum := sha256.Sum256([]byte(sql))
	return hex.EncodeToString(sum[:])
}

func acquireMigrationLock(ctx context.Context, tx pgx.Tx) error {
	rows, err := tx.Query(ctx, `SELECT pg_advisory_xact_lock($1)`, migrationAdvisoryLockKey)
	if err != nil {
		return fmt.Errorf("acquire migration advisory lock: %w", err)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("acquire migration advisory lock: %w", err)
	}
	return nil
}

func loadAppliedMigrationChecksums(ctx context.Context, tx pgx.Tx) (map[string]string, error) {
	rows, err := tx.Query(ctx, migrationLedgerSelectSQL, migrationLedgerService)
	if err != nil {
		return nil, fmt.Errorf("read migration ledger: %w", err)
	}
	defer rows.Close()

	applied := make(map[string]string)
	for rows.Next() {
		var (
			filename string
			checksum string
		)
		if err := rows.Scan(&filename, &checksum); err != nil {
			return nil, fmt.Errorf("scan migration ledger: %w", err)
		}
		applied[filename] = checksum
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("read migration ledger rows: %w", err)
	}
	return applied, nil
}
