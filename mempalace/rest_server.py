"""REST API for MemPalace.

Thin FastAPI wrapper that delegates to the existing tool_* handlers in
mcp_server. Each MCP tool maps to one REST endpoint. Auto-generated
OpenAPI at /openapi.json is what Dify (and other clients) import.

Run:  uvicorn mempalace.rest_server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field

from . import mcp_server as mcp
from .version import __version__

app = FastAPI(
    title="MemPalace REST API",
    version=__version__,
    description="HTTP surface over MemPalace. One endpoint per MemPalace tool.",
)


# Dify (and other OpenAPI 3.0-only consumers) cannot parse the 3.1.0 schema
# FastAPI emits by default — type arrays like `["string", "null"]`, `examples`
# lists, and numeric `exclusiveMinimum`/`exclusiveMaximum` all trip its
# importer. Override `app.openapi` to emit a 3.0.3-compatible schema.
def _is_null_schema(s: Any) -> bool:
    return isinstance(s, dict) and s.get("type") == "null" and len(s) == 1


def _collapse_anyof_null(node: dict[str, Any]) -> None:
    # Pydantic v2 emits `Optional[T]` as anyOf: [<T>, {type: "null"}]. 3.0 has no
    # `null` type, so drop the null branch and set `nullable: true` on the rest.
    for key in ("anyOf", "oneOf"):
        variants = node.get(key)
        if not isinstance(variants, list):
            continue
        non_null = [v for v in variants if not _is_null_schema(v)]
        had_null = len(non_null) != len(variants)
        if not had_null:
            continue
        if len(non_null) == 1:
            survivor = non_null[0]
            del node[key]
            for k, v in survivor.items():
                node.setdefault(k, v)
            node["nullable"] = True
        else:
            node[key] = non_null
            node["nullable"] = True


def _downgrade_openapi_31_to_30(node: Any) -> None:
    if isinstance(node, dict):
        _collapse_anyof_null(node)
        t = node.get("type")
        if isinstance(t, list):
            non_null = [x for x in t if x != "null"]
            if len(non_null) == 1:
                node["type"] = non_null[0]
                if "null" in t:
                    node["nullable"] = True
        examples = node.get("examples")
        if isinstance(examples, list) and examples and "example" not in node:
            node["example"] = examples[0]
            del node["examples"]
        for key, partner in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
            v = node.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                node[partner] = v
                node[key] = True
        if node.get("const") is not None and "enum" not in node:
            node["enum"] = [node.pop("const")]
        for v in node.values():
            _downgrade_openapi_31_to_30(v)
    elif isinstance(node, list):
        for v in node:
            _downgrade_openapi_31_to_30(v)


def _custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema["openapi"] = "3.0.3"
    # Dify warns on a missing `servers` block. Allow override via env var so
    # operators can set the LAN URL the API is reachable on; fall back to a
    # relative URL, which Dify can override in its custom-tool UI anyway.
    public_url = os.environ.get("MEMPALACE_PUBLIC_URL", "/")
    schema["servers"] = [{"url": public_url}]
    _strip_validation_error_schemas(schema)
    _downgrade_openapi_31_to_30(schema)
    app.openapi_schema = schema
    return schema


def _strip_validation_error_schemas(schema: dict[str, Any]) -> None:
    # FastAPI auto-emits a 422 response on every body endpoint, with a
    # `ValidationError` schema whose `loc` is `list[str | int]`. Dify does not
    # use 422 schemas and its importer dislikes the resulting union. Strip the
    # 422 responses and the now-orphaned validation schemas.
    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for op in path_item.values():
            if isinstance(op, dict):
                op.get("responses", {}).pop("422", None)
    schemas = schema.get("components", {}).get("schemas", {})
    schemas.pop("ValidationError", None)
    schemas.pop("HTTPValidationError", None)


app.openapi = _custom_openapi  # type: ignore[method-assign]


# ──────────────────────────────────────────────────────────────────────────────
# Discovery / read-only
# ──────────────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/status", tags=["palace"])
def status() -> Any:
    return mcp.tool_status()


@app.get("/wings", tags=["palace"])
def list_wings() -> Any:
    return mcp.tool_list_wings()


@app.get("/rooms", tags=["palace"])
def list_rooms(wing: str | None = None) -> Any:
    return mcp.tool_list_rooms(wing=wing)


@app.get("/taxonomy", tags=["palace"])
def get_taxonomy() -> Any:
    return mcp.tool_get_taxonomy()


@app.get("/aaak-spec", tags=["meta"])
def get_aaak_spec() -> Any:
    return mcp.tool_get_aaak_spec()


# ──────────────────────────────────────────────────────────────────────────────
# Search / write
# ──────────────────────────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str = Field(..., description="What to search for")
    limit: int = Field(5, description="Max results")
    wing: str | None = Field(None, description="Filter by wing")
    room: str | None = Field(None, description="Filter by room")


@app.post("/search", tags=["search"])
def search(req: SearchRequest) -> Any:
    return mcp.tool_search(query=req.query, limit=req.limit, wing=req.wing, room=req.room)


class CheckDuplicateRequest(BaseModel):
    content: str = Field(..., description="Content to check")
    threshold: float = Field(0.9, description="Similarity threshold 0-1")


@app.post("/drawers/check-duplicate", tags=["drawers"])
def check_duplicate(req: CheckDuplicateRequest) -> Any:
    return mcp.tool_check_duplicate(content=req.content, threshold=req.threshold)


class AddDrawerRequest(BaseModel):
    wing: str = Field(..., description="Wing (project name)")
    room: str = Field(..., description="Room (aspect: backend, decisions, meetings...)")
    content: str = Field(..., description="Verbatim content to store — never summarized")
    source_file: str | None = Field(None, description="Where this came from")
    added_by: str = Field("rest", description="Who is filing this")


@app.post("/drawers", tags=["drawers"])
def add_drawer(req: AddDrawerRequest) -> Any:
    return mcp.tool_add_drawer(
        wing=req.wing,
        room=req.room,
        content=req.content,
        source_file=req.source_file,
        added_by=req.added_by,
    )


@app.delete("/drawers/{drawer_id}", tags=["drawers"])
def delete_drawer(drawer_id: str) -> Any:
    return mcp.tool_delete_drawer(drawer_id=drawer_id)


# ──────────────────────────────────────────────────────────────────────────────
# Knowledge graph
# ──────────────────────────────────────────────────────────────────────────────


@app.get("/kg/query", tags=["kg"])
def kg_query(
    entity: str,
    as_of: str | None = None,
    direction: str = "both",
) -> Any:
    return mcp.tool_kg_query(entity=entity, as_of=as_of, direction=direction)


class KgAddRequest(BaseModel):
    subject: str = Field(..., description="The entity doing/being something")
    predicate: str = Field(..., description="Relationship type (e.g. 'loves', 'works_on')")
    object: str = Field(..., description="The entity being connected to")
    valid_from: str | None = Field(None, description="When this became true (YYYY-MM-DD)")
    source_closet: str | None = Field(None, description="Closet ID where this fact appears")


@app.post("/kg/facts", tags=["kg"])
def kg_add(req: KgAddRequest) -> Any:
    return mcp.tool_kg_add(
        subject=req.subject,
        predicate=req.predicate,
        object=req.object,
        valid_from=req.valid_from,
        source_closet=req.source_closet,
    )


class KgInvalidateRequest(BaseModel):
    subject: str
    predicate: str
    object: str
    ended: str | None = Field(None, description="When it stopped being true (YYYY-MM-DD)")


@app.post("/kg/facts/invalidate", tags=["kg"])
def kg_invalidate(req: KgInvalidateRequest) -> Any:
    return mcp.tool_kg_invalidate(
        subject=req.subject,
        predicate=req.predicate,
        object=req.object,
        ended=req.ended,
    )


@app.get("/kg/timeline", tags=["kg"])
def kg_timeline(entity: str | None = None) -> Any:
    return mcp.tool_kg_timeline(entity=entity)


@app.get("/kg/stats", tags=["kg"])
def kg_stats() -> Any:
    return mcp.tool_kg_stats()


# ──────────────────────────────────────────────────────────────────────────────
# Palace graph (rooms / tunnels)
# ──────────────────────────────────────────────────────────────────────────────


@app.get("/graph/traverse", tags=["graph"])
def traverse(start_room: str, max_hops: int = 2) -> Any:
    return mcp.tool_traverse_graph(start_room=start_room, max_hops=max_hops)


@app.get("/graph/tunnels", tags=["graph"])
def find_tunnels(wing_a: str | None = None, wing_b: str | None = None) -> Any:
    return mcp.tool_find_tunnels(wing_a=wing_a, wing_b=wing_b)


@app.get("/graph/stats", tags=["graph"])
def graph_stats() -> Any:
    return mcp.tool_graph_stats()


# ──────────────────────────────────────────────────────────────────────────────
# Agent diary
# ──────────────────────────────────────────────────────────────────────────────


class DiaryWriteRequest(BaseModel):
    agent_name: str = Field(..., description="Your name — each agent gets their own diary wing")
    entry: str = Field(..., description="Diary entry, AAAK-compressed")
    topic: str = Field("general", description="Topic tag")


@app.post("/diary", tags=["diary"])
def diary_write(req: DiaryWriteRequest) -> Any:
    return mcp.tool_diary_write(
        agent_name=req.agent_name,
        entry=req.entry,
        topic=req.topic,
    )


@app.get("/diary/{agent_name}", tags=["diary"])
def diary_read(agent_name: str, last_n: int = 10) -> Any:
    return mcp.tool_diary_read(agent_name=agent_name, last_n=last_n)
