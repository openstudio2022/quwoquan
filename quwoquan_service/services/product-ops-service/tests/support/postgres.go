package support

import (
	"fmt"
	"net"
	"os"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"

	"quwoquan_service/internal/platform/testinfra"
)

type EmbeddedPostgres struct {
	database    *embeddedpostgres.EmbeddedPostgres
	runtimePath string
}

func StartEmbeddedPostgres() (*EmbeddedPostgres, string, error) {
	port, err := reservePort()
	if err != nil {
		return nil, "", err
	}
	runtimePath, err := os.MkdirTemp("", "quwoquan-product-ops-api-postgres-*")
	if err != nil {
		return nil, "", fmt.Errorf("product-ops embedded-postgres runtime: %w", err)
	}
	database := embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Version(testinfra.StableEmbeddedPostgresVersion).
			Port(port).
			RuntimePath(runtimePath).
			Username("postgres").
			Password("postgres"),
	)
	if err := database.Start(); err != nil {
		_ = os.RemoveAll(runtimePath)
		return nil, "", fmt.Errorf("product-ops embedded-postgres start: %w", err)
	}
	runtime := &EmbeddedPostgres{database: database, runtimePath: runtimePath}
	dsn := fmt.Sprintf(
		"postgres://postgres:postgres@127.0.0.1:%d/postgres?sslmode=disable",
		port,
	)
	return runtime, dsn, nil
}

func (runtime *EmbeddedPostgres) Stop() error {
	if runtime == nil {
		return nil
	}
	stopErr := runtime.database.Stop()
	removeErr := os.RemoveAll(runtime.runtimePath)
	if stopErr != nil {
		return stopErr
	}
	return removeErr
}

func reservePort() (uint32, error) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, fmt.Errorf("reserve product-ops postgres port: %w", err)
	}
	defer listener.Close()
	address, ok := listener.Addr().(*net.TCPAddr)
	if !ok {
		return 0, fmt.Errorf("unexpected product-ops postgres listener %T", listener.Addr())
	}
	return uint32(address.Port), nil
}
