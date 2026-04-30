"""REST API for MemPalace.

Thin FastAPI wrapper that delegates to the existing tool_* handlers in
mcp_server. Each MCP tool maps to one REST endpoint. Auto-generated
OpenAPI at /openapi.json is what Dify (and other clients) import.

Run:  uvicorn mempalace.rest_server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import mcp_server as mcp
from .version import __version__

app = FastAPI(
    title="MemPalace REST API",
    version=__version__,
    description="HTTP surface over MemPalace. One endpoint per MemPalace tool.",
)


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
