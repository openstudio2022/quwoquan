import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show profileHomeSocialProofReaderProvider;

/// 我的主页影响力面「成行力」单行事实计数（REQ-008 / OPEN-007 收口）。
///
/// 消费四锚点社会证明读面的 creator 锚点（成形/经历两级诚实计数，云侧聚合
/// 派生、端不估算）。成形为 0 或读取失败整行不渲染（L0 氛围层：静默降级，
/// 不阻塞主页、不伪造社会证明）。
class CreatorFlywheelProofRow extends ConsumerWidget {
  const CreatorFlywheelProofRow({super.key, required this.personaId});

  static const Key rowKey = ValueKey<String>('creator-flywheel-proof-row');

  final String personaId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = personaId.trim();
    if (id.isEmpty) {
      return const SizedBox.shrink();
    }
    final proof = ref.watch(_creatorSocialProofProvider(id));
    return proof.when(
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
      data: (summary) {
        if (summary.formed <= 0) {
          return const SizedBox.shrink();
        }
        final text = StringBuffer(
          DiscoveryFeedText.creatorFlywheelFormedLabel(summary.formed),
        );
        if (summary.experienced > 0) {
          text.write(
            DiscoveryFeedText.creatorFlywheelExperiencedSuffix(
              summary.experienced,
            ),
          );
        }
        return Padding(
          key: CreatorFlywheelProofRow.rowKey,
          padding: EdgeInsets.only(
            top: AppSpacing.intraGroupSm,
            left: AppSpacing.containerSm,
            right: AppSpacing.containerSm,
          ),
          child: Row(
            children: <Widget>[
              Icon(
                CupertinoIcons.arrow_2_circlepath,
                size: AppSpacing.iconSmall,
                color: AppColors.iosSecondaryLabel(context),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: Text(
                  text.toString(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

typedef _CreatorSocialProof = ({int formed, int experienced});

/// creator 锚点社会证明（autoDispose；失败由消费方静默收起）。
final _creatorSocialProofProvider = FutureProvider.autoDispose
    .family<_CreatorSocialProof, String>((ref, personaId) async {
      final summary = await ref
          .watch(profileHomeSocialProofReaderProvider)
          .getGatheringSocialProof(anchorKind: 'creator', objectId: personaId);
      return (
        formed: summary.formedCount,
        experienced: summary.experiencedCount,
      );
    });
