// Command migrate-content-release-state performs the one-time, quiesced
// conversion of the historical Content active release row and its indexes.
package main

import (
	"context"
	"log"
	"os"

	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func main() {
	if err := releaseimport.RunLegacyReleaseStateMigration(context.Background(), os.Args[1:]); err != nil {
		log.Fatal(err)
	}
}
