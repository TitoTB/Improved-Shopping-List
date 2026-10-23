"""DIA account tickets. Credentials and session cookies remain private in HA."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.request
from uuid import uuid4

from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .catalog import CatalogError
from .const import DOMAIN
from .dia import ROOT, MAX_RESPONSE, NoRedirect
from .dia_receipts import summary, reference_id, reference_params

API="/api/v3/eservice-back"
COOKIE_FIELDS=("version","name","value","port","port_specified","domain","domain_specified","domain_initial_dot","path","path_specified","secure","expires","discard","comment","comment_url","rfc2109")


class DiaAccountError(CatalogError):
    def __init__(self,message,stage,**details):
        super().__init__(message,"dia_account_error")
        self.diagnostics={"stage":stage,**details}


class DiaAccountHTTP:
    """Synchronous, bounded first-party requests; used only in HA's executor."""
    def __init__(self,cookies=None):
        self.jar=http.cookiejar.CookieJar()
        for item in (cookies or [])[:50]:
            if not isinstance(item,dict) or str(item.get("domain","")).lstrip(".") not in ("dia.es","www.dia.es"):
                continue
            if any(not isinstance(item.get(key),str) or len(item[key])>4096 or any(c in item[key] for c in "\r\n") for key in ("name","value","domain","path")):
                continue
            try:
                self.jar.set_cookie(http.cookiejar.Cookie(**{key:item[key] for key in COOKIE_FIELDS},rest=item.get("rest",{})))
            except (KeyError,TypeError,ValueError):
                continue
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar),NoRedirect())

    def request(self,path,body=None,headers=None):
        stage=re.sub(r"/tickets/[0-9]+","/tickets/{id}",path.split("?",1)[0])
        if not path.startswith(API+"/"):
            raise DiaAccountError("La ruta de DIA no es válida.","endpoint")
        request=urllib.request.Request(ROOT+path,data=json.dumps(body).encode() if body is not None else None,
            headers={"Accept":"application/json","Content-Type":"application/json","X-Requested-With":"XMLHttpRequest",
                     "Origin":ROOT,"Referer":ROOT+"/my-account/tickets","x-locale":"es","x-mobile":"false",**(headers or {})})
        try:
            with self.opener.open(request,timeout=25) as response:
                raw=response.read(MAX_RESPONSE+1)
                if response.status!=200 or len(raw)>MAX_RESPONSE or "json" not in response.headers.get("Content-Type","").lower():
                    raise DiaAccountError("DIA ha devuelto una respuesta no reconocida.",stage,http_status=response.status,response_class="invalid_response")
                result=json.loads(raw)
                if not isinstance(result,dict):
                    raise ValueError
                cookies=[{**{key:getattr(c,key) for key in COOKIE_FIELDS},"rest":dict(c._rest)} for c in self.jar if c.domain.lstrip(".") in ("dia.es","www.dia.es")][:50]
                return result,cookies,{key:response.headers.get(key,"") for key in ("customer_code","session_id")}
        except urllib.error.HTTPError as err:
            try:
                kind=err.headers.get("Content-Type","").lower();raw=err.read(65536).lower()
                denied=err.code==403 and "json" not in kind
                classification="access_denied" if denied else "session_expired" if err.code==401 else "rate_limited" if err.code==429 else "http_error"
                message=("DIA ha rechazado el acceso desde esta conexión" if denied else "La sesión de DIA ha caducado. Vuelve a conectar la cuenta" if err.code==401 else "DIA no ha podido completar la consulta")
                raise DiaAccountError(f"{message} (HTTP {err.code}).",stage,http_status=err.code,response_class=classification,
                    service_misuse=b"service misuse" in raw) from None
            finally:
                err.close()
        except (urllib.error.URLError,OSError,TimeoutError) as err:
            raise DiaAccountError("No se ha podido conectar con DIA. Vuelve a intentarlo más tarde.",stage,response_class="network_error") from err
        except (ValueError,UnicodeError) as err:
            if isinstance(err,CatalogError):raise
            raise DiaAccountError("DIA ha devuelto una respuesta no reconocida.",stage,response_class="invalid_response") from err


