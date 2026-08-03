package ports

import "context"

type Store interface {
	LoadWatermarks(context.Context, string) (map[string]int64, error)
	SaveWatermarks(context.Context, string, map[string]int64) error
}
