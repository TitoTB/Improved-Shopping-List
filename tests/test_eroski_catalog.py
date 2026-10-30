"""Exact EAN search, anonymous session reuse and opt-in Eroski alternatives."""
from unittest.mock import AsyncMock
import time

import pytest

from custom_components.improved_shopping_list.eroski_catalog import EroskiCatalogClient, search_result, product_data
from custom_components.improved_shopping_list.eroski import EroskiError, ROOT
from custom_components.improved_shopping_list.store_links import normalize_link
from custom_components.improved_shopping_list.option_lookup import OptionLookup
from custom_components.improved_shopping_list.catalog import Catalog
from custom_components.improved_shopping_list.ean_links import EANLinks
from custom_components.improved_shopping_list.product_references import gtin
from custom_components.improved_shopping_list.public_catalogs import CatalogDiscovery, PublicCatalogSource

CODE = '8410199023094'
WEB = ROOT+'/es/productdetail/24791428-patatas-lays-gourmet-bolsa-170-g/'
SEARCH = ROOT+'/es/search/results/?q='+CODE
EMPTY = '<p class="lineal-products-no-products" IDAutomation="no_results_found">No hemos encontrado lo que buscas</p>'
RESULTS = f'''<h1><span>Resultados</span><span class="item-desk">Mostrando resultados para {CODE}</span> (1)</h1>
<div id="productListZone"><div class="product-item-lineal"><a href="{WEB.replace('.es/','.es:443/')}">Patatas</a><a href="{WEB}">Imagen</a></div></div>
<aside><a href="{ROOT}/es/productdetail/111-recomendado/">Recomendado</a></aside>'''
PRODUCT = f'''<link rel="canonical" href="{WEB}"><h1 itemprop="description">Patatas LAY`S GOURMET, bolsa 170 g</h1>
<meta itemprop="priceCurrency" content="EUR"><span itemprop="price" class="offer-now">2,89</span>'''


def test_exact_query_unique_card_and_canonical_product():
    link = search_result(RESULTS, gtin(CODE))
    assert link['id'] == '24791428' and link['url'] == WEB
    data = product_data(PRODUCT, link, CODE)
    assert data['ean'] == CODE and data['price'] == 2.89
    assert data['content_quantity'] == 170 and data['content_unit'] == 'g'
    assert data['measure_price']['price'] == 17 and data['brand'] == ''
    assert search_result(EMPTY, CODE) is None


@pytest.mark.parametrize('raw', [RESULTS.replace(CODE,'8410422111086'),RESULTS.replace('(1)','(2)'),
    RESULTS.replace('supermercado.eroski.es','evil.example'), '<h1>Inicia sesión</h1>',
    RESULTS.replace('productListZone','recommendations'), RESULTS+EMPTY])
def test_unknown_query_ambiguous_results_and_untrusted_links_are_rejected(raw):
    with pytest.raises(EroskiError): search_result(raw, CODE)


async def test_live_shape_reuses_anonymous_session_and_paces_every_request(hass, aioclient_mock):
    client = EroskiCatalogClient(hass)
    aioclient_mock.get(ROOT+'/es/', text='<html>Inicio</html>')
    aioclient_mock.get(SEARCH, text=RESULTS)
    aioclient_mock.get(WEB, text=PRODUCT)
    aioclient_mock.get(ROOT+'/es/search/results/?q=9999999999994', text=EMPTY)
    gate = AsyncMock()
    try:
        result = await client.search(gtin(CODE), gate)
        assert result['ean'] == CODE and result['reference_id'] == '24791428'
        assert await client.search('9999999999994', gate) is None
        assert aioclient_mock.call_count == gate.await_count == 4
    finally: client.close()


