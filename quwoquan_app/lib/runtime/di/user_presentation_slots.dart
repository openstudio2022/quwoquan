import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/contact_candidate_vm.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/contact_candidate_row.dart';

/// Persona Relationship owns the shared candidate renderer. Contact Discovery
/// receives it from DI rather than importing private presentation code.
typedef ContactCandidateRowBuilder =
    Widget Function({
      Key? key,
      required ContactCandidateVm candidate,
      required VoidCallback onAdd,
      VoidCallback? onTap,
      bool pending,
    });

final contactCandidateRowBuilderProvider = Provider<ContactCandidateRowBuilder>(
  (ref) {
    return ({key, required candidate, required onAdd, onTap, pending = false}) {
      return ContactCandidateRow(
        key: key,
        candidate: candidate,
        onAdd: onAdd,
        onTap: onTap,
        pending: pending,
      );
    };
  },
);
