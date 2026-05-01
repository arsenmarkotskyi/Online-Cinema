"""Register /docs, /redoc, and /openapi.json (public or JWT-only per settings)."""

from __future__ import annotations

import html
import json

from fastapi import Depends, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from src.auth.dependencies import get_current_active_user
from src.database.models import User


def register_openapi_documentation(app: FastAPI, *, require_auth: bool) -> None:
    """Mount OpenAPI UI; if ``require_auth``, only active users may access."""
    doc_title = (app.title or "API") + " - Swagger UI"
    redoc_title = (app.title or "API") + " - ReDoc"

    if not require_auth:

        @app.get("/openapi.json", include_in_schema=False)
        async def openapi_json() -> JSONResponse:
            return JSONResponse(app.openapi())

        @app.get("/docs", include_in_schema=False)
        async def swagger_ui_html() -> HTMLResponse:
            return get_swagger_ui_html(
                openapi_url="/openapi.json",
                title=doc_title,
            )

        @app.get("/redoc", include_in_schema=False)
        async def redoc_html() -> HTMLResponse:
            return get_redoc_html(
                openapi_url="/openapi.json",
                title=redoc_title,
            )

        return

    @app.get("/openapi.json", include_in_schema=False)
    async def openapi_json_auth(
        _: User = Depends(get_current_active_user),
    ) -> JSONResponse:
        return JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui_html_auth(
        _: User = Depends(get_current_active_user),
    ) -> HTMLResponse:
        return _swagger_ui_inline(app, title=html.escape(doc_title))

    @app.get("/redoc", include_in_schema=False)
    async def redoc_html_auth(
        _: User = Depends(get_current_active_user),
    ) -> HTMLResponse:
        return _redoc_inline(app, title=html.escape(redoc_title))


def _spec_json_parse_js_literal(app: FastAPI) -> str:
    """Double-encoded JSON string safe to embed in ``JSON.parse(...)`` in JS."""
    spec = jsonable_encoder(app.openapi())
    return json.dumps(json.dumps(spec))


def _swagger_ui_inline(app: FastAPI, *, title: str) -> HTMLResponse:
    """Swagger UI with inlined OpenAPI (avoids a separate public schema fetch)."""
    spec_literal = _spec_json_parse_js_literal(app)
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
  <title>{title}</title>
</head>
<body>
  <div id="swagger-ui"></div>
  <script
    src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
  ></script>
  <script>
    const spec = JSON.parse({spec_literal});
    SwaggerUIBundle({{
      spec: spec,
      dom_id: '#swagger-ui',
      layout: 'BaseLayout',
      deepLinking: true,
      showExtensions: true,
      showCommonExtensions: true,
      persistAuthorization: true,
      presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset
      ],
    }});
  </script>
</body>
</html>"""
    )


def _redoc_inline(app: FastAPI, *, title: str) -> HTMLResponse:
    """ReDoc with inlined spec (no unauthenticated ``openapi.json`` fetch)."""
    spec_literal = _spec_json_parse_js_literal(app)
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html>
<head>
  <title>{title}</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link
    href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700"
    rel="stylesheet"
  >
  <style>body {{ margin: 0; padding: 0; }}</style>
</head>
<body>
  <div id="redoc-container"></div>
  <script
    src="https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js"
  ></script>
  <script>
    const spec = JSON.parse({spec_literal});
    Redoc.init(spec, document.getElementById('redoc-container'));
  </script>
</body>
</html>"""
    )
