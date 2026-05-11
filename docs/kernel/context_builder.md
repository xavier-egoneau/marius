# context_builder

## Rôle

Assemble des sources Markdown explicites en un `system_prompt` déterministe. Ne découvre pas le projet seul — reçoit des sources déclarées par le host ou `project_context`.

## Couche

Kernel

## Standalone

Oui. Utilisable dans tout assistant piloté par des fichiers Markdown.

## Dépendances

Aucune dépendance interne Marius (stdlib + lecture de fichiers via protocole injecté).

## Interface publique

```python
class MarkdownSourceReader(Protocol):
    def read_text(self, path: Path) -> str | None: ...

@dataclass
class ContextSource:
    key: str          # identifiant unique ("soul", "user", "agents", etc.)
    title: str        # titre affiché dans le prompt assemblé
    path: Path        # chemin vers le fichier .md
    required: bool    # si True, une absence lève MissingContextSourceError

@dataclass
class ContextBuildInput:
    sources: list[ContextSource]   # ordre déclaré = ordre d'assemblage
    preamble: str = ""             # texte injecté en tête du prompt

@dataclass
class ContextBundle:
    markdown: str                          # Markdown assemblé, prêt pour le provider
    loaded_sources: list[ContextSource]    # sources chargées avec succès
    missing_optional_sources: list[ContextSource]
    metadata: dict

class ContextBuilder:
    def __init__(self, *, reader: MarkdownSourceReader)
    def build(self, build_input: ContextBuildInput) -> ContextBundle
```

## Usage

```python
from marius.kernel.context_builder import ContextBuildInput, ContextBuilder, ContextSource
from pathlib import Path

class FileReader:
    def read_text(self, path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError):
            return None

sources = [
    ContextSource(key="soul",   title="Identité",    path=Path("~/.marius/SOUL.md").expanduser(),   required=False),
    ContextSource(key="user",   title="Contexte",    path=Path("~/.marius/USER.md").expanduser(),   required=False),
    ContextSource(key="agents", title="Conventions", path=Path("~/.marius/AGENTS.md").expanduser(), required=False),
]
bundle = ContextBuilder(reader=FileReader()).build(ContextBuildInput(sources=sources))
system_prompt = bundle.markdown
```

## Invariants

- Une source `required=True` absente lève `MissingContextSourceError`.
- Une source `required=False` absente est tracée dans `missing_optional_sources` sans interrompre le build.
- L'ordre des sources est préservé dans `markdown`.
- Le builder ne devine pas le projet actif — c'est la responsabilité du host.
