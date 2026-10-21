"""Process GitHub-authenticated submissions; run only trusted code from main.

The data branch is a public database, never an executable checkout. Tokens are
read from the environment and never interpolated into contributor-controlled text.
"""

from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import time
import types
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
# Load pure modules without importing the Home Assistant package initializer.
package = types.ModuleType("isl_protocol")
package.__path__ = [str(ROOT / "custom_components/improved_shopping_list")]
sys.modules[package.__name__] = package
protocol = importlib.import_module("isl_protocol.community_data")
TOKEN = os.environ["GH_TOKEN"]
API = "https://api.github.com/repos/"+protocol.REPO
OUTPUT = ROOT / ".community-output"


def request(url, *, method="GET", data=None, github=True, limit=4*1024*1024):
    headers = {"Accept": "application/json", "User-Agent": "ISL-community-validator"}
    if github:
        if not url.startswith("https://api.github.com/"):
            raise ValueError("Invalid GitHub destination")
        headers["Authorization"] = "Bearer "+TOKEN
    if data is not None:
        headers["Content-Type"] = "application/json"
    # No untrusted URL reaches this function. urllib defaults would follow redirects;
    # known GitHub/Iconify API destinations are additionally checked after opening.
    with urlopen(Request(url, data=json.dumps(data).encode() if data is not None else None,
                         headers=headers, method=method), timeout=30) as response:
        if response.geturl().split("/", 3)[:3] != url.split("/", 3)[:3]:
            raise ValueError("Unexpected API redirect")
        raw = response.read(limit+1)
        if len(raw) > limit:
            raise ValueError("Response too large")
        return json.loads(raw)


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def authored(item, user):
    return (item.get("user", {}).get("id") == user
        and (item.get("performed_via_github_app") or {}).get("id") == protocol.APP_ID)


def parse_body(body):
    if not isinstance(body, str) or not body.startswith(protocol.MARKER) or len(body) > 60000:
        raise ValueError("Invalid contribution envelope")
    try:
        return json.loads(body[len(protocol.MARKER):])
    except RecursionError as err:
        raise ValueError("Envelope nesting too deep") from err


def load_data(filename, default):
    try:
        return request(f"https://raw.githubusercontent.com/{protocol.REPO}/data/community/{filename}", github=False, limit=64*1024*1024)
    except HTTPError as err:
        if err.code != 404:
            raise
        return default


def icon_metadata(registry, policy):
    identifiers = {icon for record in registry["records"].values() for vote in record["votes"].values()
                   for icon in vote["item"]["icons"]}
    prefixes = ({icon.split(":")[0] for icon in identifiers} & set(policy["allowed_icon_prefixes"])) - set(policy["excluded_icon_prefixes"])
    cache = {}
    for prefix in sorted(prefixes)[:100]:
        try:
            data = request("https://api.iconify.design/collection?prefix="+prefix+"&info=true", github=False)
            info = data.get("info", {})
            license_info = info.get("license", {})
            license_id = license_info.get("spdx", license_info.get("title", ""))
            if license_id not in policy["allowed_licenses"] or not info.get("author", {}).get("name"):
                continue
            names = set(data.get("uncategorized", []))
            for group in data.get("categories", {}).values():
                names.update(group)
            names.update(data.get("aliases", {}))
            urls = {"CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
                "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
                "MIT": "https://opensource.org/license/mit", "ISC": "https://opensource.org/license/isc-license-txt",
                "Apache-2.0": "https://www.apache.org/licenses/LICENSE-2.0"}
            if "api.iconify.design" not in policy["allowed_image_hosts"]:
                continue
            for identifier in identifiers:
                if identifier.startswith(prefix+":") and identifier.split(":", 1)[1] in names:
                    cache[identifier] = {"author": info["author"]["name"], "license": license_id,
                        "license_url": urls[license_id], "source_url": "https://icon-sets.iconify.design/"+identifier.replace(":", "/")+"/"}
        except (HTTPError, ValueError, OSError, TypeError):
            continue  # Unknown/unavailable provenance is excluded, never guessed.
    return cache


def main():
    policy = json.loads((ROOT / "community/policy.json").read_text())
    registry = load_data("registry.json", protocol.new_registry())
    now = time.time()
    accounts = {}
    close = []
    incomplete = 0
    # One account submits one issue per daily batch. Only open intake issues are read.
    # Limit work per invocation; the next run handles remaining open contributions.
    for page in range(1, 11):
        issues = request(API+f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}")
        if not issues:
            break
        for issue in issues:
            user = issue.get("user", {}).get("id")
            if not authored(issue, user) or not issue.get("body", "").startswith(protocol.MARKER):
                continue
            number = issue["number"]
            if user in policy["blocked_github_ids"] or number in registry["processed"]:
                close.append(number)
                continue
            try:
                manifest = parse_body(issue["body"])
                if type(manifest.get("parts")) is not int or not 1 <= manifest["parts"] <= 60:
                    raise ValueError("Invalid part count")
                comments = request(API+f"/issues/{number}/comments?per_page=100")
                parts = {}
                for comment in comments:
                    if not authored(comment, user):
                        continue
                    part = parse_body(comment["body"])
                    if (part.get("digest") == manifest["digest"] and type(part.get("part")) is int
                        and 0 <= part["part"] < manifest["parts"]):
                        if part["part"] in parts and parts[part["part"]] != part.get("data"):
                            raise ValueError("Conflicting contribution fragments")
                        parts[part["part"]] = part["data"]
                if len(parts) != manifest["parts"]:
                    incomplete += 1
                    if stamp(issue["created_at"]) < now-protocol.DAY*2:
                        close.append(number)
                    continue
                payload = protocol.unpack(manifest, [parts[i] for i in range(manifest["parts"])])
                # Prices are validated against submission time, never workflow execution time.
                created = stamp(issue["created_at"])
                if user not in accounts:
                    account = request("https://api.github.com/users/"+issue["user"]["login"])
                    accounts[user] = created-stamp(account["created_at"]) >= policy["minimum_account_age_days"]*protocol.DAY
                protocol.contribute(registry, payload, user, created, number,
                    banned=policy["blocked_github_ids"], eligible=accounts[user])
                close.append(number)
            except (ValueError, KeyError, TypeError):
                # Invalid authenticated payloads consume their daily slot too.
                registry["last_submission"][str(user)] = max(stamp(issue["created_at"]), registry["last_submission"].get(str(user), 0))
                registry["processed"].append(number)
                close.append(number)
    dictionary = protocol.compile_dictionary(registry, now, banned=policy["blocked_github_ids"],
        icon_metadata=icon_metadata(registry, policy))
    protocol.validate_dictionary(dictionary, now)
    OUTPUT.mkdir(exist_ok=True)
    for filename, data in (("registry.json", registry), ("products.json", dictionary), ("close.json", sorted(set(close)))):
        (OUTPUT/filename).write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))+"\n")
    print(f"Validated dictionary: {len(dictionary['products'])} products; {len(close)} completed batches; {incomplete} incomplete batches.")


if __name__ == "__main__":
    if "--close" in sys.argv:
        # Only acknowledge after the data commit has been pushed successfully.
        for number in json.loads((OUTPUT/"close.json").read_text()):
            request(API+f"/issues/{int(number)}", method="PATCH", data={"state": "closed"})
    else:
        main()
