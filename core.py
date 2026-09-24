# -*- coding: utf-8 -*-
"""
core.py — o "motor" do Segundo Cérebro.

Responsável por:
- Ler a pasta `vault/` (onde ficam os arquivos .md)
- Fazer parse do front matter (YAML) de cada nota
- Extrair [[wikilinks]] e #tags do corpo do texto
- Calcular backlinks (quem linka para quem)
- Montar os dados do grafo de conexões
- Criar, salvar, renomear e apagar notas
- Buscar notas por texto, tipo ou tag

Tudo é guardado como arquivos .md com front matter YAML — texto puro,
compatível com Obsidian, fácil de sincronizar pelo Google Drive, Dropbox,
git, etc. Não existe "banco de dados" escondido: os arquivos SÃO os dados.
Mantemos apenas um índice em memória (reconstruído a partir dos arquivos
toda vez que o servidor inicia, e atualizado incrementalmente conforme
você usa o app) para tornar buscas e o grafo rápidos.
"""
from __future__ import annotations

import os
import re
import uuid
import unicodedata
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

import yaml

# --------------------------------------------------------------------------
# Configuração de tipos de nota. Cada tipo tem uma subpasta dentro do vault
# e uma lista de campos estruturados extras (além dos campos comuns como
# título e tags). Isso é o que dá o "jeito Notion" às coleções de Jogos e
# Livros, enquanto Notas/Ideias continuam livres, ao "jeito Obsidian".
# --------------------------------------------------------------------------
TYPES: dict[str, dict[str, Any]] = {
    "nota": {
        "label": "Nota",
        "folder": "Notas",
        "fields": [],
    },
    "ideia": {
        "label": "Ideia",
        "folder": "Ideias",
        "fields": [],
    },
    "jogo": {
        "label": "Jogo",
        "folder": "Jogos",
        "fields": [
            {"key": "status", "label": "Status", "type": "select",
             "options": ["quero jogar", "jogando", "concluído", "abandonado", "platinado"],
             "default": "quero jogar"},
            {"key": "nota", "label": "Nota", "type": "rating", "max": 10, "default": None},
            {"key": "plataforma", "label": "Plataforma", "type": "text", "default": ""},
            {"key": "horas", "label": "Horas jogadas", "type": "number", "default": None},
        ],
    },
    "livro": {
        "label": "Livro",
        "folder": "Livros",
        "fields": [
            {"key": "status", "label": "Status", "type": "select",
             "options": ["quero ler", "lendo", "lido", "abandonado"],
             "default": "quero ler"},
            {"key": "nota", "label": "Nota", "type": "rating", "max": 10, "default": None},
            {"key": "autor", "label": "Autor", "type": "text", "default": ""},
            {"key": "paginas", "label": "Páginas", "type": "number", "default": None},
        ],
    },
}

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
TAG_RE = re.compile(r"(?<!\w)#([a-zA-Z0-9_\-/À-ÖØ-öø-ÿ]+)")
_CODE_RE = re.compile(r"```.*?```|`[^`\n]+`", re.DOTALL)


def mask_code(text: str) -> tuple[str, list[str]]:
    """Substitui trechos de código (```blocos``` e `inline`) por marcadores,
    para que [[wikilinks]] e #tags escritos como *exemplo* dentro de código
    não sejam tratados como links/tags de verdade. Use `restore_code` depois."""
    codes: list[str] = []

    def _repl(m: "re.Match") -> str:
        codes.append(m.group(0))
        return f"\x00C{len(codes) - 1}\x00"

    return _CODE_RE.sub(_repl, text), codes


def restore_code(text: str, codes: list[str]) -> str:
    for i, c in enumerate(codes):
        text = text.replace(f"\x00C{i}\x00", c)
    return text


def slugify(text: str) -> str:
    """Transforma um título em um nome de arquivo seguro, mantendo leitura fácil."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    text = re.sub(r"[\s_]+", "-", text)
    return text or uuid.uuid4().hex[:8]


def _json_safe(value: Any) -> Any:
    """Converte tipos que o YAML pode devolver (date/datetime) para string,
    para que o front matter possa ser enviado como JSON para o navegador."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


