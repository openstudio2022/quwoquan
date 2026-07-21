package api_integration

import (
	"fmt"
	"net"
	"os"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"

	"quwoquan_service/internal/platform/testinfra"
)

var productOpsEmbeddedPG *embeddedpostgres.EmbeddedPostgres
var productOpsEmbeddedPGRuntimePath string

func startProductOpsEmbeddedPostgres() string {
	port := reserveProductOpsEmbeddedPostgresPort()
	runtimePath, err := os.MkdirTemp("", "quwoquan-product-ops-api-postgres-*")
	if err != nil {
		panic("product-ops embedded-postgres runtime: " + err.Error())
	}
	productOpsEmbeddedPGRuntimePath = runtimePath
	productOpsEmbeddedPG = embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Version(testinfra.StableEmbeddedPostgresVersion).
			Port(port).
			RuntimePath(runtimePath).
			Username("postgres").
			Password("postgres"),
	)
	if err := productOpsEmbeddedPG.Start(); err != nil {
		_ = os.RemoveAll(runtimePath)
		panic("product-ops embedded-postgres start: " + err.Error())
	}
	return fmt.Sprintf("postgres://postgres:postgres@127.0.0.1:%d/postgres?sslmode=disable", port)
}

func reserveProductOpsEmbeddedPostgresPort() uint32 {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		panic("product-ops embedded-postgres reserve port: " + err.Error())
	}
	defer listener.Close()
	address, ok := listener.Addr().(*net.TCPAddr)
	if !ok {
		panic(fmt.Sprintf("unexpected product-ops postgres listener %T", listener.Addr()))
	}
	return uint32(address.Port)
}
