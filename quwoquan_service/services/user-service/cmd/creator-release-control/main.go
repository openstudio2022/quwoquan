// Command creator-release-control exposes exact Creator candidate queries.
package main

import (
	"context"
	"log"
	"os"

	releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"
)

func main() {
	if err := releaseimport.RunReleaseControl(context.Background(), os.Args[1:]); err != nil {
		log.Fatal(err)
	}
}
