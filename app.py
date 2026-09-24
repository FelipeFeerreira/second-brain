# -*- coding: utf-8 -*-
"""
Segundo Cérebro — servidor local (Flask).

Como rodar:
    python app.py

Depois abra http://127.0.0.1:5000 no navegador.

Onde ficam os dados:
    Por padrão, tudo é salvo em ./vault (arquivos .md). Para sincronizar
    entre computadores pelo Google Drive, mova (ou aponte) essa pasta para
    dentro da pasta do Google Drive sincronizada no seu computador — veja
    o config.json e o README.md para instruções.
"""
from __future__ import annotations

import argparse
import json
import html as html_lib
from pathlib import Path

import markdown as md
from flask import Flask, jsonify, request, send_from_directory

from core import Vault, TYPES, WIKILINK_RE, mask_code, restore_code

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def resolve_vault_path(cli_arg: str | None) -> Path:
    if cli_arg:
        return Path(cli_arg).expanduser()
    cfg = load_config()
    if cfg.get("vault_path"):
        return Path(cfg["vault_path"]).expanduser()
    return BASE_DIR / "vault"


def render_markdown(body: str, vault: Vault) -> str:
    """Converte markdown -> HTML, resolvendo [[wikilinks]] para <a> clicáveis
    (marcando com a classe 'broken' quando a nota alvo ainda não existe,
    para que o usuário possa criá-la com um clique — como no Obsidian)."""

    def _replace(m: "re.Match") -> str:
        target = m.group(1).strip()
        alias = (m.group(2) or target).strip()
        found = vault.resolve_link(target)
        cls = "wikilink" if found else "wikilink broken"
        target_id = found.id if found else ""
        return (
            f'<a href="#" class="{cls}" '
            f'data-target-id="{html_lib.escape(target_id)}" '
            f'data-target-title="{html_lib.escape(target)}">{html_lib.escape(alias)}</a>'
        )

    masked, codes = mask_code(body)
    masked = WIKILINK_RE.sub(_replace, masked)
    pre_processed = restore_code(masked, codes)
    return md.markdown(
        pre_processed,
        extensions=["fenced_code", "tables", "nl2br", "sane_lists", "codehilite"],
        extension_configs={"codehilite": {"guess_lang": False}},
    )


def create_app(vault_path: Path) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    vault = Vault(vault_path)
    app.config["VAULT"] = vault

    # ---------------------------------------------------------------- UI
    @app.get("/")
    def index():
        return send_from_directory(app.template_folder, "index.html")

    # ------------------------------------------------------------- config
    @app.get("/api/types")
    def api_types():
        return jsonify(TYPES)

    @app.get("/api/stats")
    def api_stats():
        vault.reindex()
        return jsonify(vault.stats())

    @app.get("/api/vault-info")
    def api_vault_info():
        return jsonify({"path": str(vault.root.resolve())})

    # -------------------------------------------------------------- notas
    @app.get("/api/notes")
    def api_notes_list():
        vault.reindex()
        q = request.args.get("q", "")
        type_ = request.args.get("type", "")
        tag = request.args.get("tag", "")
        notes = vault.search(query=q, type_=type_, tag=tag)
        return jsonify([n.to_dict() for n in notes])

    @app.post("/api/notes")
    def api_notes_create():
        data = request.get_json(force=True) or {}
        title = (data.get("title") or "Sem título").strip()
        type_ = data.get("type") or "nota"
        extra_fm = data.get("frontmatter") or {}
        body = data.get("body") or ""
        note = vault.create(title=title, type_=type_, extra_fm=extra_fm, body=body)
        return jsonify(note.to_dict(include_body=True)), 201

    @app.get("/api/notes/<path:note_id>")
    def api_notes_get(note_id: str):
        vault.reindex()
        note = vault.get(note_id)
        if note is None:
            return jsonify({"error": "não encontrada"}), 404
        d = note.to_dict(include_body=True)
        d["html"] = render_markdown(note.body, vault)
        d["backlinks"] = [n.to_dict() for n in vault.backlinks(note)]
        return jsonify(d)

    @app.put("/api/notes/<path:note_id>")
    def api_notes_update(note_id: str):
        data = request.get_json(force=True) or {}
        try:
            note = vault.save(
                note_id,
                title=data.get("title"),
                body=data.get("body"),
                frontmatter=data.get("frontmatter"),
            )
        except KeyError:
            return jsonify({"error": "não encontrada"}), 404
        d = note.to_dict(include_body=True)
        d["html"] = render_markdown(note.body, vault)
        return jsonify(d)

    @app.delete("/api/notes/<path:note_id>")
    def api_notes_delete(note_id: str):
        try:
            vault.delete(note_id)
        except KeyError:
            return jsonify({"error": "não encontrada"}), 404
        return jsonify({"ok": True})

    # --------------------------------------------------------------- misc
    @app.post("/api/render")
    def api_render():
        data = request.get_json(force=True) or {}
        body = data.get("body") or ""
        return jsonify({"html": render_markdown(body, vault)})

    @app.get("/api/tags")
    def api_tags():
        vault.reindex()
        return jsonify(vault.all_tags())

    @app.get("/api/graph")
    def api_graph():
        vault.reindex()
        return jsonify(vault.graph_data())

    @app.post("/api/reindex")
    def api_reindex():
        vault.reindex()
        return jsonify({"ok": True, "stats": vault.stats()})

    return app


def main():
    parser = argparse.ArgumentParser(description="Segundo Cérebro — servidor local")
    parser.add_argument("--vault", help="Caminho da pasta do vault (sobrepõe config.json)")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    vault_path = resolve_vault_path(args.vault)
    app = create_app(vault_path)
    print(f"\nSegundo Cérebro rodando!  Vault: {vault_path.resolve()}")
    print(f"Abra no navegador: http://{args.host}:{args.port}\n")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
