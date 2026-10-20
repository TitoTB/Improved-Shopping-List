"""Atomically publish validated data to an orphan data branch, not an integration release."""

import argparse
import base64
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

from shopping_feed import protocol


class GitHubDataPublisher:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token:
            raise ValueError("Falta el repositorio o el token privado de publicación.")
        self.root = f"https://api.github.com/repos/{repository}"
        self.token = token

    def request(self, method, path, body=None, missing_ok=False):
        request = urllib.request.Request(self.root+path, method=method,
            data=protocol.encode(body) if body is not None else None,
            headers={"Authorization":f"Bearer {self.token}","Accept":"application/vnd.github+json",
                "Content-Type":"application/json","User-Agent":"Improved-Shopping-List-data"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404 and missing_ok:
                return None
            raise ValueError(f"GitHub rechazó la publicación (HTTP {error.code}). No se actualizó la rama de datos.") from None
        except (urllib.error.URLError, TimeoutError):
            raise ValueError("No se pudo contactar con GitHub. No se actualizó la rama de datos.") from None

    def publish(self, directory):
        directory = Path(directory)
        manifest_raw = (directory/"manifest.json").read_bytes()
        manifest = json.loads(manifest_raw)
        if manifest.get("schema") != 1 or manifest.get("store") != "carrefour":
            raise ValueError("El manifiesto preparado no es válido.")
        reference = protocol.check_descriptor(manifest["snapshot"])
        body = (directory/reference["path"]).read_bytes()
        if protocol.digest(body) != manifest["version"] or protocol.digest(body) != reference["sha256"] or len(body) != reference["bytes"]:
            raise ValueError("El catálogo preparado no es válido.")
        products = protocol.read_snapshot(body)
        if len(products) != manifest.get("products_count"):
            raise ValueError("El catálogo preparado no está completo.")
        files = {reference["path"]:body,"manifest.json":manifest_raw}
        delta = manifest.get("delta")
        if delta:
            ref = protocol.check_descriptor({key:delta[key] for key in ("path","sha256","bytes")})
            raw = (directory/ref["path"]).read_bytes()
            if protocol.digest(raw) != ref["sha256"] or len(raw) != ref["bytes"]:
                raise ValueError("El delta preparado no es válido.")
            files[ref["path"]] = raw
        previous = self.request("GET","/git/ref/heads/data",missing_ok=True)
        tree = []
        for path, raw in files.items():
            blob = self.request("POST","/git/blobs",{"content":base64.b64encode(raw).decode(),"encoding":"base64"})
            tree.append({"path":"carrefour/"+path,"mode":"100644","type":"blob","sha":blob["sha"]})
        payload = {"tree":tree}
        parents = []
        if previous:
            parents = [previous["object"]["sha"]]
            commit = self.request("GET","/git/commits/"+parents[0])
            payload["base_tree"] = commit["tree"]["sha"]
        tree = self.request("POST","/git/trees",payload)
        commit = self.request("POST","/git/commits",{"message":"Update Carrefour shopping data","tree":tree["sha"],"parents":parents})
        if previous:
            self.request("PATCH","/git/refs/heads/data",{"sha":commit["sha"],"force":False})
        else:
            self.request("POST","/git/refs",{"ref":"refs/heads/data","sha":commit["sha"]})
        return commit["sha"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--repository", default="TitoTB/Improved-Shopping-List")
    parser.add_argument("--publish", action="store_true", help="Publish the prepared catalog; omitted means no remote writes.")
    args = parser.parse_args()
    if not args.publish:
        parser.exit(0,"Publicación desactivada. Añade --publish únicamente cuando corresponda publicar los datos.\n")
    try:
        sha = GitHubDataPublisher(args.repository,os.environ.get("SHOPPING_DATA_GITHUB_TOKEN","")).publish(args.directory)
    except (ValueError, OSError, KeyError):
        parser.exit(1,"No se pudo publicar el catálogo validado. Revisa la configuración privada.\n")
    print(json.dumps({"commit":sha}))