class DiaAccount:
    def __init__(self,hass,receipts,activity):
        self.hass,self.receipts,self.activity=hass,receipts,activity
        self._store=Store(hass,1,f"{DOMAIN}.dia_account",private=True)
        self._credentials_store=Store(hass,1,f"{DOMAIN}.dia_credentials",private=True)
        self._options_store=Store(hass,1,f"{DOMAIN}.dia_options",private=True)
        self._session,self._credentials={},{}
        self._options={"history_enabled":False,"auto_ticket":False,"completion_at":0,"handled_completion":0,"ticket_day":""}
        self._lock,self._sync_lock=asyncio.Lock(),asyncio.Lock()
        self._active=False;self._generation=0;self._transport=None;self._task=None;self._timer_stop=None

    async def async_load(self):
        data=await self._store.async_load()
        if isinstance(data,dict) and isinstance(data.get("access_token"),str) and isinstance(data.get("email"),str):
            self._session=data
        data=await self._credentials_store.async_load()
        if isinstance(data,dict) and all(isinstance(data.get(k),str) and 0<len(data[k])<=255 for k in ("username","password")):
            self._credentials=data
        data=await self._options_store.async_load()
        if isinstance(data,dict):
            for key in ("history_enabled","auto_ticket"):
                if type(data.get(key)) is bool:self._options[key]=data[key]
            for key in ("completion_at","handled_completion"):
                if type(data.get(key)) in (int,float) and 0<=data[key]<1e12:self._options[key]=data[key]
            if isinstance(data.get("ticket_day"),str):self._options["ticket_day"]=data["ticket_day"]

    def start(self):
        self._active=True
        if not self._timer_stop:self._timer_stop=async_track_time_interval(self.hass,self._queue_background,timedelta(minutes=1))

    async def async_stop(self):
        self._active=False;self._generation+=1;self._transport=None
        if self._timer_stop:self._timer_stop();self._timer_stop=None
        if self._task:
            self._task.cancel();await asyncio.gather(self._task,return_exceptions=True)
        self._task=None

    def status(self,owner):
        return {"connected":bool(self._session.get("access_token")),"email":self._session.get("email","") if self._session.get("access_token") else "",
            "credentials_saved":bool(self._credentials),"remembered_email":self._credentials.get("username",""),
            "options":{key:self._options[key] for key in ("history_enabled","auto_ticket")},"verification_required":False,"verification_sent":False,"destinations":[]}

    async def _http(self,path,body=None):
        if not self._active:raise DiaAccountError("La integración ya no está activa.","inactive")
        generation=self._generation
        if self._transport is None:self._transport=DiaAccountHTTP(self._session.get("cookies",[]))
        headers={key:self._session.get(key,"") for key in ("session_id","cart_id","customer_code","customer_id")}
        result,cookies,rotated=await self.hass.async_add_executor_job(self._transport.request,path,body,headers)
        if not self._active or generation!=self._generation:raise DiaAccountError("La conexión de DIA ha cambiado.","inactive")
        self._session["cookies"]=cookies
        for key,value in rotated.items():
            if isinstance(value,str) and 0<len(value)<=255 and not any(c in value for c in "\r\n"):
                self._session[key]=value
                if key=="customer_code":self._session["customer_id"]=value
        if self._session.get("access_token"):await self._store.async_save(self._session)
        return result

    async def _login(self,username,password):
        self._transport=None
        previous=deepcopy(self._session)
        self._session={"session_id":str(uuid4()),"cart_id":str(uuid4()),"email":username}
        try:
            info=await self._http(API+"/check-email",{"email":username})
            personal=info.get("personal_info")
            if not isinstance(personal,dict):raise DiaAccountError("DIA no ha reconocido la cuenta.","check_email")
            body={"email":username,"password":password}
            for key in ("are_legal_conditions_accepted","are_consents_accepted"):
                # Reuse the account's existing choices; never grant new consents.
                body[key]=personal.get(key) is True
            response=await self._http(API+"/login",body)
            tokens=response.get("user_tokens")
            if not isinstance(tokens,dict) or any(not isinstance(tokens.get(k),str) or not 1<=len(tokens[k])<=16384 for k in ("access_token","refresh_token")):
                raise DiaAccountError("DIA no ha confirmado el inicio de sesión.","login")
            self._session.update({key:value for key,value in tokens.items() if key in ("access_token","refresh_token","id_token")})
            if previous.get("email")==username:self._session["purchase_refs"]=previous.get("purchase_refs",{})
            await self._store.async_save(self._session)
        except BaseException:
            self._session=previous;self._transport=None
            raise

    async def async_login(self,owner,username,password,remember_credentials=False):
        if type(remember_credentials) is not bool or not isinstance(username,str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",username.strip()) or len(username)>255 or not isinstance(password,str) or len(password)>255:
            raise DiaAccountError("Indica un correo y contraseña válidos.","login")
        username=username.strip()
        if not password:
            if not remember_credentials or self._credentials.get("username")!=username or not self._credentials.get("password"):
                raise DiaAccountError("Introduce la contraseña de DIA.","login")
            password=self._credentials["password"]
        async with self._lock:
            await self._login(username,password)
            credentials={"username":username,"password":password} if remember_credentials else {}
            await self._credentials_store.async_save(credentials);self._credentials=credentials
        if self._options["history_enabled"]:await self.async_sync_history(owner)
        return self.status(owner)

    async def _request(self,path):
        if not self._session.get("access_token"):raise DiaAccountError("Conecta tu cuenta de DIA en Ajustes → Tiendas.","not_connected")
        try:return await self._http(path)
        except DiaAccountError as err:
            if err.diagnostics.get("http_status")!=401:raise
            if self._credentials and self._credentials.get("username")==self._session.get("email"):
                try:
                    await self._login(self._credentials["username"],self._credentials["password"])
                    return await self._http(path)
                except DiaAccountError as retry_error:
                    if retry_error.diagnostics.get("http_status")!=401:raise
            self._session={};self._transport=None;await self._store.async_save({})
            raise

    async def async_disconnect(self,owner):
        async with self._lock:
            self._generation+=1;await self._store.async_save({});self._session={};self._transport=None
            self._options.update(history_enabled=False,auto_ticket=False);await self._options_store.async_save(self._options)
        return self.status(owner)

    async def async_options(self,owner,options):
        if not isinstance(options,dict) or set(options)!={"history_enabled","auto_ticket"} or any(type(v) is not bool for v in options.values()):
            raise DiaAccountError("Las opciones de DIA no son válidas.","options")
        if not self._session.get("access_token") and any(options.values()):raise DiaAccountError("Conecta primero tu cuenta de DIA.","not_connected")
        recover=options["history_enabled"] and not self._options["history_enabled"]
        self._options.update(options);await self._options_store.async_save(self._options)
        if recover:await self.async_sync_history(owner)
        self._queue_background()
        return self.status(owner)

    async def async_purchases(self,owner,cursor=None,*,import_summaries=None):
        from urllib.parse import urlencode
        if cursor is not None and (not isinstance(cursor,dict) or set(cursor)!={"offset"} or type(cursor["offset"]) is not int or not 0<=cursor["offset"]<=10000):
            raise DiaAccountError("La página de compras de DIA no es válida.","pagination")
        offset=cursor["offset"] if cursor else 0
        async with self._lock:
            response=await self._request(API+"/customer/current/tickets?"+urlencode({"offset":offset,"page_size":20}))
            rows=response.get("tickets")
            if not isinstance(rows,list) or len(rows)>100:raise DiaAccountError("DIA no ha devuelto un historial reconocido.","history_format")
            output=[];summaries=[];now=dt_util.utcnow();refs=deepcopy(self._session.get("purchase_refs",{}))
            for raw in rows:
                if isinstance(raw,dict) and (raw.get("return") or raw.get("void")):continue
                purchase=summary(raw)
                date=dt_util.as_utc(dt_util.parse_datetime(purchase["purchased_at"]).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE))
                if not now-timedelta(days=365)<=date<=now+timedelta(days=1):continue
                key=self.receipts._account_key(purchase["reference"],"dia")
                refs[key]=purchase
                summaries.append({"purchaseId":purchase["reference"],"purchaseDate":purchase["purchased_at"],"amount":purchase["amount"],"ticket_available":purchase["supported"]})
                output.append({"id":key,"purchased_at":purchase["purchased_at"],"amount":purchase["amount"],"store":"DIA","reviewable":purchase["supported"],"kind":"Ticket"})
            self._session["purchase_refs"]=dict(list(refs.items())[-1000:]);await self._store.async_save(self._session)
            added=await self.receipts.async_import_account_purchases(summaries,"dia") if (self._options["history_enabled"] if import_summaries is None else import_summaries) else 0
            total=response.get("total_tickets")
            if total is not None and (type(total) is not int or total<0):raise DiaAccountError("La paginación de DIA no es válida.","history_format")
            following=offset+len(rows)
            next_cursor={"offset":following} if rows and following<=10000 and (following<total if total is not None else len(rows)==20) else None
            return {"purchases":output,"next_cursor":next_cursor,"added":added}

    async def async_sync_history(self,owner):
        if self._sync_lock.locked():raise DiaAccountError("Ya se está incorporando el historial de DIA.","history_sync")
        async with self._sync_lock:
            cursor=None;added=available=0
            for _ in range(50):
                result=await self.async_purchases(owner,cursor,import_summaries=True)
                added+=result["added"];available+=len(result["purchases"]);cursor=result["next_cursor"]
                if cursor is None:return {"added":added,"available":available,"complete":True}
                await asyncio.sleep(1)
            return {"added":added,"available":available,"complete":False}

    async def async_preview_saved(self,owner,receipt_id):
        saved=self.receipts.stock.receipts["history"].get(receipt_id)
        if not saved or saved.get("store")!="dia" or not saved.get("summary_only") or not saved.get("account_key"):
            raise DiaAccountError("Esta compra no tiene un ticket pendiente de DIA.","saved_purchase")
        key=saved["account_key"]
        if key not in self._session.get("purchase_refs",{}):await self.async_sync_history(owner)
        return await self.async_preview(owner,key)

    async def async_preview(self,owner,purchase_id):
        from urllib.parse import urlencode
        async with self._lock:
            purchase=self._session.get("purchase_refs",{}).get(purchase_id)
            if not isinstance(purchase,dict) or self.receipts._account_key(purchase.get("reference",""),"dia")!=purchase_id:
                raise DiaAccountError("Vuelve a consultar las compras de DIA antes de abrir este ticket.","purchase_unavailable")
            params=reference_params(purchase.get("params"))
            response=await self._request(API+"/customer/current/tickets/"+params["ticket"]+"?"+urlencode({k:v for k,v in params.items() if k!="ticket"}))
            return await self.receipts.async_preview_dia_ticket(response,params,purchase["amount"],owner)

    async def _save_options(self):
        payload=dict(self._options)
        if payload!=getattr(self,"_saved_options",None):
            await self._options_store.async_save(payload)
            self._saved_options=payload

    def note_completion(self):
        if not self._active or not self._options["auto_ticket"] or not self._session.get("access_token"):return
        self._options["completion_at"]=time.time();self._queue_background()

    def _queue_background(self,*_args):
        if self._active and self._options["auto_ticket"] and (self._task is None or self._task.done()):
            self._task=self.hass.async_create_background_task(self._run_background(),"DIA automatic tickets")

    async def _run_background(self):
        # A shared coordinator orders all account connectors, not one independent search per store.
        if getattr(self,"ticket_accounts",None):
            await self.ticket_accounts.async_check()

    def automatic_due(self,now,detected_today):
        day=now.date().isoformat()
        return bool(self._active and self._session.get("access_token") and self._options["auto_ticket"] and self._options["ticket_day"]!=day and
            self._options["completion_at"]>self._options["handled_completion"] and (detected_today or now.strftime("%H:%M")>=self.settings.snapshot["price_update_time"]))

    async def async_automatic_ticket(self,now,detected_today):
        if not self.automatic_due(now,detected_today):return
        self._options["ticket_day"]=now.date().isoformat();await self._options_store.async_save(self._options)
        try:
            result=await self.async_purchases("automatic_dia")
            candidates=result["purchases"]
            if detected_today:
                candidates=[p for p in candidates if dt_util.parse_datetime(p["purchased_at"]).date()==now.date()]
            latest=max(candidates,key=lambda p:p["purchased_at"],default=None)
            if latest and self._active and self._options["auto_ticket"]:
                ref=self._session["purchase_refs"][latest["id"]]["reference"]
                if not self.receipts.account_ticket_available(ref,"dia"):
                    draft=await self.async_preview("automatic_dia",latest["id"])
                    if self._active and self._options["auto_ticket"]:await self.receipts.async_archive_account_ticket(draft["token"],"automatic_dia")
                    else:self.receipts.discard(draft["token"],"automatic_dia")
                self.activity.record("stores.account","DIA: última compra disponible para revisar",source="automatic")
            self._options["handled_completion"]=self._options["completion_at"]
            return bool(latest and dt_util.parse_datetime(latest["purchased_at"]).date()==now.date())
        finally:
            await self._options_store.async_save(self._options)
