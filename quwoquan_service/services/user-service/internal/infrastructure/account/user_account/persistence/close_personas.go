package persistence

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

// retireAndScrubPersonas 保留 account/persona id、创建时间、退役时间和 version
// 作为最小归因骨架；公开资料、联系方式、媒体引用与个性化设置全部擦除。
func retireAndScrubPersonas(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	closedAt time.Time,
) error {
	_, err := tx.Exec(ctx, `
UPDATE personas
SET display_name='已注销用户',
    user_handle=NULL,
    phone=NULL,
    email=NULL,
    avatar_url=NULL,
    avatar_version=0,
    background_url=NULL,
    caller_ringtone_id=NULL,
    theme_mode_override=NULL,
    font_size_preset_override=NULL,
    appearance_override_updated_at=NULL,
    is_primary=false,
    is_private=true,
    is_active=false,
    status='retired',
    retired_at=COALESCE(retired_at,$2),
    isolation_level='open',
    purpose_hint=NULL,
    inherits_profile_from_owner=false,
    overridden_profile_fields=ARRAY[]::text[],
    last_profile_sync_at=NULL,
    last_profile_sync_source=NULL,
    last_activated_at=NULL,
    bio='',
    avatar_media_asset_id='',
    background_media_asset_id='',
    updated_at=$2,
    version=version+1
WHERE user_id=$1
  AND (
    display_name IS DISTINCT FROM '已注销用户'
    OR user_handle IS NOT NULL
    OR phone IS NOT NULL
    OR email IS NOT NULL
    OR avatar_url IS NOT NULL
    OR avatar_version<>0
    OR background_url IS NOT NULL
    OR caller_ringtone_id IS NOT NULL
    OR theme_mode_override IS NOT NULL
    OR font_size_preset_override IS NOT NULL
    OR appearance_override_updated_at IS NOT NULL
    OR is_primary
    OR NOT is_private
    OR is_active
    OR status<>'retired'
    OR retired_at IS NULL
    OR isolation_level<>'open'
    OR purpose_hint IS NOT NULL
    OR inherits_profile_from_owner
    OR overridden_profile_fields IS DISTINCT FROM ARRAY[]::text[]
    OR last_profile_sync_at IS NOT NULL
    OR last_profile_sync_source IS NOT NULL
    OR last_activated_at IS NOT NULL
    OR bio<>''
    OR avatar_media_asset_id<>''
    OR background_media_asset_id<>''
    OR updated_at IS DISTINCT FROM $2
  )`, accountID, closedAt)
	if err != nil {
		return fmt.Errorf("retire and scrub personas on account close: %w", err)
	}
	return nil
}
