"""Package #179: reject broken or ambiguous OpenAPI security declarations.

A generated client must not silently treat a protected endpoint as anonymous
because its security scheme was renamed or an empty alternative was introduced.
This test validates declarations without changing runtime authentication.
"""
from orin_api.main import app


HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}


def test_openapi_security_requirements_reference_declared_schemes():
    schema = app.openapi()
    schemes = schema.get("components", {}).get("securitySchemes", {})
    global_security = schema.get("security", [])

    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            requirements = operation.get("security", global_security)
            assert isinstance(requirements, list), (
                f"Invalid security requirements: {method.upper()} {path}"
            )
            for alternative in requirements:
                assert isinstance(alternative, dict), (
                    f"Invalid security alternative: {method.upper()} {path}"
                )
                for scheme_name, scopes in alternative.items():
                    assert scheme_name in schemes, (
                        f"Undeclared security scheme {scheme_name}: {method.upper()} {path}"
                    )
                    assert isinstance(scopes, list), (
                        f"Invalid scopes for {scheme_name}: {method.upper()} {path}"
                    )
                    if schemes[scheme_name].get("type") != "oauth2":
                        assert not scopes, (
                            f"Non-OAuth scheme cannot require scopes: {method.upper()} {path}"
                        )


def test_release_critical_private_operations_have_no_anonymous_alternative():
    schema = app.openapi()
    protected = (
        ("get", "/api/v1/tasks"),
        ("post", "/api/v1/tasks"),
        ("patch", "/api/v1/tasks/{task_id}"),
        ("get", "/api/v1/notifications/preferences"),
        ("put", "/api/v1/auth/reminder-lease"),
        ("delete", "/api/v1/auth/reminder-lease"),
    )
    for method, path in protected:
        operation = schema["paths"][path][method]
        requirements = operation.get("security", schema.get("security", []))
        assert requirements and all(isinstance(alt, dict) and alt for alt in requirements), (
            f"Anonymous security alternative: {method.upper()} {path}"
        )
