/// assistantSettings 页面 user_acceptance（B8 阶段 4a：真实页面 pump 验收）。
///
/// surface: assistantSettings · owner: assistant · route: chatDetail
/// 本文件替代旧「证据文件路径存在性断言」伪验收。承载关系说明：
/// assistantSettings surface（私助会话设置：consent 授权 / 显式偏好管理 / 技能）
/// 的真实页面本体是 `AssistantManagementPage`；consent 开关经
/// `personalContentAccessProvider` 接 `AssistantSkillConsentFacet`。
/// 四类必测 case：
/// - load_success：真实 pump 后核心结构出现（标题 + consent 开关行 + 状态摘要）；
/// - empty_permission_error：consent Facet 抛 CloudException → notifier
///   fail-closed（granted=false）且错误走结构化 errorMessage 通道，UI 不崩溃；
/// - primary_cta：拨动 consent 开关触发 GrantSkillConsent（Recording 替身
///   断言命令）且 UI 状态推进为「已允许」；
/// - trace_context：页面曝光进入 VisitRecorder（VisitTarget.page）。
library;

import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/cloud/assistant/generated/assistant_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_management_page.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../support/runtime_failure_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  _mockPathProvider();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_assistant_settings_uat_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('load_success：真实 pump 私助管理页出现核心结构', (tester) async {
    final facet = _RecordingConsentFacet();
    final container = await _pumpManagementPage(
      tester,
      facet: facet,
      preferenceFacet: _RecordingPreferenceFacet(
        initial: const <AssistantPreferenceFact>[
          AssistantPreferenceFact(
            preferenceId: 'preference_uat_1',
            userId: 'persona_assistant_uat',
            scope: 'long_term',
            kind: 'tone',
            value: 'warm',
            sourceType: 'management',
            status: 'active',
            createdAt: '2026-07-20T08:00:00Z',
            updatedAt: '2026-07-20T08:00:00Z',
            version: 1,
          ),
        ],
      ),
    );

    expect(find.byType(AssistantManagementPage), findsOneWidget);
    expect(
      find.text(AppConceptConstants.assistantManagementTitle),
      findsOneWidget,
    );
    // consent 开关行：真实标签 + 唯一真实开关（3b 已删除无后端假开关）。
    expect(
      find.text(AssistantText.assistantContentAccessPermission),
      findsOneWidget,
    );
    expect(find.byType(CupertinoSwitch), findsOneWidget);

    // hydrate 完成：无授权时 fail-closed 显示「未允许」摘要。
    final state = container.read(personalContentAccessProvider);
    expect(state.isHydrating, isFalse);
    expect(state.granted, isFalse);
    expect(find.text(state.summaryLabel), findsOneWidget);
    // 显式偏好真实进入管理页，不暴露内部 preferenceId/userId。
    expect(
      find.text(AssistantText.assistantMemorySectionTitle),
      findsOneWidget,
    );
    expect(find.text(AssistantText.assistantPreferenceWarm), findsOneWidget);
    expect(find.text('preference_uat_1'), findsNothing);
    expect(find.text('persona_assistant_uat'), findsNothing);

    await _disposeTree(tester);
  });

  testWidgets(
    'empty_permission_error：consent Facet 抛 CloudException 时 fail-closed 且错误结构化',
    (tester) async {
      final facet = _RecordingConsentFacet(
        listError: CloudException(
          type: CloudErrorType.forbidden,
          message: 'skill consent required',
          statusCode: AssistantErrorCode.skillConsentRequired.httpStatus,
          code: AssistantErrorCode.skillConsentRequired.code,
          userMessage: AssistantErrorCode.skillConsentRequired.defaultMessage,
          runtimeFailure: testRuntimeFailure(
            code: AssistantErrorCode.skillConsentRequired.code,
            kind: RuntimeFailureKind.permission,
          ),
        ),
      );
      final container = await _pumpManagementPage(tester, facet: facet);

      final state = container.read(personalContentAccessProvider);
      // 结构化错误进入 errorMessage 通道（服务端 userMessage 优先），
      // 授权 fail-closed：不伪造「已允许」。
      expect(
        state.errorMessage,
        AssistantErrorCode.skillConsentRequired.defaultMessage,
      );
      expect(state.granted, isFalse);
      expect(state.source, 'remote_unavailable');
      expect(state.isHydrating, isFalse);
      // 页面不崩溃：标题、开关行与「未允许」摘要仍在。
      expect(find.byType(AssistantManagementPage), findsOneWidget);
      expect(find.byType(CupertinoSwitch), findsOneWidget);
      expect(find.text(state.summaryLabel), findsOneWidget);
      expect(
        find.text(AssistantText.assistantConsentLoadFailedTitle),
        findsOneWidget,
      );

      await _disposeTree(tester);
    },
  );

  testWidgets('primary_cta：拨动 consent 开关触发 GrantSkillConsent 且状态推进', (
    tester,
  ) async {
    final facet = _RecordingConsentFacet();
    final container = await _pumpManagementPage(tester, facet: facet);

    await tester.tap(find.byType(CupertinoSwitch));
    await tester.pumpAndSettle();

    // Recording 替身断言主 CTA 副作用：授权命令携带 consent skillId。
    expect(facet.grantedSkillIds, <String>[kPersonalContentAccessSkillId]);
    final state = container.read(personalContentAccessProvider);
    expect(state.granted, isTrue);
    expect(state.isSyncing, isFalse);
    expect(find.text(state.summaryLabel), findsOneWidget);

    // 再拨一次回关：撤回命令同样真实下发（闭环验证，不留半程状态）。
    await tester.tap(find.byType(CupertinoSwitch));
    await tester.pumpAndSettle();
    expect(facet.revokedSkillIds, <String>[kPersonalContentAccessSkillId]);
    expect(container.read(personalContentAccessProvider).granted, isFalse);

    await _disposeTree(tester);
  });

  testWidgets('preference_control：遗忘显式偏好后可在窗口内撤销恢复', (tester) async {
    final preferenceFacet = _RecordingPreferenceFacet(
      initial: const <AssistantPreferenceFact>[
        AssistantPreferenceFact(
          preferenceId: 'preference_uat_undo',
          userId: 'persona_assistant_uat',
          scope: 'long_term',
          kind: 'reply_length',
          value: 'concise',
          sourceType: 'management',
          status: 'active',
          createdAt: '2026-07-20T08:00:00Z',
          updatedAt: '2026-07-20T08:00:00Z',
          version: 1,
        ),
      ],
    );
    await _pumpManagementPage(
      tester,
      facet: _RecordingConsentFacet(),
      preferenceFacet: preferenceFacet,
    );

    await tester.tap(find.text(AssistantText.assistantPreferenceForget));
    await tester.pumpAndSettle();
    expect(find.text(AssistantText.assistantPreferenceForgot), findsOneWidget);
    expect(preferenceFacet.revokedPreferenceIds, <String>[
      'preference_uat_undo',
    ]);

    await tester.tap(find.text(AssistantText.assistantPreferenceUndo));
    await tester.pumpAndSettle();
    expect(preferenceFacet.restoredPreferenceIds, <String>[
      'preference_uat_undo',
    ]);
    expect(
      find.text(AssistantText.assistantPreferenceConcise),
      findsNWidgets(2),
    );

    await _disposeTree(tester);
  });

  testWidgets('trace_context：页面曝光进入 VisitRecorder', (tester) async {
    final recorder = _CapturingVisitRecorder();
    await _pumpManagementPage(
      tester,
      facet: _RecordingConsentFacet(),
      visitRecorder: recorder,
    );

    // 曝光埋点（R20）：进入管理页记录 assistant_management 页面访问。
    expect(
      recorder.recorded.map((target) => target.targetKey),
      contains(const VisitTarget.page(PageNames.assistantManagement).targetKey),
    );

    await _disposeTree(tester);
  });
}

