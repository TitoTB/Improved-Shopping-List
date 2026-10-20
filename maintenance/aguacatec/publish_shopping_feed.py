"""Install as apps/panel/management/commands/publish_shopping_feed.py in Aguacatec."""

import csv
import io
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.panel.awin_feeds import AwinFeedError, download_feed
from apps.panel.management.commands.run_due_crons import command_lock
from apps.panel.models import DevicePlatform


def source_version(platform):
    url = "https://productdata.awin.com/datafeed/list/apikey/"+urllib.parse.quote(platform.awin_api_key,safe="")
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Aguacatec/1.0"}),timeout=60) as response:
            raw = response.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:
            raise ValueError("Lista demasiado grande")
        text = raw.decode("utf-8-sig")
        dialect = csv.Sniffer().sniff(text[:20000], delimiters=",;\t")
        for row in csv.DictReader(io.StringIO(text),dialect=dialect):
            fields = {key.strip().lower().replace("_"," "):value for key,value in row.items() if key}
            if fields.get("feed id") == str(platform.awin_feed_id):
                return fields.get("last imported") or None
        return None
    except (ValueError, OSError, csv.Error, urllib.error.URLError):
        # Fall back to a full download. Never expose the credential-bearing list URL.
        return None


class Command(BaseCommand):
    help = "Prepara el catálogo Carrefour de cinco campos; publica en GitHub solo con --publish."

    def add_arguments(self, parser):
        parser.add_argument("--integration-path", default=os.environ.get("SHOPPING_LIST_REPOSITORY",""))
        parser.add_argument("--repository", default="TitoTB/Improved-Shopping-List")
        parser.add_argument("--platform", default="carrefour")
        parser.add_argument("--publish", action="store_true")

    def handle(self, *args, **options):
        with command_lock("aguacatec-shopping-feed.lock") as acquired:
            if not acquired:
                self.stdout.write("Ya hay una actualización del catálogo en curso.")
                return
            root = Path(options["integration_path"]).resolve()
            if not (root/"scripts/shopping_feed.py").is_file():
                raise CommandError("Configura SHOPPING_LIST_REPOSITORY con la copia de Improved Shopping List.")
            platform = DevicePlatform.objects.filter(key=options["platform"],awin_feed_id="84214").first()
            if not platform or not platform.awin_api_key or str(platform.awin_merchant_id or platform.awinmid) != "25399":
                raise CommandError("Configura Carrefour en Plataformas: anunciante 25399, feed 84214 y su clave privada de Awin.")
            sys.path.insert(0,str(root/"scripts"))
            from shopping_feed import build
            from publish_shopping_data import GitHubDataPublisher
            output = Path(settings.BASE_DIR)/"runtime/shopping_feed/carrefour"
            current = None
            if (output/"manifest.json").exists():
                current = json.loads((output/"manifest.json").read_bytes())
            upstream = source_version(platform)
            changed = not current or not upstream or current.get("source_updated_at") != upstream
            try:
                if changed:
                    current = build(download_feed(platform,force=True),output,upstream)
                state_file = output/"published-version.json"
                published = json.loads(state_file.read_bytes()) if state_file.exists() else {}
                if options["publish"] and (published.get("version"),published.get("source_updated_at")) != (current["version"],current["source_updated_at"]):
                    publisher = GitHubDataPublisher(options["repository"],os.environ.get("SHOPPING_DATA_GITHUB_TOKEN",""))
                    commit = publisher.publish(output)
                    state_file.write_text(json.dumps({"version":current["version"],"source_updated_at":current["source_updated_at"],"commit":commit}),encoding="utf-8")
                self.stdout.write(f"Carrefour: {current['products_count']} productos preparados. Publicación {'habilitada' if options['publish'] else 'desactivada'}.")
            except (ValueError, OSError, AwinFeedError, KeyError, EOFError, csv.Error):
                raise CommandError("No se pudo actualizar el catálogo. Se conserva la publicación anterior; revisa los registros privados sin compartir claves ni URLs de descarga.") from None
