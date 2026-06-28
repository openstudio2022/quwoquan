import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/services/connection/connection_models.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/constants/plaza_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_state_views.dart';

/// 同频/广场三类连接卡：同趣/附近的人、结伴行程、线下局。
///
/// 视觉对标微信/小红书卡片密度：圆角 surface、首字母色块头像优雅降级（图片留空
/// 不硬编码外链）、弱底色标签 pill、底部行动阶梯 CTA。所有固定文案来自
/// [PlazaTextConstants]，业务文案来自数据模型。

const double _avatarSize = 48;
const double _smallAvatarSize = 24;

/// 人际连接卡（同趣 / 附近共用）。
class PeerConnectionCard extends StatelessWidget {
  const PeerConnectionCard({
    super.key,
    required this.peer,
    required this.onAction,
  });

  final PeerConnection peer;
  final void Function(ConnectionActionHint action) onAction;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return _CardShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              RoundedSquareAvatar(
                size: _avatarSize,
                imageUrl: peer.privacyBlurred ? null : peer.avatarUrl,
                name: peer.displayName,
                fallbackIcon: peer.privacyBlurred
                    ? CupertinoIcons.person_fill
                    : null,
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Flexible(
                          child: Text(
                            peer.displayName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.iosCallout,
                              fontWeight: AppTypography.semiBold,
                              color: fgPrimary,
                            ),
                          ),
                        ),
                        if ((peer.activeStatusLabel ?? '').trim().isNotEmpty) ...<Widget>[
                          SizedBox(width: AppSpacing.sm),
                          Text(
                            peer.activeStatusLabel!.trim(),
                            style: TextStyle(
                              fontSize: AppTypography.iosCaption2,
                              color: AppColors.iosTertiaryLabel(context),
                            ),
                          ),
                        ],
                      ],
                    ),
                    if (peer.headline.trim().isNotEmpty) ...<Widget>[
                      SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        peer.headline.trim(),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.sm),
          if (peer.sharedSummary.trim().isNotEmpty)
            Text(
              peer.sharedSummary.trim(),
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: fgPrimary,
                height: 1.35,
              ),
            ),
          if (peer.sharedInterests.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: <Widget>[
                for (final interest in peer.sharedInterests)
                  ConnectionChip(label: interest, emphasize: true),
              ],
            ),
          ],
          if (peer.isNearby || peer.mutualConsentRequired) ...<Widget>[
            SizedBox(height: AppSpacing.sm),
            _MetaRow(peer: peer),
          ],
          SizedBox(height: AppSpacing.containerSm),
          ConnectionActionBar(actions: peer.actions, onAction: onAction),
        ],
      ),
    );
  }
}

class _MetaRow extends StatelessWidget {
  const _MetaRow({required this.peer});

  final PeerConnection peer;

  @override
  Widget build(BuildContext context) {
    final color = AppColors.iosTertiaryLabel(context);
    return Row(
      children: <Widget>[
        if (peer.isNearby) ...<Widget>[
          Icon(CupertinoIcons.location, size: AppSpacing.fourteen, color: color),
          SizedBox(width: AppSpacing.intraGroupXs),
          Text(
            peer.distanceLabel!.trim(),
            style: TextStyle(fontSize: AppTypography.iosCaption1, color: color),
          ),
          SizedBox(width: AppSpacing.sm),
          ConnectionChip(label: PlazaTextConstants.fuzzyLocationHint),
        ],
        if (peer.mutualConsentRequired) ...<Widget>[
          if (peer.isNearby) SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Row(
              children: <Widget>[
                Icon(CupertinoIcons.lock, size: AppSpacing.fourteen, color: color),
                SizedBox(width: AppSpacing.intraGroupXs),
                Expanded(
                  child: Text(
                    PlazaTextConstants.mutualConsentHint,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: color,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

/// 结伴 / 行程机会卡。
class CompanionTripCard extends StatelessWidget {
  const CompanionTripCard({
    super.key,
    required this.trip,
    required this.onAction,
  });

  final CompanionTrip trip;
  final void Function(ConnectionActionHint action) onAction;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return _CardShell(
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _CoverPlaceholder(title: trip.destinationName),
          Padding(
            padding: EdgeInsets.all(AppSpacing.containerMd),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(
                        trip.destinationName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosCallout,
                          fontWeight: AppTypography.semiBold,
                          color: fgPrimary,
                        ),
                      ),
                    ),
                    SizedBox(width: AppSpacing.sm),
                    Text(
                      trip.dateRangeLabel,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: AppColors.iosAccent(context),
                        fontWeight: AppTypography.medium,
                      ),
                    ),
                  ],
                ),
                SizedBox(height: AppSpacing.sm),
                if (trip.companionSummary.trim().isNotEmpty)
                  Text(
                    trip.companionSummary.trim(),
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: fgPrimary,
                      height: 1.35,
                    ),
                  ),
                SizedBox(height: AppSpacing.sm),
                Row(
                  children: <Widget>[
                    _AvatarStack(
                      organizerName: trip.organizerName,
                      organizerAvatarUrl: trip.organizerAvatarUrl,
                      companionAvatars: trip.companionAvatars,
                    ),
                    SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        trip.organizerName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: fgSecondary,
                        ),
                      ),
                    ),
                  ],
                ),
                if (trip.tags.isNotEmpty) ...<Widget>[
                  SizedBox(height: AppSpacing.sm),
                  Wrap(
                    spacing: AppSpacing.sm,
                    runSpacing: AppSpacing.sm,
                    children: <Widget>[
                      for (final tag in trip.tags) ConnectionChip(label: tag),
                    ],
                  ),
                ],
                SizedBox(height: AppSpacing.containerSm),
                ConnectionActionBar(actions: trip.actions, onAction: onAction),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 线下局卡。
class OfflineMeetupCard extends StatelessWidget {
  const OfflineMeetupCard({
    super.key,
    required this.meetup,
    required this.onAction,
  });

  final OfflineMeetup meetup;
  final void Function(ConnectionActionHint action) onAction;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return _CardShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            meetup.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCallout,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          _IconLine(
            icon: CupertinoIcons.placemark,
            text: meetup.placeName,
            color: fgSecondary,
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          _IconLine(
            icon: CupertinoIcons.clock,
            text: meetup.timeLabel,
            color: fgSecondary,
          ),
          SizedBox(height: AppSpacing.sm),
          Row(
            children: <Widget>[
              RoundedSquareAvatar(
                size: _smallAvatarSize,
                imageUrl: meetup.hostAvatarUrl,
                name: meetup.hostName,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: Text(
                  meetup.hostName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: fgSecondary,
                  ),
                ),
              ),
              ConnectionChip(
                label: meetup.attendanceLabel,
                icon: CupertinoIcons.person_2,
                emphasize: true,
              ),
            ],
          ),
          if (meetup.tags.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: <Widget>[
                for (final tag in meetup.tags) ConnectionChip(label: tag),
              ],
            ),
          ],
          SizedBox(height: AppSpacing.containerSm),
          ConnectionActionBar(actions: meetup.actions, onAction: onAction),
        ],
      ),
    );
  }
}

