"""Lidl offer-region identifiers observed in its public product API; not postal codes."""

LIDL_REGIONS = {'1': 'A Coruña', '2': 'Pontevedra', '3': 'Lugo', '4': 'Ourense', '5': 'Asturias', '6': 'León', '7': 'Zamora', '8': 'Salamanca', '9': 'Ávila', '10': 'Valladolid', '11': 'Segovia', '12': 'Soria', '13': 'Burgos', '14': 'Palencia', '15': 'Cantabria', '16': 'Vizcaya', '17': 'Guipúzcoa', '18': 'Álava', '19': 'La Rioja', '20': 'Navarra', '21': 'Huesca', '22': 'Zaragoza', '23': 'Teruel', '24': 'Lleida', '25': 'Tarragona', '26': 'Barcelona', '27': 'Girona', '28': 'Madrid', '29': 'Cáceres', '30': 'Badajoz', '31': 'Toledo', '32': 'Ciudad Real', '33': 'Guadalajara', '34': 'Cuenca', '35': 'Albacete', '36': 'Castellón', '37': 'Valencia', '38': 'Alicante', '39': 'Murcia', '40': 'Huelva', '41': 'Sevilla', '42': 'Cádiz', '43': 'Córdoba', '44': 'Málaga', '45': 'Jaén', '46': 'Granada', '47': 'Almería', '48': 'Mallorca', '49': 'Santa Cruz de Tenerife', '50': 'Las Palmas', '51': 'Ceuta', '52': 'Melilla', '53': 'Fuerteventura', '54': 'Lanzarote', '55': 'Gran Canaria', '56': 'Vit 2 (región comercial de Lidl)', '57': 'Cat 2 (región comercial de Lidl)', '58': 'Menorca', '59': 'Ibiza'}


def lidl_zone(region_id):
    """Map island offer regions to the web shop zone, preserving mainland defaults."""
    if region_id in {"48", "58", "59"}:
        return "BAL"
    if region_id in {"49", "50", "53", "54", "55"}:
        return "CAN"
    if region_id in {"51", "52"}:
        return ""  # No verified online zone for Ceuta or Melilla.
    return "PEN"
