"""Lidl Plus OAuth/PKCE and HTTP/1.1 receipts, with private durable renewal."""
import asyncio
import base64
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import math
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit, parse_qs, quote
import urllib.error
import urllib.request

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from .account_history import account_purchase_check, twelve_months_ago
from .catalog import CatalogError
from .const import DOMAIN
from .dia_account import DiaAccount
from .lidl_receipts import summary, ticket_id

CLIENT = "LidlPlusNativeClient"
REDIRECT = "com.lidlplus.app://callback"
HEADERS = {"App-Version":"15.30.0", "Operating-System":"iOs", "App":"com.lidl.eci.lidl.plus", "Accept-Language":"es"}


class LidlAccountError(CatalogError):
    def __init__(self, message, stage, **details):
        super().__init__(message, "lidl_account_error")
        self.diagnostics = {"stage":stage, **details}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, fields=None, token=None):
    """Only caller-constructed first-party endpoints; no redirects or body logging."""
    headers = {**HEADERS, "Accept":"application/json"}
    if fields is not None:
        headers.update({"Content-Type":"application/x-www-form-urlencoded",
            "Authorization":"Basic " + base64.b64encode((CLIENT+":secret").encode()).decode()})
    elif token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=urlencode(fields).encode() if fields is not None else None, headers=headers)
    stage = "token" if fields is not None else "ticket_detail" if "/tickets/" in url else "tickets"
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=25) as response:
            raw = response.read(2000001)
            if len(raw)>2000000:
                raise LidlAccountError("Lidl ha devuelto una respuesta demasiado grande.", stage)
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError
            return result
    except urllib.error.HTTPError as err:
        oauth = ""
        try:
            data = json.loads(err.read(8192)); value = data.get("error")
            if value in ("invalid_grant", "invalid_client", "invalid_request", "access_denied"):
                oauth = value
        except (ValueError, AttributeError):
            pass
        finally:
            err.close()
        raise LidlAccountError("Lidl ha rechazado la consulta. Vuelve a conectar si la sesión ha caducado.", stage,
            http_status=err.code, oauth_error=oauth) from None
    except (urllib.error.URLError, OSError, TimeoutError) as err:
        raise LidlAccountError("No se ha podido conectar con Lidl. Vuelve a intentarlo más tarde.", stage, response_class="network_error") from err
    except CatalogError:
        raise
    except (ValueError, UnicodeError) as err:
        raise LidlAccountError("Lidl ha devuelto una respuesta no reconocida.", stage, response_class="invalid_response") from err