class _IconLine extends StatelessWidget {
  const _IconLine({
    required this.icon,
    required this.text,
    required this.color,
  });

  final IconData icon;
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Icon(icon, size: AppSpacing.fourteen, color: color),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: Text(
            text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: AppTypography.iosFootnote, color: color),
          ),
        ),
      ],
    );
  }
}

class _AvatarStack extends StatelessWidget {
  const _AvatarStack({
    required this.organizerName,
    required this.organizerAvatarUrl,
    required this.companionAvatars,
  });

  final String organizerName;
  final String organizerAvatarUrl;
  final List<String> companionAvatars;

  @override
  Widget build(BuildContext context) {
    final extras = companionAvatars.take(3).toList(growable: false);
    final overlap = _smallAvatarSize * 0.62;
    final width =
        _smallAvatarSize + extras.length * overlap;
    final border = AppColors.iosGroupedSurface(context);
    return SizedBox(
      width: width,
      height: _smallAvatarSize,
      child: Stack(
        children: <Widget>[
          for (var i = extras.length - 1; i >= 0; i--)
            Positioned(
              left: (i + 1) * overlap,
              child: _bordered(
                border,
                RoundedSquareAvatar(
                  size: _smallAvatarSize,
                  imageUrl: extras[i].isEmpty ? null : extras[i],
                  name: organizerName,
                  fallbackIcon: CupertinoIcons.person_fill,
                ),
              ),
            ),
          _bordered(
            border,
            RoundedSquareAvatar(
              size: _smallAvatarSize,
              imageUrl: organizerAvatarUrl,
              name: organizerName,
            ),
          ),
        ],
      ),
    );
  }

  Widget _bordered(Color border, Widget child) {
    return Container(
      decoration: BoxDecoration(
        color: border,
        borderRadius: BorderRadius.circular(AppSpacing.intraGroupSm),
      ),
      padding: EdgeInsets.all(AppSpacing.one),
      child: child,
    );
  }
}

class _CoverPlaceholder extends StatelessWidget {
  const _CoverPlaceholder({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return Container(
      height: AppSpacing.forty * 2.4,
      width: double.infinity,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            accent.withValues(alpha: 0.85),
            accent.withValues(alpha: 0.45),
          ],
        ),
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppSpacing.radiusTwentyFour),
        ),
      ),
      alignment: Alignment.bottomLeft,
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: Row(
        children: <Widget>[
          Icon(
            CupertinoIcons.location_solid,
            size: AppSpacing.fourteen,
            color: CupertinoColors.white,
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          Flexible(
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                fontWeight: AppTypography.bold,
                color: CupertinoColors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CardShell extends StatelessWidget {
  const _CardShell({required this.child, this.padding});

  final Widget child;
  final EdgeInsets? padding;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyFour),
      ),
      clipBehavior: Clip.antiAlias,
      padding: padding ?? EdgeInsets.all(AppSpacing.containerMd),
      child: child,
    );
  }
}
