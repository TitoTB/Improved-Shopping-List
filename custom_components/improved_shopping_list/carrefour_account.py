"""Carrefour sessions and optional locally remembered credentials."""

import asyncio
import base64
from datetime import timedelta
from hashlib import sha256
import json
import math
import re
import time
from uuid import uuid4

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .account_history import account_purchase_check
from .catalog import CatalogError
from .const import DOMAIN
from .receipt_parser import MAX_PDF_BYTES

WEB = "https://www.carrefour.es"
API = "https://pro.api.carrefour.es"
IDENTITY = "https://ss-mya-p3.carrefour.es"
# Persistent session: -1 requires a dynamic expiry cookie and otherwise lasts 60s.
# SAP CDC may still revoke or shorten the session according to provider policy.
SESSION_EXPIRATION = "-2"
OFFSET_KEYS = ("atgfOffset", "atgnfOffset", "currentAtgfOrders", "currentAtgnfOrders", "currentTickets", "ticketOffset")


class CarrefourAccountError(CatalogError):
    def __init__(self, message, stage, *, status=None, error_code=None):
        super().__init__(message, "carrefour_account_error")
        self.diagnostics = {"stage": stage}
        if status is not None:
            self.diagnostics["http_status"] = status
        if isinstance(error_code, int):
            self.diagnostics["provider_error_code"] = error_code


