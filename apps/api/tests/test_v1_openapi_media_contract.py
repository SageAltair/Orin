"""Package #179: guard OpenAPI response and request-body structure.

These structural checks complement the reference graph and route sentinels.
They reject malformed HTTP response status keys and empty request/response
content declarations before client SDKs consume the published schema.
"""
import re

from orin_api.main import app


HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}


def test_openapi_response_status_keys_are_valid():
    schema = app.openapi()
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            for status, response in operation["responses"].items():
                assert status == "default" or re.fullmatch(r"[1-5][0-9]{2}|[1-5]XX", str(status)), (
                    f"Invalid response status {status!r}: {method.upper()} {path}"
                )
                assert isinstance(response, dict) and response, (
                    f"Empty response declaration: {method.upper()} {path} {status}"
                )


def test_openapi_request_and_response_media_types_have_schemas():
    schema = app.openapi()
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            declarations = []
            if "requestBody" in operation:
                declarations.append(("request", operation["requestBody"]))
            declarations.extend(
                (f"response {status}", response)
                for status, response in operation["responses"].items()
            )
            for kind, declaration in declarations:
                # Reference validity is verified by test_v1_openapi_integrity.
                if "$ref" in declaration:
                    continue
                for media_type, media in declaration.get("content", {}).items():
                    assert "/" in media_type and media_type.split("/", 1)[0], (
                        f"Invalid media type {media_type!r}: {kind} {method} {path}"
                    )
                    assert isinstance(media, dict) and ("schema" in media), (
                        f"Missing media schema: {kind} {media_type} {method} {path}"
                    )
