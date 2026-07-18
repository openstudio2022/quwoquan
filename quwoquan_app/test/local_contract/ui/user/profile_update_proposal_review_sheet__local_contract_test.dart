import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_update_proposal_review_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets(
    'pending proposal confirms target version server-side then applies',
    (tester) async {
      final writer = _RecordingWriter();
      await _pumpReview(tester, writer: writer, proposal: _proposal());

      await tester.tap(find.byKey(const ValueKey('profile-proposal-approve')));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 4));

      expect(writer.calls, <String>['confirm:proposal-1', 'apply:proposal-1']);
      expect(
        find.byKey(const ValueKey('profile-proposal-review-sheet')),
        findsNothing,
      );
    },
  );

  testWidgets(
    'reject is a single aggregate command with no apply side effect',
    (tester) async {
      final writer = _RecordingWriter();
      await _pumpReview(tester, writer: writer, proposal: _proposal());

      await tester.tap(find.byKey(const ValueKey('profile-proposal-reject')));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 4));

      expect(writer.calls, <String>['reject:proposal-1']);
    },
  );

  testWidgets('command failure remains visible and retryable', (tester) async {
    final writer = _RecordingWriter(error: StateError('write failed'));
    await _pumpReview(tester, writer: writer, proposal: _proposal());

    await tester.tap(find.byKey(const ValueKey('profile-proposal-approve')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('profile-proposal-error')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('profile-proposal-review-sheet')),
      findsOneWidget,
    );
  });

  testWidgets('applying proposal can resume but cannot be rejected', (
    tester,
  ) async {
    final writer = _RecordingWriter();
    await _pumpReview(
      tester,
      writer: writer,
      proposal: _proposal(status: ProfileUpdateProposalStatus.applying),
    );

    expect(
      find.byKey(const ValueKey('profile-proposal-approve')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('profile-proposal-reject')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('profile-proposal-approve')));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));

    expect(writer.calls, <String>['apply:proposal-1']);
  });
}

Future<void> _pumpReview(
  WidgetTester tester, {
  required _RecordingWriter writer,
  required ProfileUpdateProposalView proposal,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        profileEditProposalCommandWriterProvider.overrideWithValue(writer),
      ],
      child: CupertinoApp(
        initialRoute: '/review',
        routes: <String, WidgetBuilder>{
          '/': (_) => const SizedBox.shrink(),
          '/review': (_) =>
              ProfileUpdateProposalReviewSheet(proposal: proposal),
        },
      ),
    ),
  );
  await tester.pumpAndSettle();
}

ProfileUpdateProposalView _proposal({
  ProfileUpdateProposalStatus status = ProfileUpdateProposalStatus.pending,
}) => ProfileUpdateProposalView(
  id: 'proposal-1',
  personaId: 'persona-1',
  source: ProfileUpdateProposalSource.assistant,
  status: status,
  changes: ProfileChangeSet(displayName: 'new name', bio: ''),
  reviewedBy: null,
  version: 1,
  createdAt: DateTime.utc(2026, 7, 16),
  updatedAt: DateTime.utc(2026, 7, 16),
  resolvedAt: null,
);

final class _RecordingWriter implements ProfileUpdateProposalCommandWriter {
  _RecordingWriter({this.error});

  final Object? error;
  final List<String> calls = <String>[];

  void _throwIfNeeded() {
    final current = error;
    if (current != null) throw current;
  }

  @override
  Future<ProfileUpdateProposalCommandResult> confirm(
    ConfirmProfileUpdateProposalCommand command,
  ) async {
    calls.add('confirm:${command.proposalId}');
    _throwIfNeeded();
    return const ProfileUpdateProposalCommandResult(
      proposalId: 'proposal-1',
      version: 2,
      status: ProfileUpdateProposalStatus.confirmed,
      replayed: false,
    );
  }

  @override
  Future<ProfileUpdateProposalCommandResult> apply(
    ApplyProfileUpdateProposalCommand command,
  ) async {
    calls.add('apply:${command.proposalId}');
    _throwIfNeeded();
    return const ProfileUpdateProposalCommandResult(
      proposalId: 'proposal-1',
      version: 3,
      status: ProfileUpdateProposalStatus.applied,
      replayed: false,
    );
  }

  @override
  Future<ProfileUpdateProposalCommandResult> reject(
    RejectProfileUpdateProposalCommand command,
  ) async {
    calls.add('reject:${command.proposalId}');
    _throwIfNeeded();
    return const ProfileUpdateProposalCommandResult(
      proposalId: 'proposal-1',
      version: 2,
      status: ProfileUpdateProposalStatus.rejected,
      replayed: false,
    );
  }

  @override
  Future<ProfileUpdateProposalCommandResult> create(
    CreateProfileUpdateProposalCommand command,
  ) => throw UnsupportedError('review sheet cannot create proposals');
}
