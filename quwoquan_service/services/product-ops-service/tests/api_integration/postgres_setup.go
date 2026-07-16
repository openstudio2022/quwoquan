package api_integration

import (
	"fmt"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"

	"quwoquan_service/internal/platform/testinfra"
)

var productOpsEmbeddedPG *embeddedpostgres.EmbeddedPostgres

func startProductOpsEmbeddedPostgres() string {
	const port = uint32(15436)
	productOpsEmbeddedPG = embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Version(testinfra.StableEmbeddedPostgresVersion).
			Port(port).
			Username("postgres").
			Password("postgres"),
	)
	if err := productOpsEmbeddedPG.Start(); err != nil {
		panic("product-ops embedded-postgres start: " + err.Error())
	}
	return fmt.Sprintf("postgres://postgres:postgres@127.0.0.1:%d/postgres?sslmode=disable", port)
}
