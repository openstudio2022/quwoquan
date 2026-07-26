package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io/fs"
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
	migrationRoot := resolveManagedMigrationRoot()
	if migrationRoot == "" {
		return fmt.Errorf("migration root not found")
	}

	files, err := readManagedMigrationFiles(migrationRoot)
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
	root := resolveManagedMigrationRoot()
	if root == "" {
		return nil, fmt.Errorf("migration root not found")
	}
	files, err := readManagedMigrationFiles(root)
	if err != nil {
		return nil, err
	}
	names := make([]string, 0, len(files))
	for _, file := range files {
		names = append(names, file.Name)
	}
	return names, nil
}

func resolveManagedMigrationRoot() string {
	candidates := []string{
		filepath.Join("resources", "migrations"),
		filepath.Join("services", "user-service", "resources", "migrations"),
		filepath.Join("..", "services", "user-service", "resources", "migrations"),
	}
	if _, currentFile, _, ok := runtime.Caller(0); ok {
		candidates = append(candidates, filepath.Clean(filepath.Join(
			filepath.Dir(currentFile), "..", "..", "..", "..", "..",
			"resources", "migrations",
		)))
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

func readManagedMigrationFiles(migrationRoot string) ([]migrationFile, error) {
	paths := make([]string, 0)
	err := fs.WalkDir(os.DirFS(migrationRoot), ".", func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".up.sql") {
			paths = append(paths, filepath.ToSlash(path))
		}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("walk migration root: %w", err)
	}
	sort.Slice(paths, func(i, j int) bool {
		leftName := filepath.Base(paths[i])
		rightName := filepath.Base(paths[j])
		if leftName == rightName {
			return paths[i] < paths[j]
		}
		return leftName < rightName
	})

	result := make([]migrationFile, 0, len(paths))
	for _, relativePath := range paths {
		content, err := os.ReadFile(filepath.Join(migrationRoot, filepath.FromSlash(relativePath)))
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", relativePath, err)
		}
		sql := string(content)
		ledgerName := relativePath
		// 001-033 已以 basename 写入生产账本；保持旧身份不变。新对象迁移从
		// context/object 相对路径获得唯一账本键，避免跨对象同名冲突。
		if strings.HasPrefix(relativePath, "account/user_account/") {
			ledgerName = filepath.Base(relativePath)
		}
		result = append(result, migrationFile{
			Name:     ledgerName,
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