/// 统一 pump 真实私助管理页：窄 consent Facet 替身 + authenticated 会话。
Future<ProviderContainer> _pumpManagementPage(
  WidgetTester tester, {
  required _RecordingConsentFacet facet,
  _CapturingVisitRecorder? visitRecorder,
  _RecordingPreferenceFacet? preferenceFacet,
}) async {
  final resolvedPreferenceFacet =
      preferenceFacet ?? _RecordingPreferenceFacet();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        assistantSkillConsentFacetProvider.overrideWithValue(facet),
        assistantPreferenceFactFacetProvider.overrideWithValue(
          resolvedPreferenceFacet,
        ),
        visitRecorderServiceProvider.overrideWithValue(
          visitRecorder ?? _CapturingVisitRecorder(),
        ),
        authSessionControllerProvider.overrideWith(
          _AuthenticatedSessionController.new,
        ),
      ],
      child: MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: _AuthWarmup(child: AssistantManagementPage(onBack: () {})),
      ),
    ),
  );
  // initState postFrameCallback（曝光）+ consent hydrate microtask。
  await tester.pumpAndSettle();
  return ProviderScope.containerOf(
    tester.element(find.byType(AssistantManagementPage)),
  );
}

Future<void> _disposeTree(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(milliseconds: 50));
}

void _mockPathProvider() {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  final directory = Directory.systemTemp.createTempSync(
    'qwq_assistant_settings_uat_fs_',
  );
  tearDownAll(() {
    if (directory.existsSync()) {
      directory.deleteSync(recursive: true);
    }
  });
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
        switch (call.method) {
          case 'getApplicationDocumentsDirectory':
          case 'getApplicationSupportDirectory':
          case 'getTemporaryDirectory':
            return directory.path;
          default:
            return null;
        }
      });
}

