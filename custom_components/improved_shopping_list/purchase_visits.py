"""Minimum-dwell visits and non-duplicating, multi-store daily purchase groups."""
from copy import deepcopy
from datetime import timedelta

from homeassistant.util import dt as dt_util


class PurchaseVisits:
    def _observe_shop_presence(self, entity, state):
        config = self.zone_config
        now = dt_util.now()
        today = now.date().isoformat()
        if not self.enabled or not config.get('zone_assignment'):
            self._inside_since.clear()
            return
        wanted = set()
        for shop in config.get('shops',[]):
            for zone_id in shop['zones']:
                key = (shop['id'],entity,zone_id)
                zone = self.hass.states.get(zone_id)
                inside = bool(state and state.state not in ('unknown','unavailable') and zone and self._inside_zone(state,zone))
                if not inside:
                    # Known exits may qualify between minute ticks. Unknown states
                    # never add unobserved dwell time.
                    start = self._inside_since.pop(key,None)
                    if start and state and state.state not in ('unknown','unavailable'):
                        self._qualify_visit(shop,entity,zone_id,start,now)
                    continue
                wanted.add(key)
                start = self._inside_since.setdefault(key,now)
                if start.date() != now.date():
                    start = self._inside_since[key] = now.replace(hour=0,minute=0,second=0,microsecond=0)
                self._qualify_visit(shop,entity,zone_id,start,now)
        for key in list(self._inside_since):
            if key[1] == entity and key not in wanted:
                self._inside_since.pop(key,None)

    def _qualify_visit(self, shop, entity, zone, start, now):
        seconds = max(0,(now-start).total_seconds())
        if seconds >= self.zone_config.get('minimum_minutes',5)*60:
            self._shop_visits.append((now.date().isoformat(),shop['id'],entity,zone,start.isoformat(),now.isoformat(),seconds))

    def qualified_places(self, day=None):
        day = day or dt_util.now().date().isoformat()
        persons = set(self.zone_config.get('persons',[]))
        visits = self._days.get(day,{}).get('qualified_shops',{})
        return [(shop, [v for v in visits.get(shop['id'],{}).values()
                       if v['person'] in persons and v['zone'] in shop['zones']
                       and v['seconds'] >= self.zone_config.get('minimum_minutes',5)*60])
                for shop in self.zone_config.get('shops',[])
                if any(v['person'] in persons and v['zone'] in shop['zones']
                       and v['seconds'] >= self.zone_config.get('minimum_minutes',5)*60
                       for v in visits.get(shop['id'],{}).values())] if self.zone_config.get('zone_assignment') else []

    def ticket_scope(self, account):
        history = self.receipts.stock.receipts['history']
        return sorted(receipt['id'] for receipt in history.values()
            if receipt.get('purchase_group') == dt_util.now().date().isoformat()
            and receipt.get('account') == account and receipt.get('needs_details'))

    async def _check_places(self):
        if not self.enabled:
            self._events.clear();self._shop_visits.clear();self._inside_since.clear()
            return
        for entity in self.zone_config.get('persons',[]):
            self._observe_shop_presence(entity,self.hass.states.get(entity))
        now = dt_util.now()
        allowed={(shop['id'],person,zone) for shop in self.zone_config.get('shops',[])
                 for person in self.zone_config.get('persons',[]) for zone in shop['zones']}
        self._inside_since={key:value for key,value in self._inside_since.items() if key in allowed}
        days = deepcopy(self._days)
        events, visits = list(self._events), list(self._shop_visits)
        for day, when, key, product in events:
            record = days.setdefault(day,{'entries':{},'first_at':when,'created':False,'receipt_id':'detected:'+day})
            if len(record['entries']) < 2500:
                record['entries'].setdefault(key,{**product,'key':key,'completed_at':when})
        for day, shop, person, zone, start, end, seconds in visits:
            record = days.setdefault(day,{'entries':{},'first_at':end,'created':False,'receipt_id':'detected:'+day})
            record.setdefault('qualified_shops',{}).setdefault(shop,{})[person+':'+zone] = {
                'person':person,'zone':zone,'started_at':start,'last_seen':end,'seconds':seconds}
        cutoff = (now.date()-timedelta(days=6)).isoformat()
        days = {day:value for day,value in days.items() if day >= cutoff}
        if days != self._days:
            await self._store.async_save({'days':days});self._days=days
        for _ in events:self._events.popleft()
        for _ in visits:self._shop_visits.popleft()
        request = False
        for day,record in self._days.items():
            products = [{**p,'key':key,'completed_at':p.get('completed_at',record['first_at'])} for key,p in record['entries'].items()]
            if len(products) <= self.zone_config.get('threshold',5):continue
            places = self.qualified_places(day)
            allocations = {shop['id']:[] for shop,_ in places}
            unknown = []
            for product in products:
                when = dt_util.parse_datetime(product.get('completed_at',''))
                matches = [shop['id'] for shop,visits in places if when and any(
                    dt_util.parse_datetime(v['started_at']) <= when <= dt_util.parse_datetime(v['last_seen']) for v in visits)]
                if len(matches)==1:allocations[matches[0]].append(product)
                elif len(places)==1:allocations[places[0][0]['id']].append(product)
                else:unknown.append(product)
            groups = []
            for shop,visits in places:
                groups.append({'id':'detected:'+day+':'+shop['id'],'shop':shop,'products':allocations[shop['id']],
                    'shoppers':sorted({v['person'] for v in visits}),
                    'purchased_at':min(v['started_at'] for v in visits)})
            if unknown or not places:
                groups.append({'id':'detected:'+day,'shop':None,'products':unknown or products,'shoppers':[],
                    'purchased_at':record['first_at']})
            await self.receipts.async_save_purchase_group(day,groups,products)
            identifiers = [group['id'] for group in groups]
            if record.get('receipt_ids') != identifiers:
                record['receipt_ids'] = identifiers;record['created']=True
                await self._store.async_save({'days':self._days})
                self.activity.record('purchase.detected','Compra detectada: '+str(len(groups))+' registros pendientes de revisión',source='automatic')
                request = request or day == now.date().isoformat() and bool(self.ticket_scope('carrefour'))
        await self.receipts.async_reconcile_detected_purchases()
        if request and self.pending_for_today:self.carrefour.note_completion()
