import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';

/// 跨对象只读公开资料所需的最小 Persona seam。
///
/// 调用方只能按 persona id 读取公开投影，不获得 Persona 管理、生命周期或
/// 活动身份上下文等对象私有能力。
abstract interface class PersonaProfileQuery {
  Future<PersonaProfileViewData> getPersonaProfile(String personaId);
}
