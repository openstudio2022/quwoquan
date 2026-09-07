// Command release-control exposes Content-owned release candidate and active
// queries plus expected-current CAS activation.
package main

import (
	"context"
	"log"
	"os"

	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func main() {
	if err := releaseimport.RunReleaseControl(context.Background(), os.Args[1:]); err != nil {
		log.Fatal(err)
	}
}
