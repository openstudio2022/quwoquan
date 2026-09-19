package collection

import (
	"context"
	"errors"
	"slices"
	"strings"
	"time"
)

// Failure 是公开端口的闭集失败；边界将其映射为 canonical runtime error。
type Failure string

func (f Failure) Error() string { return string(f) }

const (
	Invalid      Failure = "invalid_argument"
	Unavailable  Failure = "post_collection_unavailable"
	Conflict     Failure = "version_conflict"
	Unauthorized Failure = "unauthorized"
	StorageRead  Failure = "storage_read_failed"
	StorageWrite Failure = "storage_write_failed"
)

type Visibility string

const (
	Public  Visibility = "public"
	Private Visibility = "private"
)

type Status string

const (
	Active  Status = "active"
	Deleted Status = "deleted"
)

type Collection struct {
	ID           string
	Owner        string
	Name         string
	CoverAssetID string
	Visibility   Visibility
	PostIDs      []string
	Version      int64
	Status       Status
	UpdatedAt    time.Time
}

// Store 仅供合集 owner 使用，CompareAndSwap 必须原子校验 owner 和版本。
type Store interface {
	Find(context.Context, string) (Collection, bool, error)
	CompareAndSwap(context.Context, Collection, int64) (bool, error)
}

type Save struct {
	ID              string
	ExpectedVersion int64
	Name            string
	CoverAssetID    string
	Visibility      Visibility
	PostIDs         []string
}

func (s Save) Validate() error {
	if strings.TrimSpace(s.ID) == "" || len(s.ID) > 128 || s.ExpectedVersion < 0 || strings.TrimSpace(s.Name) == "" || len([]rune(s.Name)) > 120 || len(s.PostIDs) > 100 {
		return Invalid
	}
	if s.Visibility != Public && s.Visibility != Private {
		return Invalid
	}
	seen := make(map[string]bool, len(s.PostIDs))
	for _, id := range s.PostIDs {
		if strings.TrimSpace(id) == "" || id != strings.TrimSpace(id) || len(id) > 128 || seen[id] {
			return Invalid
		}
		seen[id] = true
	}
	return nil
}
func (c Collection) Same(s Save) bool {
	return c.ID == s.ID && c.Name == s.Name && c.CoverAssetID == s.CoverAssetID && c.Visibility == s.Visibility && slices.Equal(c.PostIDs, s.PostIDs) && c.Status == Active
}
func Is(err error, failure Failure) bool { return errors.Is(err, failure) }