async def test_manual_url_does_not_invent_ean_and_cached_page_still_requires_verification(hass, aioclient_mock, monkeypatch):
    lookup = OptionLookup(hass)
    monkeypatch.setattr(lookup, '_before_request', AsyncMock())
    aioclient_mock.get(ROOT+'/es/', text='<html>Inicio</html>')
    aioclient_mock.get(SEARCH, text=RESULTS)
    aioclient_mock.get(WEB, text=PRODUCT)
    try:
        manual = await lookup.retrieve(WEB)
        assert not manual.get('ean') and manual['price'] == 2.89
        verified = await lookup.retrieve(WEB, expected_ean=CODE)
        assert verified['ean'] == CODE and aioclient_mock.call_count == 4
        assert await lookup.retrieve(WEB, expected_ean=CODE) == verified
        assert aioclient_mock.call_count == 4
        with pytest.raises(ValueError, match='EAN'):
            await lookup.retrieve(WEB, expected_ean='8410422111086')
    finally: lookup.close()


async def test_dictionary_link_must_match_exact_ean_search_before_reading_price(hass, aioclient_mock):
    client = EroskiCatalogClient(hass)
    aioclient_mock.get(ROOT+'/es/', text='<html>Inicio</html>')
    aioclient_mock.get(SEARCH, text=RESULTS.replace('24791428-', '999-'))
    try:
        with pytest.raises(EroskiError, match='EAN'):
            await client.retrieve(WEB, AsyncMock(), CODE)
        assert aioclient_mock.call_count == 2
    finally: client.close()


async def test_visible_source_finds_alternative_for_complete_ean_then_skips_repeat(hass, aioclient_mock, monkeypatch):
    catalog = Catalog(hass); await catalog.async_load()
    await catalog.async_save_product({'name':'Patatas','barcodes':[CODE],'commercial_references':[
        {'store':'carrefour','ean':CODE,'name':'Patatas 170 g','reference_id':'R-old','url':'',
         'content_quantity':170,'content_unit':'g','last_price':{'price':3,'currency':'EUR','checked_at':int(time.time())}}]})
    links = EANLinks(hass,catalog); await links.async_load(); links._data['checked_at'] = time.time()
    lookup = OptionLookup(hass)
    discovery = CatalogDiscovery(hass,catalog,links,lookup); await discovery.async_load()
    source = PublicCatalogSource(hass,catalog,links,lookup,None,'eroski',discovery); await source.async_load()
    source._active = True; discovery.managers = {'eroski':source}
    monkeypatch.setattr(source,'_before_request',AsyncMock())
    aioclient_mock.get(ROOT+'/es/',text='<html>Inicio</html>')
    aioclient_mock.get(SEARCH,text=RESULTS)
    aioclient_mock.get(WEB,text=PRODUCT)
    try:
        await source.async_run(); assert aioclient_mock.call_count == 0
        await source.async_set_enabled(True)
        await source.async_run(); assert aioclient_mock.call_count == 0  # Data-only source: already complete.
        await source.async_set_show_store(True)
        await source.async_run()
        ref = next(r for r in catalog.products[0]['commercial_references'] if r['store']=='eroski')
        assert ref['last_price']['price'] == 2.89 and ref['url'] == WEB and gtin(ref['ean']) == gtin(CODE)
        await source.async_run()
        assert source.snapshot['total'] == 0 and aioclient_mock.call_count == 3
        await source.async_set_show_store(False)
        assert not any(r['store']=='eroski' for r in catalog.products[0]['commercial_references'])
        await source.async_set_show_store(True)
        assert aioclient_mock.call_count == 3
    finally:
        await source.async_stop(); lookup.close()


async def test_http_block_exposes_stage_and_backoff(hass, aioclient_mock):
    client = EroskiCatalogClient(hass)
    aioclient_mock.get(ROOT+'/es/',status=403)
    try:
        with pytest.raises(EroskiError) as error: await client.search(CODE,AsyncMock())
        assert error.value.diagnostics['retry_seconds'] >= 900
        assert error.value.diagnostics['stage'] == 'session'
        assert client.session is None
    finally: client.close()