class Note:
    """Representa uma nota carregada em memória."""

    def __init__(self, path: Path, vault_root: Path):
        self.path = path
        self.rel_path = str(path.relative_to(vault_root))
        self.id = self.rel_path  # o caminho relativo é o identificador estável
        self.frontmatter: dict[str, Any] = {}
        self.body: str = ""
        self._load()

    def _load(self) -> None:
        raw = self.path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(raw)
        self.frontmatter = fm
        self.body = body

    # -- campos derivados -------------------------------------------------
    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title") or self.path.stem.replace("-", " "))

    @property
    def type(self) -> str:
        return str(self.frontmatter.get("type") or "nota")

    @property
    def tags(self) -> list[str]:
        fm_tags = self.frontmatter.get("tags") or []
        if isinstance(fm_tags, str):
            fm_tags = [t.strip() for t in fm_tags.split(",") if t.strip()]
        masked_body, _ = mask_code(self.body)
        body_tags = TAG_RE.findall(masked_body)
        seen = []
        for t in list(fm_tags) + body_tags:
            t = str(t).strip().lstrip("#")
            if t and t not in seen:
                seen.append(t)
        return seen

    @property
    def links(self) -> list[str]:
        """Títulos citados via [[wikilink]] dentro do corpo da nota."""
        out = []
        masked_body, _ = mask_code(self.body)
        for target, _alias in WIKILINK_RE.findall(masked_body):
            target = target.strip()
            if target and target not in out:
                out.append(target)
        return out

    @property
    def mtime(self) -> float:
        return self.path.stat().st_mtime

    def to_dict(self, include_body: bool = False) -> dict[str, Any]:
        d = {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "tags": self.tags,
            "links": self.links,
            "frontmatter": _json_safe(self.frontmatter),
            "updated": datetime.fromtimestamp(self.mtime).isoformat(timespec="seconds"),
            "excerpt": _make_excerpt(self.body),
        }
        if include_body:
            d["body"] = self.body
        return d


