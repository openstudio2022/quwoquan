package main

import (
	"encoding/json"
	"fmt"
	"os"
	post "quwoquan_service/services/content-service/internal/content/post/application"
)

func main() {
	raw, _ := os.ReadFile(os.Args[1])
	var e map[string]any
	if json.Unmarshal(raw, &e) != nil {
		panic("decode")
	}
	var m string
	var err error
	if len(os.Args) > 2 && os.Args[2] == "safe" {
		m, err = post.SafeProjectionMap(e)
	} else {
		m, err = post.SerializeEnvelopeMap(e)
	}
	if err != nil {
		panic(err)
	}
	fmt.Print(m)
}
