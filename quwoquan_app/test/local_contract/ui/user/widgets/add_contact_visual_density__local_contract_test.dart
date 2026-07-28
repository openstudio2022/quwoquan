import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pretty_qr_code/pretty_qr_code.dart';

import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/core/constants/search_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/ui/user/widgets/add_contact_entry_card.dart';
import 'package:quwoquan_app/ui/user/widgets/my_qr_card.dart';

const _qrCard = ProfileQrCardData(
  publicProfileUrl: 'https://mock.quwoquan.local/u/current',
  qrPayload: 'https://mock.quwoquan.local/u/current?qr=mock_current',
  qrTokenId: 'qr_current',
  styleVersion: 'v1',
  avatarUrl: '',
  displayName: 'fixture_user_current',
  region: '杭州',
  shareText: 'https://mock.quwoquan.local/u/current?qr=mock_current',
);

Widget _wrap(Widget child) {
  return CupertinoApp(
    home: Center(
      child: SizedBox(width: AppSpacing.webPcLoginSurfaceWidth, child: child),
    ),
  );
}

void main() {
  testWidgets('添加联系人搜索框提示语使用浅色占位样式', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const AppSearchField(
          placeholder: ContactText.addContactSearchHubPlaceholder,
        ),
      ),
    );

    final field = tester.widget<CupertinoSearchTextField>(
      find.byType(CupertinoSearchTextField),
    );
    final context = tester.element(find.byType(CupertinoSearchTextField));
    expect(
      field.placeholderStyle?.color,
      SearchSemanticConstants.placeholderTextStyle(context).color,
    );
  });

  testWidgets('添加联系人入口列表标题使用正常字重', (tester) async {
    await tester.pumpWidget(
      _wrap(
        AddContactEntryCard(
          icon: CupertinoIcons.qrcode_viewfinder,
          title: ProfileText.editProfileQrScanAction,
          subtitle: ContactText.addContactScanEntrySubtitle,
          onTap: () {},
        ),
      ),
    );

    final title = tester.widget<Text>(
      find.text(ProfileText.editProfileQrScanAction),
    );
    expect(title.style?.fontWeight, AppTypography.regular);
  });

  testWidgets('添加联系人页内嵌二维码名片使用紧凑密度', (tester) async {
    await tester.pumpWidget(
      _wrap(const MyQrCardContent(card: _qrCard, compact: true)),
    );

    final heading = tester.widget<Text>(
      find.text(ProfileText.editProfileQrCardHeading),
    );
    final displayName = tester.widget<Text>(find.text(_qrCard.displayName));
    final qrSize = tester.getSize(find.byType(PrettyQrView));

    expect(heading.style?.fontSize, AppTypography.iosBody);
    expect(heading.style?.fontWeight, AppTypography.regular);
    expect(displayName.style?.fontSize, AppTypography.iosBody);
    expect(displayName.style?.fontWeight, AppTypography.regular);
    expect(find.text(ProfileText.editProfileQrCardHint), findsNothing);
    expect(qrSize.width, lessThanOrEqualTo(AppSpacing.twoHundredTwenty));
    expect(qrSize.height, lessThanOrEqualTo(AppSpacing.twoHundredTwenty));
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is SizedBox &&
            widget.width == AppSpacing.avatarUserLg &&
            widget.height == AppSpacing.avatarUserLg,
      ),
      findsOneWidget,
    );
  });
}