class CarrefourAccount:
    def __init__(self, hass, receipts, activity):
        self.hass, self.receipts, self.activity = hass, receipts, activity
        self._store = Store(hass, 1, f"{DOMAIN}.carrefour_account", private=True)
        self._session, self._config, self._pending, self._purchases = {}, {}, {}, {}
        self._credentials_store = Store(hass, 1, f"{DOMAIN}.carrefour_credentials", private=True)
        self._credentials = {}
        self._options_store = Store(hass, 1, f"{DOMAIN}.carrefour_options", private=True)
        self._options = {"history_enabled":False,"auto_ticket":False,"completion_at":0,"handled_completion":0,"ticket_day":"","ticket_scopes":[]}
        self._background_task, self._timer_stop = None, None
        self._options_lock = asyncio.Lock()
        self._saved_options = None
        self._cookies = {}
        self._lock = asyncio.Lock()
        self._sync_lock = asyncio.Lock()
        self._active = False
        self._restored_session = False

    async def async_load(self):
        credentials = await self._credentials_store.async_load()
        if (isinstance(credentials, dict) and all(isinstance(credentials.get(key), str)
                and 0 < len(credentials[key]) <= 255 for key in ("username", "password"))):
            self._credentials = {key: credentials[key] for key in ("username", "password")}
        options = await self._options_store.async_load()
        if isinstance(options,dict):
            self._options.update({key:value for key,value in options.items() if key in self._options})
        data = await self._store.async_load()
        if data and isinstance(data, dict) and isinstance(data.get("login_token"), str):
            self._session = {key: data[key] for key in ("login_token", "jwt", "jwt_until", "device_cookies", "email", "purchase_refs") if key in data}
            self._restored_session = bool(self._session.get("login_token"))

    def start(self):
        self._active = True
        if not self._timer_stop:
            self._timer_stop = async_track_time_interval(self.hass,self._queue_background,timedelta(minutes=1))
        self._cookies = dict(self._session.get("device_cookies", {}))

    def stop(self):
        self._active = False
        if self._timer_stop:
            self._timer_stop();self._timer_stop=None
        if self._background_task:
            self._background_task.cancel()
        self._pending.clear()
        self._purchases.clear()
        self._config.clear()
        self._cookies.clear()

    def status(self, owner):
        pending = self._pending.get(owner, {})
        return {"connected": bool(self._session.get("login_token")), "email":self._email(),
                "credentials_saved":bool(self._credentials), "remembered_email":self._credentials.get("username",""),
                "options":{key:self._options[key] for key in ("history_enabled","auto_ticket")},
                "verification_required": pending.get("expires", 0) > time.time(),
                "destinations": [{"id": str(i), "label": item["label"]} for i, item in enumerate(pending.get("destinations", []))]
                    if pending.get("expires", 0) > time.time() else [],
                "verification_sent": bool(pending.get("phvToken")) and pending.get("expires", 0) > time.time()}

    def _email(self):
        value = self._session.get("email", "")
        if not value and self._session.get("jwt"):
            try:
                payload = self._session["jwt"].split(".")[1]
                claims = json.loads(base64.urlsafe_b64decode(payload+"="*(-len(payload)%4)))
                value = claims.get("email") or claims.get("profile.email") or claims.get("profile",{}).get("email","")
            except (ValueError,IndexError,AttributeError,TypeError):
                value = ""
        return value if isinstance(value,str) and len(value)<=255 else ""

    async def _save_options(self):
        async with self._options_lock:
            payload=dict(self._options)
            if payload!=self._saved_options:
                await self._options_store.async_save(payload)
                self._saved_options=payload

    async def async_options(self, owner, options):
        if (not isinstance(options,dict) or set(options)-{"public_prices"}!={"history_enabled","auto_ticket"}
                or any(type(value) is not bool for value in options.values())):
            raise CarrefourAccountError("Las opciones de Carrefour no son válidas.","options")
        if not self._session.get("login_token") and (options["history_enabled"] or options["auto_ticket"]):
            raise CarrefourAccountError("Conecta primero tu cuenta de Carrefour.","not_connected")
        options={key:options[key] for key in ("history_enabled","auto_ticket")}
        recover = options["history_enabled"] and not self._options["history_enabled"]
        self._options.update(options)
        await self._save_options()
        if recover:
            await self.async_sync_history(owner)
        self._queue_background()
        return self.status(owner)

    def note_completion(self):
        if not self._active or not self._options["auto_ticket"] or not self._session.get("login_token"):
            return
        self._options["completion_at"] = time.time()
        self._queue_background()

    def _queue_background(self, *_args):
        if self._active and self._options["auto_ticket"] and (self._background_task is None or self._background_task.done()):
            self._background_task = self.hass.async_create_task(self._run_background())

    async def _run_background(self):
        if getattr(self,"ticket_accounts",None):
            await self.ticket_accounts.async_check()
            return
        try:
            await self._save_options()
            settings = getattr(self,"settings",None)
            if settings is None:
                return
            now = dt_util.now();day=now.date().isoformat()
            detection = getattr(self,"purchase_detection",None)
            detected_today = bool(detection and detection.pending_for_today)
            if not detected_today and now.strftime("%H:%M") < settings.snapshot["price_update_time"]:
                return
            completion = self._options["completion_at"]
            if (not self._session.get("login_token") or not self._options["auto_ticket"] or self._options["ticket_day"]==day
                    or completion<=self._options["handled_completion"]):
                return
            self._options["ticket_day"]=day;await self._save_options()
            owner="automatic_carrefour"
            try:
                if detection and getattr(detection,"enabled",False):
                    await detection.async_search_ticket_sources({"carrefour":lambda:self._download_automatic_ticket(owner,now,detected_today)})
                else:
                    await self._download_automatic_ticket(owner,now,detected_today)
                self._options["handled_completion"]=completion;await self._save_options()
            except CatalogError as err:
                self.activity.record("stores.account","Carrefour: no se ha podido recuperar automáticamente el ticket",source="automatic",diagnostics=getattr(err,"diagnostics",{"stage":"ticket_preview"}))
        except asyncio.CancelledError:
            raise
        except (OSError,aiohttp.ClientError,TimeoutError):
            self.activity.record("stores.account","Carrefour: no se ha podido guardar la revisión automática",source="automatic")

    def automatic_due(self,now,detected_today):
        detection=getattr(self,'purchase_detection',None)
        if detection and getattr(detection,'enabled',False) and 'shops' in getattr(detection,'zone_config',{}):
            return bool(self._active and self._session.get('login_token') and self._options['auto_ticket'] and
                set(detection.ticket_scope('carrefour'))-set(self._options['ticket_scopes']))
        return bool(self._active and self._session.get("login_token") and self._options["auto_ticket"] and
            self._options["ticket_day"]!=now.date().isoformat() and self._options["completion_at"]>self._options["handled_completion"] and
            (detected_today or now.strftime("%H:%M")>=self.settings.snapshot["price_update_time"]))

    async def async_automatic_ticket(self,now,detected_today):
        if not self.automatic_due(now,detected_today):return False
        detection=getattr(self,'purchase_detection',None)
        if detection and 'shops' in getattr(detection,'zone_config',{}):
            day=now.date().isoformat()
            self._options['ticket_scopes']=list(dict.fromkeys([scope for scope in self._options['ticket_scopes'] if day in scope]+detection.ticket_scope('carrefour')))
        self._options["ticket_day"]=now.date().isoformat();await self._save_options()
        try:
            found=await self._download_automatic_ticket("automatic_carrefour",now,detected_today)
            self._options["handled_completion"]=self._options["completion_at"]
            return found
        finally:
            await self._save_options()

    async def _download_automatic_ticket(self, owner, now, detected_today):
        async with account_purchase_check(
            lambda cursor: self.async_purchases(owner, cursor, import_summaries=True),
            pagination_error=lambda: CarrefourAccountError("Carrefour ha repetido una página del historial. Las compras ya incorporadas se conservan.", "history_pagination"),
        ) as result:
            candidates = result["purchases"]
            detection=getattr(self,'purchase_detection',None)
            if detection and getattr(detection,'enabled',False) and 'shops' in getattr(detection,'zone_config',{}):
                found=False
                for purchase in candidates[:100]:
                    date=dt_util.parse_datetime(purchase['purchased_at'])
                    if not date or dt_util.as_local(date if date.tzinfo else date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)).date()!=now.date() or not purchase['reviewable']:continue
                    cached=self._purchases[purchase['id']]
                    if not self.receipts.account_ticket_available(cached['id']):
                        draft=await self.async_preview(owner,purchase['id'])
                        if self._active and self._options['auto_ticket']:await self.receipts.async_archive_account_ticket(draft['token'],owner)
                        else:self.receipts.discard(draft['token'],owner)
                    found=True
                return found
            if detected_today:
                def same_day(purchase):
                    date = dt_util.parse_datetime(purchase["purchased_at"])
                    return bool(date and dt_util.as_local(date if date.tzinfo else date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)).date() == now.date())
                candidates = [purchase for purchase in candidates if same_day(purchase)]
            latest=max(candidates,key=lambda purchase:purchase["purchased_at"],default=None)
            if latest and latest["reviewable"]:
                cached=self._purchases[latest["id"]]
                if not self.receipts.account_ticket_available(cached["id"]):
                    draft=await self.async_preview(owner,latest["id"])
                    if self._active and self._options["auto_ticket"]:
                        await self.receipts.async_archive_account_ticket(draft["token"],owner)
                    else:
                        self.receipts.discard(draft["token"],owner)
                self.activity.record("stores.account","Carrefour: última compra disponible para revisar",source="automatic")
            elif latest:
                self.activity.record("stores.account","Carrefour: la factura online debe subirse manualmente",source="automatic")
            date=dt_util.parse_datetime(latest["purchased_at"]) if latest else None
            return bool(latest and latest["reviewable"] and date and dt_util.as_local(date if date.tzinfo else date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)).date()==now.date())

    async def async_stop(self):
        task=self._background_task
        self.stop()
        if task:
            await asyncio.gather(task,return_exceptions=True)

    def _check_active(self):
        if not self._active:
            raise CarrefourAccountError("La integración ya no está activa.", "inactive")

    async def _http(self, method, url, *, data=None, params=None, headers=None, pdf=False, text=False):
        self._check_active()
        stage = url.split("/", 3)[-1]
        stage = re.sub(r"tickets/[^/]+", "tickets/{id}", stage)
        limit = MAX_PDF_BYTES if pdf else 2 * 1024 * 1024
        try:
            async with async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar()) as session:
                async with session.request(method, url, data=data, params=params, headers={
                    "Accept": "application/json", "Origin": WEB, "Referer": WEB + "/myaccount/", **(headers or {})},
                    timeout=aiohttp.ClientTimeout(total=25), allow_redirects=False) as response:
                    if response.status != 200:
                        message = "Carrefour ha rechazado el acceso" if response.status in (401, 403) else "Carrefour no ha podido completar la consulta"
                        raise CarrefourAccountError(f"{message} (HTTP {response.status}).", stage, status=response.status)
                    content = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        content.extend(chunk)
                        if len(content) > limit:
                            raise CarrefourAccountError("La respuesta de Carrefour supera el tamaño permitido.", stage)
                    if url.startswith(IDENTITY + "/"):
                        for name in ("gmid", "ucid", "hasGmid"):
                            cookie = response.cookies.get(name)
                            if cookie and 0 < len(cookie.value) <= 4096 and not any(c in cookie.value for c in "\r\n;"):
                                self._cookies[name] = cookie.value
            self._check_active()
            if url.startswith(IDENTITY + "/"):
                await self._persist_device_cookies()
            if pdf:
                if not content.startswith(b"%PDF-"):
                    raise CarrefourAccountError("Carrefour no ha devuelto un ticket PDF válido.", stage)
                return bytes(content)
            if text:
                return content.decode("utf-8")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError
            return result
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CarrefourAccountError("No se ha podido conectar con Carrefour. Vuelve a intentarlo manualmente.", stage) from err
        except CarrefourAccountError:
            raise
        except (ValueError, UnicodeError) as err:
            raise CarrefourAccountError("Carrefour ha devuelto una respuesta no reconocida.", stage) from err

    async def _persist_device_cookies(self):
        """Keep rotated device cookies alongside the durable login token."""
        if self._session.get("login_token") and self._session.get("device_cookies") != self._cookies:
            session = {**self._session, "device_cookies":dict(self._cookies)}
            await self._store.async_save(session)
            self._session = session

    async def _public_config(self):
        if not self._config:
            source = await self._http("GET", WEB + "/access/resources/config.js", text=True)
            def read_object(name):
                match = re.search(r"var\s+" + name + r"\s*=\s*\{(.*?)\};", source, re.S)
                return dict(re.findall(r"(\w+)\s*:\s*['\"]([^'\"]+)['\"]", match[1])) if match else {}
            apis, headers = read_object("c4apis"), read_object("c4Headers")
            if not apis.get("val") or not headers.get("clientMD") or not headers.get("secretMD"):
                raise CarrefourAccountError("Ha cambiado la configuración pública de acceso a Carrefour.", "public_config")
            self._config = {"api_key": apis["val"], "client_id": headers["clientMD"], "client_secret": headers["secretMD"]}
        return self._config

    async def _identity(self, method, fields, *, allow_tfa=False):
        config = await self._public_config()
        if not self._cookies.get("gmid"):
            bootstrap = await self._http("POST", IDENTITY + "/accounts.webSdkBootstrap",
                data={"apiKey": config["api_key"], "format": "json"})
            if bootstrap.get("errorCode") != 0 or not self._cookies.get("gmid"):
                raise CarrefourAccountError("No se ha podido inicializar el dispositivo de acceso a Carrefour.", "device_bootstrap")
        response = await self._http("POST", IDENTITY + "/" + method,
            headers={"Cookie": "; ".join(name + "=" + value for name, value in self._cookies.items())},
            data={"APIKey": config["api_key"], "format": "json", "lang": "es", "targetEnv": "jssdk", "authMode": "cookie", **fields})
        error = response.get("errorCode")
        if error != 0 and not (allow_tfa and error == 403101):
            if error == 403042:
                message = "El usuario o la contraseña de Carrefour no son correctos."
            elif error in (401020, 401021, 400021, 403120):
                message = "Carrefour requiere una comprobación en su web o ha limitado los intentos. No se reintentará automáticamente."
            elif error in (403005, 403006):
                message = "La sesión de Carrefour ha caducado. Vuelve a conectar la cuenta."
            else:
                message = "Carrefour no ha aceptado esta operación de acceso o verificación."
            raise CarrefourAccountError(message, method, error_code=error)
        return response

    async def _save_session(self, response, credentials=None):
        token = response.get("sessionInfo", {}).get("login_token")
        if not isinstance(token, str) or not token:
            raise CarrefourAccountError("Carrefour no ha devuelto una sesión utilizable.", "session")
        session = {"login_token": token, "device_cookies": dict(self._cookies)}
        email=response.get("profile",{}).get("email") or getattr(self,"_login_email","")
        if isinstance(email,str) and len(email)<=255:
            session["email"]=email
        self._check_active()
        await self._store.async_save(session)
        self._session = session
        self._restored_session = False
        if credentials is not None:
            await self._credentials_store.async_save(credentials)
            self._credentials = credentials
        self._purchases.clear()
        self._pending.clear()

    async def async_login(self, owner, username, password, remember_credentials=False):
        async with self._lock:
            username = username.strip()
            if remember_credentials and not password and username == self._credentials.get("username"):
                password = self._credentials.get("password", "")
            credentials = {"username": username, "password": password} if remember_credentials else {}
            if not username or not password:
                raise CarrefourAccountError("Indica correo y contraseña de Carrefour.", "login")
            self._pending.pop(owner, None)
            self._login_email = username.strip()
            response = await self._identity("accounts.login", {"loginID": username.strip(), "password": password,
                "targetEnv": "jssdk", "authMode": "cookie", "loginMode": "standard", "sessionExpiration": SESSION_EXPIRATION,
                "include": "profile,data"}, allow_tfa=True)
            if response.get("errorCode") == 403101:
                reg = response.get("regToken")
                if not isinstance(reg, str) or not reg:
                    raise CarrefourAccountError("Carrefour solicita una verificación que no se ha podido iniciar.", "tfa")
                providers = await self._identity("accounts.tfa.getProviders", {"regToken": reg})
                active = {p.get("name") for p in providers.get("activeProviders", []) if isinstance(p, dict)}
                provider = next((p for p in ("gigyaEmail", "gigyaPhone") if p in active), None)
                if not provider:
                    raise CarrefourAccountError("El método de verificación de esta cuenta todavía no está disponible en la integración.", "tfa_provider")
                init = await self._identity("accounts.tfa.initTFA", {"regToken": reg, "provider": provider, "mode": "verify"})
                assertion = init.get("gigyaAssertion")
                kind = "email" if provider == "gigyaEmail" else "phone"
                targets = await self._identity("accounts.tfa." + kind + (".getEmails" if kind == "email" else ".getRegisteredPhoneNumbers"), {"gigyaAssertion": assertion})
                destinations = [{"id": p["id"], "label": p.get("obfuscated") or ("Correo verificado" if kind == "email" else "Teléfono verificado")}
                    for p in targets.get("emails" if kind == "email" else "phones", []) if isinstance(p, dict) and p.get("id")]
                if not assertion or not destinations:
                    raise CarrefourAccountError("No se ha encontrado un destino verificado para enviar el código.", "tfa_destination")
                self._pending[owner] = {"regToken": reg, "gigyaAssertion": assertion, "kind": kind,
                    "destinations": destinations, "expires": time.time() + 600, "email":username.strip(), "credentials":credentials}
            else:
                await self._save_session(response, credentials)
            return self.status(owner)

    def _challenge(self, owner):
        pending = self._pending.get(owner)
        if not pending or pending["expires"] <= time.time():
            self._pending.pop(owner, None)
            raise CarrefourAccountError("La verificación ha caducado. Vuelve a conectar la cuenta.", "tfa_expired")
        return pending

    async def async_send_code(self, owner, destination):
        async with self._lock:
            pending = self._challenge(owner)
            if pending.get("sent_at", 0) > time.time() - 60:
                raise CarrefourAccountError("Espera un minuto antes de solicitar otro código.", "tfa_rate_limit")
            try:
                target = pending["destinations"][int(destination)]
                if str(int(destination)) != destination or int(destination) < 0:
                    raise ValueError
            except (ValueError, IndexError):
                raise CarrefourAccountError("Selecciona un destino de verificación.", "tfa_destination") from None
            kind = pending["kind"]
            result = await self._identity("accounts.tfa." + kind + ".sendVerificationCode", {
                "gigyaAssertion": pending["gigyaAssertion"], "emailID" if kind == "email" else "phoneID": target["id"],
                **({"method": "sms"} if kind == "phone" else {})})
            if not result.get("phvToken"):
                raise CarrefourAccountError("Carrefour no ha confirmado el envío del código.", "tfa_send")
            pending.update(phvToken=result["phvToken"], sent_at=time.time())
            return self.status(owner)

    async def async_verify(self, owner, code):
        async with self._lock:
            pending = self._challenge(owner)
            if not re.fullmatch(r"\d{4,10}", code) or not pending.get("phvToken"):
                raise CarrefourAccountError("Solicita e introduce el código de verificación.", "tfa_code")
            result = await self._identity("accounts.tfa." + pending["kind"] + ".completeVerification", {
                "gigyaAssertion": pending["gigyaAssertion"], "phvToken": pending["phvToken"], "code": code})
            if not result.get("providerAssertion"):
                raise CarrefourAccountError("No se ha podido confirmar el código.", "tfa_code")
            await self._identity("accounts.tfa.finalizeTFA", {"regToken": pending["regToken"],
                "gigyaAssertion": pending["gigyaAssertion"], "providerAssertion": result["providerAssertion"], "tempDevice": "true"})
            response = await self._identity("accounts.finalizeRegistration", {"regToken": pending["regToken"],
                "sessionExpiration": SESSION_EXPIRATION, "include": "profile,data"})
            self._login_email = pending.get("email","")
            await self._save_session(response, pending.get("credentials"))
            return self.status(owner)

    async def async_disconnect(self, owner):
        self._options.update(history_enabled=False,auto_ticket=False)
        await self._save_options()
        async with self._lock:
            await self._store.async_save({})
            self._session.clear()
            self._cookies.clear()
            self._pending.clear()
            self._purchases.clear()
            return self.status(owner)

    async def _headers(self):
        if not self._session.get("login_token"):
            raise CarrefourAccountError("Conecta primero tu cuenta de Carrefour.", "not_connected")
        config = await self._public_config()
        if not self._session.get("jwt") or not isinstance(self._session.get("jwt_until"), (int, float)) or self._session["jwt_until"] <= time.time():
            try:
                result = await self._identity("accounts.getJWT", {"login_token": self._session["login_token"],
                    "expiration": "1800", "fields": "data.GR,profile.email,data.DQ,data.acceptedCustomerPolicies,data.ID_ATG"})
            except CarrefourAccountError as err:
                if err.diagnostics.get("provider_error_code") in (403005, 403006):
                    self.activity.record("stores.account", "Carrefour: el proveedor ha invalidado la sesión guardada. Es necesario volver a conectar la cuenta.",
                        source="integration", diagnostics={**err.diagnostics, "restored_after_restart":self._restored_session})
                    await self._store.async_save({})
                    self._session.clear()
                    self._purchases.clear()
                raise
            token = result.get("id_token")
            if not isinstance(token, str) or not token or len(token) > 16384 or any(c in token for c in "\r\n;"):
                raise CarrefourAccountError("Carrefour no ha devuelto una autorización válida.", "jwt")
            self._session.update(jwt=token, jwt_until=time.time()+1700)
            await self._store.async_save(self._session)
        token = self._session["jwt"]
        return {"Authorization": "Bearer " + token, "Cookie": "C4SSO_session=" + token,
            "x-ibm-client-id": config["client_id"], "x-ibm-client-secret": config["client_secret"], "requestOrigin": "MYA"}

    async def async_purchases(self, owner, cursor=None, *, import_summaries=None):
        async with self._lock:
            if cursor is not None and (not isinstance(cursor, dict) or set(cursor) != set(OFFSET_KEYS) or
                    any(type(v) is not int or not 0 <= v <= 100000 for v in cursor.values())):
                raise CarrefourAccountError("La página de compras no es válida.", "pagination")
            now = dt_util.utcnow()
            params = {"from": (now-timedelta(days=365)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                      "to": (now+timedelta(days=1)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                      "count": 10, **(cursor or dict.fromkeys(OFFSET_KEYS, 0))}
            response = await self._http("GET", API + "/md-purchasesAccount-v1/purchases", params=params, headers=await self._headers())
            purchases = response.get("purchases")
            if not isinstance(purchases, list) or len(purchases) > 100:
                raise CarrefourAccountError("Carrefour no ha devuelto un listado de compras válido.", "purchases")
            self._purchases = {key: value for key, value in self._purchases.items() if value["expires"] > time.time()}
            if len(self._purchases) > 500:
                self._purchases.clear()
            output, summaries = [], []
            for purchase in purchases:
                if not isinstance(purchase, dict):
                    continue
                identifier, amount, at = purchase.get("purchaseId"), purchase.get("amount"), purchase.get("purchaseDate")
                if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", identifier):
                    continue
                if type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0 or not isinstance(at, str) or not dt_util.parse_datetime(at):
                    continue
                at_date = dt_util.parse_datetime(at)
                at_utc = dt_util.as_utc(at_date if at_date.tzinfo else at_date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE))
                if not now-timedelta(days=365) <= at_utc <= now+timedelta(days=1):
                    continue
                supported = purchase.get("orderSource") == "TICKET"
                summaries.append({"purchaseId":identifier,"purchaseDate":at,"amount":amount,"ticket_available":supported})
                references = self._session.setdefault("purchase_refs", {})
                references[sha256(("carrefour:"+identifier).encode()).hexdigest()] = {"id":identifier,"amount":amount,"supported":supported}
                key = str(uuid4())
                supported = purchase.get("orderSource") == "TICKET"
                self._purchases[key] = {"id": identifier, "owner": owner, "expires": time.time()+1800, "supported": supported, "amount": amount}
                output.append({"id": key, "purchased_at": at, "amount": amount,
                    "store": str(purchase.get("mallName", "Carrefour"))[:150], "reviewable": supported,
                    "kind": "Ticket" if supported else "Pedido online · factura pendiente de soporte"})
            self._session["purchase_refs"] = dict(list(self._session.get("purchase_refs", {}).items())[-1000:])
            await self._store.async_save(self._session)
            added = await self.receipts.async_import_carrefour_purchases(summaries) if (self._options["history_enabled"] if import_summaries is None else import_summaries) else 0
            offsets = response.get("offsets", {})
            next_cursor = {key: offsets.get(key, 0) for key in OFFSET_KEYS}
            if not purchases or next_cursor == (cursor or dict.fromkeys(OFFSET_KEYS, 0)) or any(type(v) is not int or not 0 <= v <= 100000 for v in next_cursor.values()):
                next_cursor = None
            return {"purchases": output, "next_cursor": next_cursor, "added":added}

    async def async_sync_history(self, owner):
        """Manual one-year import of summaries only; never download tickets."""
        if self._sync_lock.locked():
            raise CarrefourAccountError("Ya se está incorporando el historial de Carrefour.", "history_sync")
        async with self._sync_lock:
            cursor, added, available, seen = None, 0, 0, set()
            for _ in range(100):
                result = await self.async_purchases(owner,cursor,import_summaries=True)
                added += result["added"]
                available += len(result["purchases"])
                cursor = result["next_cursor"]
                if cursor is None:
                    return {"added":added,"available":available,"complete":True}
                marker = tuple(cursor[key] for key in OFFSET_KEYS)
                if marker in seen:
                    raise CarrefourAccountError("Carrefour ha repetido una página del historial. Las compras ya incorporadas se conservan.", "history_pagination")
                seen.add(marker)
                await asyncio.sleep(1)
            return {"added":added,"available":available,"complete":False}

    async def async_preview_saved(self, owner, receipt_id):
        """Resolve a locally imported purchase without exposing provider identifiers."""
        saved = self.receipts.stock.receipts["history"].get(receipt_id)
        if not saved or saved.get("store") != "carrefour" or not saved.get("summary_only") or not saved.get("account_key"):
            raise CarrefourAccountError("Esta compra no tiene un ticket pendiente de Carrefour.", "saved_purchase")
        if not self._session.get("login_token"):
            raise CarrefourAccountError("Conecta tu cuenta de Carrefour en Ajustes → Tiendas.", "not_connected")
        def reference():
            refs = self._session.get("purchase_refs", {})
            item = refs.get(saved["account_key"]) if isinstance(refs, dict) else None
            if not isinstance(item, dict):
                return None
            identifier = item.get("id")
            if (not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", identifier)
                    or sha256(("carrefour:"+identifier).encode()).hexdigest() != saved["account_key"]
                    or type(item.get("supported")) is not bool or item.get("amount") != saved["total"]):
                return None
            return item
        purchase = reference()
        cursor, seen = None, set()
        for _ in range(100):
            if purchase:
                break
            result = await self.async_purchases(owner, cursor, import_summaries=False)
            purchase = reference()
            cursor = result["next_cursor"]
            if purchase or cursor is None:
                break
            marker = tuple(cursor[key] for key in OFFSET_KEYS)
            if marker in seen:
                break
            seen.add(marker)
            await asyncio.sleep(1)
        if not purchase:
            raise CarrefourAccountError("Carrefour ya no ofrece esta compra en el historial de la cuenta conectada.", "purchase_unavailable")
        key = str(uuid4())
        self._purchases[key] = {**purchase, "owner":owner, "expires":time.time()+1800}
        try:
            return await self.async_preview(owner, key)
        finally:
            self._purchases.pop(key, None)

    async def async_preview(self, owner, purchase_id):
        async with self._lock:
            purchase = self._purchases.get(purchase_id)
            if not purchase or purchase["owner"] != owner or purchase["expires"] <= time.time():
                raise CarrefourAccountError("Vuelve a consultar las compras antes de abrir este ticket.", "purchase_expired")
            if not purchase["supported"]:
                raise CarrefourAccountError("Las facturas online todavía deben subirse manualmente.", "invoice_unsupported")
            headers = await self._headers()
            endpoint = API + "/md-ticketsAccount-v1/tickets/" + purchase["id"]
            fallback = {}
            try:
                detail = await self._http("GET", endpoint, headers=headers)
            except CarrefourAccountError as err:
                status = err.diagnostics.get("http_status")
                if not isinstance(status, int) or not 500 <= status <= 599:
                    raise
                fallback = {"detail_http_status":status}
            else:
                try:
                    return await self.receipts.async_preview_carrefour_ticket(detail, purchase["id"], purchase["amount"], owner)
                except CatalogError as err:
                    # Only unsupported structure: totals, identity and duplicates stay errors.
                    if err.code not in ("receipt_unrecognized_lines", "receipt_detail_format"):
                        raise
                    fallback = {"detail_format_error":err.code,
                        "detail_items_count":len(detail["items"]) if isinstance(detail.get("items"), list) else None,
                        "detail_lines_count":len(detail["lines"]) if isinstance(detail.get("lines"), list) else None}
            try:
                pdf = await self._http("GET", endpoint + "/pdf", headers=headers, pdf=True)
                draft = await self.receipts.async_preview(base64.b64encode(pdf).decode(), owner, account_reference=purchase["id"])
            except CatalogError as err:
                if err.code in ("receipt_unrecognized_lines", "carrefour_account_error"):
                    error = CarrefourAccountError(
                        "No se ha podido recuperar este ticket desde el detalle ni desde el PDF. Consulta la información técnica en Logs → Tiendas.",
                        "ticket_pdf_fallback")
                    error.diagnostics.update({**fallback, "fallback":"pdf", "pdf_error":err.code,
                        **getattr(err, "diagnostics", {})})
                    # The failing phase remains identifiable even for a transport error.
                    error.diagnostics["stage"] = "ticket_pdf_fallback"
                    raise error from err
                raise
            self.activity.record("stores.account", "Carrefour: ticket preparado desde el PDF alternativo",
                source="manual", diagnostics={**fallback, "fallback":"pdf"})
            return draft
