# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
from dataclasses import replace
from unittest import mock

import pytest
from quwoquan_ops.cli.lib.source_allocation import SourceTarget, SourceAllocationError, _redis_connection_descriptor, _redis_credentials, validate_target
from quwoquan_ops.cli.lib.generated.content_account_closure_runtime import ContentAccountClosureRuntimeSourceCreation, ContentAccountClosureRuntimeSource


def test_source_wire_has_only_managed_binding_names():
    fields = ContentAccountClosureRuntimeSourceCreation.model_fields
    assert "producerManagedAllocationBindingId" in fields
    assert "sourceManagedAllocationBindingId" in fields
    assert "producerPhysicalAllocationId" not in fields
    assert "sourcePhysicalAllocationId" not in fields
    assert "managedAllocationBindingId" in ContentAccountClosureRuntimeSource.model_fields
    assert "physicalAllocationId" not in ContentAccountClosureRuntimeSource.model_fields
    for name in ("producerRole", "sourceAclUser", "producerCredentialIdentity", "sourceCredentialIdentity", "rejectedProducerRole", "rejectedSourceAclUser"):
        assert fields[name].is_required()


def test_invalid_target_rejected_before_resource_access():
    approved = SourceTarget("gamma","gamma-local","sha256:"+"a"*64,"sha256:"+"b"*64,"pg","db","redis","source","role","acl","group")
    for current in (replace(approved,environment="prod",target="prod-hosted"), replace(approved,target="beta-local"),replace(approved,candidate_digest="sha256:"+"c"*64)):
        with pytest.raises(SourceAllocationError):
            validate_target(approved,current,{})


def test_redis_credentials_copy_public_connection_semantics_only():
    class SSLConnection:
        pass

    pool = mock.Mock(
        connection_class=SSLConnection,
        connection_kwargs={
            "host": "redis.internal",
            "port": 6380,
            "db": 7,
            "socket_timeout": 2.5,
            "protocol": 3,
            "ssl_ca_certs": "/run/certs/ca.pem",
            "username": "admin",
            "password": "admin-secret",
            "retry": object(),
            "himport_registry": object(),
        },
    )
    admin = mock.Mock(connection_pool=pool)

    class Redis:
        def __init__(
            self,
            host="localhost",
            port=6379,
            db=0,
            username=None,
            password=None,
            decode_responses=False,
            socket_timeout=None,
            protocol=2,
            ssl=False,
            ssl_ca_certs=None,
        ):
            self.arguments = locals()

    redis_module = mock.Mock(
        Redis=Redis,
        SSLConnection=SSLConnection,
        UnixDomainSocketConnection=type("UnixDomainSocketConnection", (), {}),
    )
    with mock.patch.dict("sys.modules", redis=redis_module):
        descriptor = _redis_connection_descriptor(admin)
        client = _redis_credentials(admin, "source-user", "source-secret")

    assert descriptor == {
        "host": "redis.internal",
        "port": 6380,
        "db": 7,
        "socket_timeout": 2.5,
        "protocol": 3,
        "ssl": True,
        "ssl_ca_certs": "/run/certs/ca.pem",
    }
    assert client.arguments == {
        "self": client,
        "host": "redis.internal",
        "port": 6380,
        "db": 7,
        "username": "source-user",
        "password": "source-secret",
        "decode_responses": True,
        "socket_timeout": 2.5,
        "protocol": 3,
        "ssl": True,
        "ssl_ca_certs": "/run/certs/ca.pem",
    }
    assert "himport_registry" not in client.arguments
    assert "admin-secret" not in client.arguments.values()