def _make_excerpt(body: str, length: int = 160) -> str:
    text = WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), body)
    text = re.sub(r"[#>*`_-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:length] + "…") if len(text) > length else text


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Separa o front matter YAML (entre --- no topo do arquivo) do corpo."""
    if raw.startswith("---"):
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, flags=re.DOTALL)
        if m:
            fm_raw, body = m.group(1), m.group(2)
            try:
                fm = yaml.safe_load(fm_raw) or {}
                if not isinstance(fm, dict):
                    fm = {}
            except yaml.YAMLError:
                fm = {}
            return fm, body
    return {}, raw


def join_frontmatter(fm: dict[str, Any], body: str) -> str:
    fm_clean = {k: v for k, v in fm.items() if v not in (None, "", [])}
    fm_yaml = yaml.safe_dump(fm_clean, allow_unicode=True, sort_keys=False).strip()
    body = body if body.startswith("\n") else "\n" + body
    return f"---\n{fm_yaml}\n---\n{body}"


class Vault:
    """Mantém o índice em memória de todas as notas do vault e oferece
    as operações de alto nível usadas pela API do Flask."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for cfg in TYPES.values():
            (self.root / cfg["folder"]).mkdir(parents=True, exist_ok=True)
        self._notes: dict[str, Note] = {}
        self.reindex()

    # -- indexação ----------------------------------------------------
    def reindex(self) -> None:
        notes: dict[str, Note] = {}
        for path in self.root.rglob("*.md"):
            if path.name.startswith("."):
                continue
            try:
                note = Note(path, self.root)
                notes[note.id] = note
            except Exception:
                # arquivo ilegível/corrompido: ignora em vez de derrubar o app
                continue
        self._notes = notes

    def _title_index(self) -> dict[str, list[Note]]:
        idx: dict[str, list[Note]] = {}
        for note in self._notes.values():
            idx.setdefault(note.title.lower(), []).append(note)
        return idx

    def resolve_link(self, target_title: str) -> Optional[Note]:
        target = target_title.strip().lower()
        for note in self._notes.values():
            if note.title.lower() == target:
                return note
        return None

    # -- consultas ------------------------------------------------------
    def all_notes(self) -> list[Note]:
        return sorted(self._notes.values(), key=lambda n: n.mtime, reverse=True)

    def get(self, note_id: str) -> Optional[Note]:
        return self._notes.get(note_id)

    def by_type(self, type_: str) -> list[Note]:
        return [n for n in self.all_notes() if n.type == type_]

    def backlinks(self, note: Note) -> list[Note]:
        out = []
        for other in self._notes.values():
            if other.id == note.id:
                continue
            if any(link.lower() == note.title.lower() for link in other.links):
                out.append(other)
        return out

    def all_tags(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for note in self._notes.values():
            for t in note.tags:
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def search(self, query: str = "", type_: str = "", tag: str = "") -> list[Note]:
        results = self.all_notes()
        if type_:
            results = [n for n in results if n.type == type_]
        if tag:
            results = [n for n in results if tag in n.tags]
        if query:
            q = query.strip().lower()
            scored = []
            for n in results:
                hay = f"{n.title}\n{n.body}".lower()
                if q in hay:
                    score = hay.count(q) + (10 if q in n.title.lower() else 0)
                    scored.append((score, n))
            scored.sort(key=lambda t: t[0], reverse=True)
            results = [n for _, n in scored]
        return results

    def graph_data(self) -> dict[str, Any]:
        nodes = []
        edges = []
        seen_edges = set()
        for note in self._notes.values():
            nodes.append({
                "id": note.id,
                "title": note.title,
                "type": note.type,
                "tags": note.tags,
            })
            for link_title in note.links:
                target = self.resolve_link(link_title)
                if target and target.id != note.id:
                    key = tuple(sorted((note.id, target.id)))
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append({"source": note.id, "target": target.id})
        return {"nodes": nodes, "edges": edges}

    def stats(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for n in self._notes.values():
            counts[n.type] = counts.get(n.type, 0) + 1
        return {
            "total": len(self._notes),
            "by_type": counts,
            "tags": len(self.all_tags()),
        }

    # -- escrita ----------------------------------------------------------
    def create(self, title: str, type_: str = "nota", extra_fm: Optional[dict] = None,
               body: str = "") -> Note:
        type_ = type_ if type_ in TYPES else "nota"
        cfg = TYPES[type_]
        folder = self.root / cfg["folder"]
        folder.mkdir(parents=True, exist_ok=True)

        base_slug = slugify(title)
        slug = base_slug
        i = 2
        while (folder / f"{slug}.md").exists():
            slug = f"{base_slug}-{i}"
            i += 1
        path = folder / f"{slug}.md"

        fm = {"title": title, "type": type_}
        for field in cfg["fields"]:
            fm[field["key"]] = field.get("default")
        if extra_fm:
            fm.update(extra_fm)
        fm["created"] = datetime.now().strftime("%Y-%m-%d")

        content = join_frontmatter(fm, body or "")
        path.write_text(content, encoding="utf-8")

        note = Note(path, self.root)
        self._notes[note.id] = note
        return note

    def save(self, note_id: str, *, title: Optional[str] = None,
              body: Optional[str] = None, frontmatter: Optional[dict] = None) -> Note:
        note = self.get(note_id)
        if note is None:
            raise KeyError(note_id)

        fm = dict(note.frontmatter)
        if frontmatter is not None:
            fm.update(frontmatter)
        if title is not None:
            fm["title"] = title
        new_body = note.body if body is None else body

        content = join_frontmatter(fm, new_body)
        note.path.write_text(content, encoding="utf-8")
        note._load()  # recarrega frontmatter/body a partir do disco
        return note

    def delete(self, note_id: str) -> None:
        note = self.get(note_id)
        if note is None:
            raise KeyError(note_id)
        note.path.unlink(missing_ok=True)
        del self._notes[note_id]

    def note_path_on_disk(self, note_id: str) -> Path:
        return self.root / note_id
