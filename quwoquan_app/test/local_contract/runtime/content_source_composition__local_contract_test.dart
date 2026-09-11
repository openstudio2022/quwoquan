// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/alpha_content_composition.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/executor/unavailable_cloud_operation_executor.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_bundled.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() {
    ContentProductionComposition.useRemoteReadComposition();
    UserProductionComposition.useRemoteReadComposition();
  });

  test('Alpha 入口显式安装资料读取能力，在线装配不复用隔离实现', () {
    final client = GeneratedCloudOperationClient(
      const UnavailableCloudOperationExecutor(),
    );
    CloudOperationInvocationContext context(String _, String _) =>
        throw StateError('构造读取能力不得发送请求');
    installAlphaContentComposition();
    final profile = UserProductionComposition.generatedAdapter<ProfileQuery>(
      UserProductionAdapter.profileQuery,
      client: client,
      invocationContext: context,
    );
    final persona = UserProductionComposition.generatedAdapter<PersonaQuery>(
      UserProductionAdapter.personaQuery,
      client: client,
      invocationContext: context,
    );
    expect(profile, isA<BundledProfileQuery>());
    expect(persona, same(profile));

    UserProductionComposition.useRemoteReadComposition();
    final remote = UserProductionComposition.generatedAdapter<ProfileQuery>(
      UserProductionAdapter.profileQuery,
      client: client,
      invocationContext: context,
    );
    expect(remote, isNot(isA<BundledProfileQuery>()));
  });

  test('Alpha 配置读取不构造在线 repository 或缓存', () async {
    installAlphaContentComposition();
    final reader = ContentProductionComposition.appContentConfigReader(
      repository: () => throw StateError('Alpha 不得构造在线配置读取器'),
      store: () => throw StateError('Alpha 不得读取在线缓存'),
    );
    expect(await reader.readActiveSnapshot(), isNull);
  });
}