class LidlAccount(DiaAccount):
    """Reuse account scheduling/lifecycle only; authentication and tickets are Lidl-specific."""
    def __init__(self, hass, receipts, activity):
        super().__init__(hass, receipts, activity)
        self._store = Store(hass, 1, f"{DOMAIN}.lidl_account", private=True)
        self._options_store = Store(hass, 1, f"{DOMAIN}.lidl_options", private=True)
        self._pending = {}
        self._options["ticket_scopes"] = []

    async def async_load(self):
        data = await self._store.async_load()
        if isinstance(data, dict):
            tokens = [data.get(key) for key in ("access_token", "refresh_token")]
            expires = data.get("expires_at")
            if (all(isinstance(v, str) and 1 <= len(v) <= 20000 for v in tokens)
                    and type(expires) in (int, float) and math.isfinite(expires)):
                self._session = {key:data[key] for key in ("access_token", "refresh_token", "expires_at")}
                self._session["email"] = ""
                refs = data.get("purchase_refs", {})
                self._session["purchase_refs"] = refs if isinstance(refs, dict) and len(refs) <= 1500 else {}
        options = await self._options_store.async_load()
        if isinstance(options, dict):
            for key in ("history_enabled", "auto_ticket"):
                if type(options.get(key)) is bool:
                    self._options[key] = options[key]
            for key in ("completion_at", "handled_completion"):
                value = options.get(key)
                if type(value) in (int, float) and math.isfinite(value) and 0 <= value < 1e12:
                    self._options[key] = value
            if isinstance(options.get("ticket_day"), str):
                self._options["ticket_day"] = options["ticket_day"][:10]
            if isinstance(options.get("ticket_scopes"), list):
                self._options["ticket_scopes"] = [v for v in options["ticket_scopes"] if isinstance(v, str) and len(v) <= 256][-100:]

    def status(self, owner):
        return {"connected":bool(self._session.get("refresh_token")), "email":self._session.get("email", ""),
            "options":{key:self._options[key] for key in ("history_enabled", "auto_ticket")}}

    def begin(self, owner):
        if not self._active:
            raise LidlAccountError("La integración no está activa.", "inactive")
        verifier, state = secrets.token_urlsafe(64), secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        self._pending = {key:value for key,value in self._pending.items() if value["until"] > time.time()}
        if len(self._pending)>20:
            raise LidlAccountError("Hay demasiadas conexiones pendientes. Espera unos minutos.", "authorization")
        self._pending[owner] = {"verifier":verifier, "state":state, "nonce":nonce, "until":time.time()+600}
        return {"authorization_url":"https://accounts.lidl.com/connect/authorize?"+urlencode({
            "client_id":CLIENT, "redirect_uri":REDIRECT, "response_type":"code",
            "scope":"openid profile offline_access lpprofile lpapis", "code_challenge_method":"S256",
            "code_challenge":base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).decode().rstrip("="),
            "state":state, "nonce":nonce, "Country":"ES", "language":"es-ES", "prompt":"login"})}

    async def _token(self, fields, generation):
        data = await self.hass.async_add_executor_job(request_json, "https://accounts.lidl.com/connect/token", fields)
        if not self._active or generation != self._generation:
            raise LidlAccountError("La conexión de Lidl ha cambiado.", "inactive")
        access, refresh = data.get("access_token"), data.get("refresh_token", self._session.get("refresh_token") if fields.get("grant_type") == "refresh_token" else None)
        expires = data.get("expires_in")
        if (not all(isinstance(v,str) and 1 <= len(v) <= 20000 for v in (access, refresh))
                or type(expires) not in (int,float) or not 60 <= expires <= 86400):
            raise LidlAccountError("Lidl no ha confirmado una sesión renovable.", "token_format")
        return {"access_token":access, "refresh_token":refresh, "expires_at":time.time()+expires}

    async def async_finish(self, owner, callback):
        pending = self._pending.get(owner)
        if not isinstance(callback,str) or len(callback)>20000:
            raise LidlAccountError("La dirección de retorno no es válida.", "authorization")
        parts = urlsplit(callback.strip()); query = parse_qs(parts.query)
        if (not pending or pending["until"] <= time.time() or parts.scheme != "com.lidlplus.app" or parts.netloc != "callback"
                or parts.path not in ("", "/") or parts.fragment or query.get("state") != [pending["state"]]
                or len(query.get("code",[])) != 1 or not 1 <= len(query["code"][0]) <= 4096):
            raise LidlAccountError("El retorno no corresponde a esta conexión o ha caducado. Inicia la conexión de nuevo.", "authorization")
        async with self._lock:
            if self._pending.get(owner) is not pending:
                raise LidlAccountError("La conexión pendiente ha cambiado.", "authorization")
            self._pending.pop(owner, None)
            generation = self._generation
            tokens = await self._token({"grant_type":"authorization_code", "code":query["code"][0],
                "redirect_uri":REDIRECT, "code_verifier":pending["verifier"]}, generation)
            session = {**tokens, "email":"", "purchase_refs":{}}
            await self._store.async_save(session); self._session = session
        if self._options["history_enabled"]:
            await self.async_sync_history(owner)
        return self.status(owner)

    async def _refresh(self):
        generation = self._generation
        try:
            tokens = await self._token({"grant_type":"refresh_token", "refresh_token":self._session["refresh_token"]}, generation)
        except LidlAccountError as err:
            if err.diagnostics.get("oauth_error") == "invalid_grant" and generation == self._generation:
                await self._store.async_save({}); self._session = {}
            raise
        session = {**self._session, **tokens}
        await self._store.async_save(session); self._session = session

    async def _request(self, path):
        if not self._active or not self._session.get("refresh_token"):
            raise LidlAccountError("Conecta tu cuenta de Lidl en Ajustes → Tiendas.", "not_connected")
        if self._session.get("expires_at", 0) <= time.time()+60:
            await self._refresh()
        generation = self._generation
        for retry in (False, True):
            try:
                result = await self.hass.async_add_executor_job(request_json, "https://tickets.lidlplus.com"+path, None, self._session["access_token"])
                if not self._active or generation != self._generation:
                    raise LidlAccountError("La conexión de Lidl ha cambiado.", "inactive")
                return result
            except LidlAccountError as err:
                if retry or err.diagnostics.get("http_status") != 401:
                    raise
                await self._refresh()

    async def async_disconnect(self, owner):
        self._pending.clear()
        return await super().async_disconnect(owner)

    async def async_stop(self):
        self._pending.clear()
        await super().async_stop()

    async def async_options(self, owner, options):
        if not isinstance(options,dict) or set(options)!={"history_enabled", "auto_ticket"} or any(type(v) is not bool for v in options.values()):
            raise LidlAccountError("Las opciones de Lidl no son válidas.", "options")
        if not self._session.get("refresh_token") and any(options.values()):
            raise LidlAccountError("Conecta primero tu cuenta de Lidl.", "not_connected")
        recover = options["history_enabled"] and not self._options["history_enabled"]
        self._options.update(options); await self._save_options()
        if recover:
            await self.async_sync_history(owner)
        self._queue_background()
        return self.status(owner)

    async def async_purchases(self, owner, cursor=None, *, import_summaries=None):
        page = cursor.get("page") if isinstance(cursor,dict) and set(cursor)=={"page"} else 1 if cursor is None else None
        if type(page) is not int or not 1 <= page <= 50:
            raise LidlAccountError("La página de compras de Lidl no es válida.", "pagination")
        async with self._lock:
            response = await self._request("/api/v2/ES/tickets?"+urlencode({"pageNumber":page, "onlyFavorite":"false"}))
            rows = response.get("tickets"); size = response.get("size", 25); total = response.get("totalCount")
            if (not isinstance(rows,list) or len(rows)>100 or type(size) is not int or not 1 <= size <= 100
                    or type(total) is not int or not 0 <= total <= 100000):
                raise LidlAccountError("Lidl no ha devuelto un historial reconocido.", "history_format")
            output, summaries = [], []; refs = deepcopy(self._session.get("purchase_refs", {})); now = dt_util.utcnow()
            for raw in rows:
                purchase = summary(raw); when = dt_util.parse_datetime(purchase["purchased_at"])
                if not twelve_months_ago(now) <= when <= now+timedelta(days=1) or not purchase["supported"]:
                    continue
                key = self.receipts._account_key(purchase["reference"], "lidl"); refs[key] = purchase
                summaries.append({"purchaseId":purchase["reference"], "purchaseDate":purchase["purchased_at"], "amount":purchase["amount"], "ticket_available":True})
                output.append({"id":key, "purchased_at":purchase["purchased_at"], "amount":purchase["amount"], "store":"Lidl", "reviewable":True, "kind":"Ticket"})
            session = {**self._session, "purchase_refs":dict(list(refs.items())[-1500:])}
            await self._store.async_save(session); self._session = session
            added = await self.receipts.async_import_account_purchases(summaries, "lidl") if (self._options["history_enabled"] if import_summaries is None else import_summaries) else 0
            return {"purchases":output, "added":added, "next_cursor":{"page":page+1} if rows and page*size < total and page<50 else None}

    async def async_sync_history(self, owner):
        if self._sync_lock.locked():
            raise LidlAccountError("Ya se está incorporando el historial de Lidl.", "history_sync")
        async with self._sync_lock:
            cursor = None; added = available = 0
            for _ in range(50):
                result = await self.async_purchases(owner, cursor, import_summaries=True)
                added += result["added"]; available += len(result["purchases"]); cursor = result["next_cursor"]
                if cursor is None:
                    return {"added":added, "available":available, "complete":True}
                await asyncio.sleep(1)
            return {"added":added, "available":available, "complete":False}

    async def async_preview_saved(self, owner, receipt_id):
        saved = self.receipts.stock.receipts["history"].get(receipt_id)
        if not saved or saved.get("store") != "lidl" or not saved.get("summary_only") or not saved.get("account_key"):
            raise LidlAccountError("Esta compra no tiene un ticket pendiente de Lidl.", "saved_purchase")
        if saved["account_key"] not in self._session.get("purchase_refs", {}):
            await self.async_sync_history(owner)
        return await self.async_preview(owner, saved["account_key"])

    async def async_preview(self, owner, purchase_id):
        async with self._lock:
            purchase = self._session.get("purchase_refs", {}).get(purchase_id)
            if not purchase or self.receipts._account_key(purchase["reference"], "lidl") != purchase_id:
                raise LidlAccountError("Vuelve a consultar las compras de Lidl antes de abrir este ticket.", "purchase_unavailable")
            detail = await self._request("/api/v3/ES/tickets/"+quote(ticket_id(purchase["reference"]), safe=""))
            return await self.receipts.async_preview_lidl_ticket(detail, purchase["reference"], purchase["amount"], purchase["purchased_at"], owner)

    async def async_reprocess_receipt(self, saved):
        """Read one original ticket to recover explicit fields absent in older imports."""
        reference=ticket_id(saved.get("identity",""))
        if saved.get("store")!="lidl" or saved.get("account_key")!=self.receipts._account_key(reference,"lidl"):
            raise LidlAccountError("La referencia del ticket guardado no es válida.","saved_purchase")
        async with self._lock:
            detail=await self._request("/api/v3/ES/tickets/"+quote(reference,safe=""))
        from .lidl_receipts import extract_lidl_ticket
        return await self.hass.async_add_executor_job(extract_lidl_ticket,detail,reference,saved["total"],saved["purchased_at"])

    def _queue_background(self, *_args):
        if self._active and self._options["auto_ticket"] and (self._task is None or self._task.done()):
            self._task = self.hass.async_create_background_task(self._run_background(), "Lidl automatic tickets")

    def automatic_due(self, now, detected_today):
        detection = getattr(self, "purchase_detection", None)
        if detection and detection.enabled and "shops" in detection.zone_config:
            return bool(self._active and self._session.get("refresh_token") and self._options["auto_ticket"] and
                set(detection.ticket_scope("lidl")) - set(self._options["ticket_scopes"]))
        return super().automatic_due(now, detected_today)

    async def async_automatic_ticket(self, now, detected_today):
        if not self.automatic_due(now, detected_today):
            return
        detection = getattr(self, "purchase_detection", None)
        if detection and "shops" in detection.zone_config:
            day = now.date().isoformat()
            self._options["ticket_scopes"] = list(dict.fromkeys([v for v in self._options["ticket_scopes"] if day in v] + detection.ticket_scope("lidl")))
        self._options["ticket_day"] = now.date().isoformat(); await self._save_options()
        try:
            owner = "automatic_lidl"
            async with account_purchase_check(
                lambda cursor: self.async_purchases(owner, cursor, import_summaries=True),
                pagination_error=lambda: LidlAccountError("Lidl ha repetido una página del historial. Las compras ya incorporadas se conservan.", "history_pagination"),
                page_limit=50,
            ) as result:
                candidates = [p for p in result["purchases"] if dt_util.as_local(dt_util.parse_datetime(p["purchased_at"])).date() == now.date()]
                if not (detection and "shops" in detection.zone_config):
                    candidates = sorted(candidates, key=lambda p:p["purchased_at"], reverse=True)[:1]
                for latest in candidates:
                    if not self._active or not self._options["auto_ticket"]:
                        break
                    ref = self._session["purchase_refs"][latest["id"]]["reference"]
                    if not self.receipts.account_ticket_available(ref, "lidl"):
                        draft = await self.async_preview(owner, latest["id"])
                        if self._active and self._options["auto_ticket"]:
                            await self.receipts.async_archive_account_ticket(draft["token"], owner)
                        else:
                            self.receipts.discard(draft["token"], owner)
                    self.activity.record("stores.account", "Lidl: última compra disponible para revisar", source="automatic")
                self._options["handled_completion"] = self._options["completion_at"]
                return bool(candidates)
        finally:
            await self._save_options()
