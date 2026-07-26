part of 'homepage_introduction_page.dart';

class _RelatedObjectsSection extends StatelessWidget {
  const _RelatedObjectsSection({required this.items, required this.onTap});

  final List<HomepageRelatedGroupSummary> items;
  final ValueChanged<HomepageRelatedGroupSummary> onTap;

  @override
  Widget build(BuildContext context) {
    return _IntroductionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            UITextConstants.objectIntroRelatedObjectsTitle,
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          SizedBox(
            height: _introRelatedObjectHeight,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: items.length,
              separatorBuilder: (_, _) =>
                  SizedBox(width: AppSpacing.containerXs),
              itemBuilder: (context, index) {
                final item = items[index];
                final homepageId = (item.linkedHomepageId ?? '').trim();
                final circleId = item.circleId.trim();
                final canOpen = homepageId.isNotEmpty || circleId.isNotEmpty;
                return CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: canOpen ? () => onTap(item) : null,
                  child: Container(
                    width: _introHorizontalCardWidth,
                    padding: EdgeInsets.all(AppSpacing.containerSm),
                    decoration: BoxDecoration(
                      color: AppColors.iosGroupedSurfaceElevated(context),
                      borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: <Widget>[
                        Text(
                          item.linkedHomepageTitle ?? item.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosBody,
                            fontWeight: AppTypography.semiBold,
                            color: AppColors.iosLabel(context),
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupXs),
                        Text(
                          item.memberCount > 0
                              ? UITextConstants.objectIntroDiscussionCount(
                                  item.memberCount,
                                )
                              : homepageId.isNotEmpty
                              ? UITextConstants.objectIntroViewHomepage
                              : UITextConstants.objectIntroViewCircle,
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: AppColors.iosSecondaryLabel(context),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _ReturnLinksCard extends StatelessWidget {
  const _ReturnLinksCard({required this.title, required this.onTap});

  final String title;
  final ValueChanged<HomepageDetailTabTarget> onTap;

  @override
  Widget build(BuildContext context) {
    return _IntroductionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            UITextConstants.objectIntroContinueTitle(title),
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          Wrap(
            spacing: AppSpacing.intraGroupSm,
            runSpacing: AppSpacing.intraGroupSm,
            children: <Widget>[
              _ReturnChip(
                label: UITextConstants.objectIntroReturnRecord,
                onTap: () => onTap(HomepageDetailTabTarget.record),
              ),
              _ReturnChip(
                label: UITextConstants.objectIntroReturnDiscussion,
                onTap: () => onTap(HomepageDetailTabTarget.discussion),
              ),
              _ReturnChip(
                label: UITextConstants.objectIntroReturnCircles,
                onTap: () => onTap(HomepageDetailTabTarget.relatedCircles),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ReturnChip extends StatelessWidget {
  const _ReturnChip({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      color: AppColors.primaryColor.withValues(alpha: 0.12),
      borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      onPressed: onTap,
      child: Text(
        label,
        style: const TextStyle(
          color: AppColors.primaryColor,
          fontSize: AppTypography.iosFootnote,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }
}

class _HomepageSourceCard extends StatelessWidget {
  const _HomepageSourceCard({required this.source});

  final HomepageSource source;

  Uri? get _safeUri {
    final uri = Uri.tryParse(source.sourceUrl.trim());
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        !_isPublicSourceHost(uri.host) ||
        uri.queryParameters.keys.any(_isSensitiveSourceQueryKey)) {
      return null;
    }
    return uri;
  }

  @override
  Widget build(BuildContext context) {
    final uri = _safeUri;
    final host = uri?.host ?? '';
    return _IntroductionCard(
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: uri == null
            ? null
            : () {
                unawaited(launchUrl(uri, mode: LaunchMode.externalApplication));
              },
        child: Row(
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    UITextConstants.objectIntroSourceTitle,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    source.title.trim().isEmpty
                        ? UITextConstants.objectIntroSourcePlatform(
                            source.sourceKind,
                          )
                        : source.title.trim(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  if (host.isNotEmpty)
                    Text(
                      '${UITextConstants.objectIntroSourcePlatform(source.sourceKind)} · $host',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: AppColors.iosTertiaryLabel(context),
                      ),
                    ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              CupertinoIcons.arrow_up_right_square,
              size: AppSpacing.iconMedium,
              color: AppColors.iosSecondaryLabel(context),
              semanticLabel: UITextConstants.objectIntroSourceOpen,
            ),
          ],
        ),
      ),
    );
  }
}

bool _isPublicSourceHost(String rawHost) {
  final host = rawHost.toLowerCase();
  if (host == 'localhost' ||
      host == '::1' ||
      host.endsWith('.local') ||
      host.startsWith('127.') ||
      host.startsWith('10.') ||
      host.startsWith('192.168.')) {
    return false;
  }
  final parts = host.split('.');
  if (parts.length == 4 && parts.first == '172') {
    final second = int.tryParse(parts[1]);
    if (second != null && second >= 16 && second <= 31) {
      return false;
    }
  }
  return true;
}

bool _isSensitiveSourceQueryKey(String rawKey) {
  final key = rawKey.toLowerCase();
  return key.contains('token') ||
      key.contains('signature') ||
      key.contains('credential') ||
      key.contains('auth');
}

class _IntroductionEmptyState extends StatelessWidget {
  const _IntroductionEmptyState({required this.onBack});

  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.doc_text_search,
              size: AppSpacing.iconLarge,
              color: AppColors.iosSecondaryLabel(context),
            ),
            SizedBox(height: AppSpacing.containerSm),
            Text(
              UITextConstants.objectIntroEmptyTitle,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              UITextConstants.objectIntroEmptyMessage,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.containerMd),
            CupertinoButton.filled(
              onPressed: onBack,
              child: const Text(UITextConstants.objectIntroBackToHomepage),
            ),
          ],
        ),
      ),
    );
  }
}

class _IntroductionCard extends StatelessWidget {
  const _IntroductionCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
          width: AppSpacing.hairline,
        ),
      ),
      child: child,
    );
  }
}
