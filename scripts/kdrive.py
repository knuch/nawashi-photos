"""Client minimal de l'API kDrive Infomaniak (stdlib uniquement).

Variables d'environnement :
  KDRIVE_ID     identifiant du kDrive (obligatoire)
  KDRIVE_TOKEN  jeton API, portée « drive ». Dans les sessions Claude Code cloud,
                le proxy réseau injecte le jeton : la variable peut être absente.
Le jeton n'est jamais écrit dans un fichier ni affiché.

Les chemins manipulés ici sont relatifs à la racine de la photothèque
(config.json → kdrive.racine_id), par ex. « originaux/2026-11-08-...jpg ».

Usage CLI :
  python scripts/kdrive.py check
  python scripts/kdrive.py ls [dossier]
  python scripts/kdrive.py get <chemin-kdrive> <fichier-local>
  python scripts/kdrive.py put <fichier-local> <dossier-kdrive> [nom]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.infomaniak.com"
REPO = Path(__file__).resolve().parent.parent
CONFIG = json.loads((REPO / "config.json").read_text(encoding="utf-8"))


class KDriveError(RuntimeError):
    pass


def _drive_id() -> str:
    drive_id = os.environ.get("KDRIVE_ID") or str(CONFIG["kdrive"].get("drive_id") or "")
    if not drive_id:
        raise KDriveError("KDRIVE_ID manquant")
    return drive_id


def _request(method: str, path: str, *, query: dict | None = None, body: bytes | None = None,
             json_body: dict | None = None, raw: bool = False):
    url = API + path.format(drive=_drive_id())
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    headers = {"Authorization": "Bearer " + os.environ.get("KDRIVE_TOKEN", "proxy-injected")}
    if json_body is not None:
        body = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif body is not None:
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        data = e.read()
        try:
            err = json.loads(data).get("error")
        except Exception:
            err = data[:300]
        raise KDriveError(f"{method} {path} → HTTP {e.code} : {err}") from None
    if raw:
        return data
    payload = json.loads(data)
    if payload.get("result") != "success":
        raise KDriveError(f"{method} {path} → {payload.get('error')}")
    return payload.get("data")


# --- opérations de base (par identifiant) ---------------------------------

def info(file_id: int) -> dict:
    return _request("GET", f"/3/drive/{{drive}}/files/{file_id}")


def list_dir(dir_id: int) -> list[dict]:
    """Contenu d'un dossier, toutes pages confondues (pagination par curseur)."""
    items, cursor = [], None
    while True:
        query = {"limit": 1000}
        if cursor:
            query["cursor"] = cursor
        url = f"/3/drive/{{drive}}/files/{dir_id}/files"
        full = _request_full("GET", url, query)
        items += full.get("data") or []
        if not full.get("has_more"):
            return items
        cursor = full.get("cursor")


def _request_full(method: str, path: str, query: dict) -> dict:
    """Comme _request mais renvoie l'enveloppe complète (cursor, has_more)."""
    raw = _request(method, path, query=query, raw=True)
    payload = json.loads(raw)
    if payload.get("result") != "success":
        raise KDriveError(f"{method} {path} → {payload.get('error')}")
    return payload


def mkdir(parent_id: int, name: str) -> dict:
    return _request("POST", f"/3/drive/{{drive}}/files/{parent_id}/directory", json_body={"name": name})


def upload(local: Path, dir_id: int, name: str | None = None, conflict: str = "error") -> dict:
    """Upload simple (≤ 1 Go). conflict : error | rename | version."""
    data = Path(local).read_bytes()
    query = {"directory_id": dir_id, "file_name": name or Path(local).name,
             "total_size": len(data), "conflict": conflict}
    return _request("POST", "/3/drive/{drive}/upload", query=query, body=data)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def download(file_id: int, dest: Path) -> Path:
    """Télécharge un fichier. L'API répond 302 vers un serveur de stockage
    (*.download.kdrive.infomaniakusercontent.com) : on suit la redirection
    nous-mêmes, sans y renvoyer l'en-tête Authorization."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = API + f"/2/drive/{_drive_id()}/files/{file_id}/download"
    headers = {"Authorization": "Bearer " + os.environ.get("KDRIVE_TOKEN", "proxy-injected")}
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=300) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise KDriveError(f"download {file_id} → HTTP {e.code}") from None
        with urllib.request.urlopen(e.headers["Location"], timeout=300) as resp:
            data = resp.read()
    dest.write_bytes(data)
    return dest


def rename(file_id: int, new_name: str) -> dict:
    return _request("POST", f"/2/drive/{{drive}}/files/{file_id}/rename", json_body={"name": new_name})


def move(file_id: int, dest_dir_id: int) -> dict:
    return _request("POST", f"/3/drive/{{drive}}/files/{file_id}/move/{dest_dir_id}")


def trash(file_id: int) -> dict:
    """Envoie à la corbeille kDrive (récupérable depuis l'interface)."""
    return _request("DELETE", f"/2/drive/{{drive}}/files/{file_id}")


# --- chemins relatifs à la racine de la photothèque ------------------------

def root_id() -> int:
    return int(CONFIG["kdrive"]["racine_id"])


_RESOLVE_CACHE: dict[str, int] = {}


def resolve(rel: str, create: bool = False) -> int:
    """Identifiant du fichier/dossier au chemin relatif `rel` (« previews/512 »)."""
    rel = rel.strip("/")
    if rel in _RESOLVE_CACHE:
        return _RESOLVE_CACHE[rel]
    current = root_id()
    for part in [p for p in rel.strip("/").split("/") if p]:
        found = [f for f in list_dir(current) if f["name"] == part]
        if found:
            current = found[0]["id"]
        elif create:
            current = mkdir(current, part)["id"]
        else:
            raise KDriveError(f"introuvable sur kDrive : {rel}")
    if rel in CONFIG["kdrive"]["dossiers"]:
        _RESOLVE_CACHE[rel] = current
    return current


def ensure_tree() -> dict[str, int]:
    """Crée l'arborescence de config.json si elle manque ; renvoie {chemin: id}."""
    return {d: resolve(d, create=True) for d in CONFIG["kdrive"]["dossiers"]}


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "check"
    if cmd == "check":
        root = info(root_id())
        print(f"kDrive {_drive_id()} OK — racine : {root.get('path') or root['name']} (id {root['id']})")
        for path, fid in ensure_tree().items():
            print(f"  {path:<14} id {fid}")
    elif cmd == "ls":
        for f in list_dir(resolve(argv[1] if len(argv) > 1 else "")):
            print(f"{f['type']:<4} {f['id']:>8} {f.get('size') or '':>10} {f['name']}")
    elif cmd == "get":
        print(download(resolve(argv[1]), Path(argv[2])))
    elif cmd == "put":
        res = upload(Path(argv[1]), resolve(argv[2]), argv[3] if len(argv) > 3 else None)
        print(res.get("file", res).get("id") if isinstance(res, dict) else res)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KDriveError as e:
        sys.exit(f"Erreur kDrive : {e}")