class _AuthWarmup extends ConsumerWidget {
  const _AuthWarmup({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(authSessionControllerProvider);
    return child;
  }
}

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_assistant_uat',
    activeSubAccountId: 'persona_assistant_uat',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
}

/// Recording consent Facet：内存授权状态 + 命令调用记录；可配置列表抛错。
class _RecordingConsentFacet implements AssistantSkillConsentFacet {
  _RecordingConsentFacet({this.listError});

  final Object? listError;
  final List<String> grantedSkillIds = <String>[];
  final List<String> revokedSkillIds = <String>[];
  final Map<String, AssistantSkillConsent> _consents =
      <String, AssistantSkillConsent>{};

  @override
  Future<List<AssistantSkillConsent>> listConsents() async {
    final error = listError;
    if (error != null) {
      throw error;
    }
    return _consents.values.toList(growable: false);
  }

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  }) async {
    grantedSkillIds.add(skillId);
    final consent = AssistantSkillConsent(
      skillId: skillId,
      grantedScope: grantedScope,
      granted: true,
      updatedAt: DateTime.utc(2026, 7, 19),
    );
    _consents[skillId] = consent;
    return consent;
  }

  @override
  Future<void> revokeSkillConsent({required String skillId}) async {
    revokedSkillIds.add(skillId);
    _consents.remove(skillId);
  }
}

class _RecordingPreferenceFacet implements AssistantPreferenceFactFacet {
  _RecordingPreferenceFacet({
    List<AssistantPreferenceFact> initial = const <AssistantPreferenceFact>[],
  }) : _preferences = <AssistantPreferenceFact>[...initial];

  final List<AssistantPreferenceFact> _preferences;
  final List<String> revokedPreferenceIds = <String>[];
  final List<String> restoredPreferenceIds = <String>[];

  @override
  Future<List<AssistantPreferenceFact>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String conversationId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  }) async {
    return _preferences
        .where(
          (preference) =>
              preference.status == status.wireName &&
              (scope == null || preference.scope == scope.wireName),
        )
        .toList(growable: false);
  }

  @override
  Future<AssistantPreferenceFact> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String conversationId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    final preference = AssistantPreferenceFact(
      preferenceId: 'preference_uat_${_preferences.length + 1}',
      userId: 'persona_assistant_uat',
      scope: scope.wireName,
      conversationId: conversationId.isEmpty ? null : conversationId,
      kind: kind.wireName,
      value: value,
      sourceType: sourceType.wireName,
      status: AssistantPreferenceStatus.active.wireName,
      createdAt: now,
      updatedAt: now,
      version: 1,
    );
    _preferences.add(preference);
    return preference;
  }

  @override
  Future<AssistantPreferenceFact> revokeAssistantPreference({
    required String preferenceId,
  }) async {
    revokedPreferenceIds.add(preferenceId);
    final index = _preferences.indexWhere(
      (preference) => preference.preferenceId == preferenceId,
    );
    final now = DateTime.now().toUtc();
    final revoked = _copyPreference(
      _preferences[index],
      status: AssistantPreferenceStatus.revoked,
      updatedAt: now.toIso8601String(),
      revokedAt: now.toIso8601String(),
      revocationDeadline: now
          .add(const Duration(minutes: 10))
          .toIso8601String(),
    );
    _preferences[index] = revoked;
    return revoked;
  }

  @override
  Future<AssistantPreferenceFact> restoreAssistantPreference({
    required String preferenceId,
  }) async {
    restoredPreferenceIds.add(preferenceId);
    final index = _preferences.indexWhere(
      (preference) => preference.preferenceId == preferenceId,
    );
    final restored = _copyPreference(
      _preferences[index],
      status: AssistantPreferenceStatus.active,
      updatedAt: DateTime.now().toUtc().toIso8601String(),
    );
    _preferences[index] = restored;
    return restored;
  }

  AssistantPreferenceFact _copyPreference(
    AssistantPreferenceFact source, {
    required AssistantPreferenceStatus status,
    required String updatedAt,
    String? revokedAt,
    String? revocationDeadline,
  }) {
    return AssistantPreferenceFact(
      preferenceId: source.preferenceId,
      userId: source.userId,
      scope: source.scope,
      conversationId: source.conversationId,
      kind: source.kind,
      value: source.value,
      sourceType: source.sourceType,
      status: status.wireName,
      revokedAt: revokedAt,
      revocationDeadline: revocationDeadline,
      createdAt: source.createdAt,
      updatedAt: updatedAt,
      version: source.version + 1,
    );
  }
}

/// 捕获页面曝光的 VisitRecorder 替身（不触达 Hive/Remote）。
class _CapturingVisitRecorder extends VisitRecorderService {
  final List<VisitTarget> recorded = <VisitTarget>[];

  @override
  Future<void> recordVisit(VisitTarget target) async {
    recorded.add(target);
  }
}
