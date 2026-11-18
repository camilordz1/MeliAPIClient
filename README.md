# Meli SDK

[![CI](https://github.com/camilordz1/meli-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/camilordz1/meli-sdk/actions/workflows/ci.yml)

`meli-sdk` es un cliente moderno y robusto para interactuar con la API de Mercado Libre en Python. Diseñado con una arquitectura modular basada en composición, soporta el manejo de múltiples sesiones concurrentes, renovación automática de tokens, y almacenamiento flexible de credenciales (archivos locales, memoria o bases de datos), conservando la interfaz clásica para los desarrollos existentes.

> **Nota:** el paquete se llamaba anteriormente `MeliAPIClient`. El nombre de importación actual es `meli_sdk` y la distribución se publica en PyPI como `meli-python-sdk` (el nombre `meli-sdk` no está disponible en PyPI).

---

## Características Clave

*   **Doble Interfaz**: Interfaz clásica (Legacy) para compatibilidad con código existente, e interfaz moderna (Composición) para nuevos desarrollos.
*   **Gestión Eficiente de Tokens**: Renovación automática y transparente de tokens expirados antes de cada petición HTTP.
*   **Almacenamiento Personalizado (`TokenStorage`)**: Guarda tus tokens en archivos JSON locales, en memoria, o directamente en tu base de datos (PostgreSQL, SQLite, MySQL, Redis, etc.) mediante funciones callback.
*   **Multi-cuenta / Multisesión**: Capacidad de gestionar múltiples cuentas de Mercado Libre en paralelo sin colisiones.
*   **Recursos Completos**: Gestión de órdenes, facturas, envíos, publicaciones (stock/precios), reputación, tendencias y opiniones de productos.
*   **Excepciones Específicas**: Manejo preciso de errores de red y respuestas del API de Mercado Libre.

---

## Instalación

Instala el módulo directamente desde el entorno local de tu proyecto:

```bash
pip install --pre meli-python-sdk
```

---

## Uso Básico (Interfaz Clásica)

Si ya tienes un script que utiliza el formato tradicional de tres archivos JSON (`ml_keys.json`, `ml_token.json`, `ml_user.json`), puedes continuar usándolo exactamente igual. El módulo renovará automáticamente el token de acceso usando el motor moderno de fondo.

```python
from meli_sdk import Session, Order, Bill, Ship

def run():
    # Inicialización tradicional
    session = Session("ml_keys.json", "ml_token.json", "ml_user.json")
    
    # Instanciación clásica de recursos
    orders_api = Order(session)
    bills_api = Bill(session)
    ship_api = Ship(session)

    # Listado de órdenes del vendedor
    mis_ordenes = orders_api.list(year=2026, month=6)
    print("Órdenes:", mis_ordenes)

    # Detalle de envío
    info_envio = ship_api.info("4028374928")
    print("Envío:", info_envio)

if __name__ == "__main__":
    run()
```

---

## Uso Avanzado (Interfaz Moderna)

El diseño moderno utiliza la composición a través de un único cliente centralizado (`MeliClient`) y propiedades perezosas para acceder a los recursos.

```python
from meli_sdk import MeliClient, FileTokenStorage

# 1. Definir dónde almacenar el token de esta sesión específica
storage = FileTokenStorage("tokens/cuenta_1.json")

# 2. Inicializar el cliente
client = MeliClient(
    client_id="TU_CLIENT_ID",
    client_secret="TU_CLIENT_SECRET",
    token_storage=storage
)

# 3. Consultar recursos usando nomenclatura estándar y tipado estático
# Ejemplo: Obtener información detallada de una publicación
producto = client.items.get("MCO123456789")
print(f"Producto: {producto['title']} | Precio: {producto['price']}")

# Actualizar stock de un producto
client.items.update_stock("MCO123456789", nuevo_stock=15)
```

### Sesión persistente y timeout

Cada `MeliClient` usa una `requests.Session` propia y aplica un timeout de 30 segundos a todas las
peticiones y a la renovación del token. Puedes cambiar el timeout, compartir una sesión entre
clientes o cerrarla automáticamente con un context manager:

```python
import requests
from meli_sdk import FileTokenStorage, MeliClient

storage = FileTokenStorage("tokens/cuenta_1.json")

# Timeout propio: 5 s para conectar y 20 s para leer
client = MeliClient(
    client_id="TU_CLIENT_ID",
    client_secret="TU_CLIENT_SECRET",
    token_storage=storage,
    timeout=(5, 20),
)

# Compartir una sesión (el cliente no la cierra)
shared = requests.Session()
client = MeliClient(
    client_id="TU_CLIENT_ID",
    client_secret="TU_CLIENT_SECRET",
    token_storage=storage,
    session=shared,
)

# Cerrar la sesión al terminar
with MeliClient(
    client_id="TU_CLIENT_ID",
    client_secret="TU_CLIENT_SECRET",
    token_storage=storage,
    timeout=10,
) as client:
    client.items.get("MCO123456789")
```

El timeout también se puede sobrescribir por llamada con `client.request(..., timeout=5)`.

### Reintentos seguros

El cliente reintenta automáticamente los fallos transitorios sin duplicar operaciones:

| Respuesta | Métodos que se reintentan |
| --- | --- |
| `429 Too Many Requests` | todos |
| `500`, `502`, `503`, `504` | solo idempotentes: `GET`, `HEAD`, `OPTIONS`, `PUT`, `DELETE` |
| `ConnectionError` / `Timeout` | solo idempotentes |
| cualquier otra (4xx, otros 5xx) | nunca |

La espera usa el encabezado `Retry-After` cuando está presente (segundos o fecha HTTP) y, si no,
un backoff exponencial. Los valores se limitan a `max_backoff`:

```python
client = MeliClient(
    client_id="TU_CLIENT_ID",
    client_secret="TU_CLIENT_SECRET",
    token_storage=storage,
    max_retries=3,       # 0 desactiva los reintentos
    backoff_factor=0.5,  # espera base: backoff_factor * 2 ** intento
    max_backoff=60.0,    # tope de espera en segundos
)
```

En el peor caso, una petición puede tardar hasta `(max_retries + 1) × timeout` más las esperas del
backoff (unos 2 minutos con los valores por defecto) antes de fallar. Para acotar ese tiempo, reduce
`max_retries` o `timeout`.

### Concurrencia y refresh del token

Los refresh tokens de Mercado Libre son de un solo uso: al canjear uno, deja de ser válido. Para
evitar que varias peticiones simultáneas quemen el mismo refresh token, el cliente serializa las
renovaciones por instancia y por almacenamiento. Si otro hilo u otro cliente ya renovó el token, se
reutiliza el nuevo sin volver a llamar a `/oauth/token`.

`MemoryTokenStorage` y `FileTokenStorage` incluyen un lock. En `FileTokenStorage` el lock es por ruta
absoluta dentro del mismo proceso, así que **no coordina procesos separados**. Para varios procesos,
usa `CallbackTokenStorage` con un lock de base de datos:

```python
import contextlib
from meli_sdk import CallbackTokenStorage, MeliClient

@contextlib.contextmanager
def db_lock():
    # Pseudocódigo: advisory lock o transacción SELECT ... FOR UPDATE
    # with connection.transaction():
    #     connection.execute("SELECT pg_advisory_lock(42)")
    #     try:
    yield
    #     finally:
    #         connection.execute("SELECT pg_advisory_unlock(42)")

storage = CallbackTokenStorage(
    load_callback=load_token_from_db,
    save_callback=save_token_to_db,
    lock_callback=db_lock,
)
client = MeliClient(
    client_id="TU_CLIENT_ID",
    client_secret="TU_CLIENT_SECRET",
    token_storage=storage,
)
```

Además, si una petición responde `401`, el cliente renueva el token una vez y reintenta la petición
con el nuevo token. Un segundo `401` se reporta como error.

### Autorización (OAuth)

Para obtener el primer token de un usuario, genera un `state` impredecible y redirige al usuario a la
URL de autorización. El `redirect_uri` debe ser exactamente el registrado en la aplicación de
Mercado Libre, y el `state` debe validarse en el callback (protección CSRF):

```python
import secrets
from meli_sdk import FileTokenStorage, MeliClient

storage = FileTokenStorage("tokens/cuenta_1.json")
client = MeliClient(
    client_id="TU_CLIENT_ID",
    client_secret="TU_CLIENT_SECRET",
    token_storage=storage,
)

state = secrets.token_urlsafe(32)
url = client.get_authorization_url(
    "https://tu-app.example.com/callback",
    state=state,
    site_id="MCO",
)
# Redirige al usuario a `url`.

# En el callback:
# if request.args["state"] != state: abort(400)
token = client.exchange_code(
    request.args["code"],
    "https://tu-app.example.com/callback",
)
```

`get_authorization_url` también acepta `code_challenge` y agrega automáticamente
`code_challenge_method=S256` si usas PKCE. `exchange_code` funciona incluso con un almacenamiento
vacío y guarda el token igual que la renovación.

Si quieres identificarte ante Mercado Libre, pasa `user_agent="TuApp/1.0"`: el SDK lo antepone al
valor por defecto `meli-sdk/<versión> python-requests/<versión>`.

### Datos normalizados

`bills.get_normalized(order_id)` devuelve un `BillingInfo` con los datos de facturación del
comprador. Primero lee `buyer.billing_info.id` de la orden y consulta el endpoint vigente
`GET /orders/billing-info/{site_id}/{id}`; si no hay id o el endpoint responde 404, cae al endpoint
antiguo `/orders/{id}/billing_info` (v2 y luego v1). El endpoint antiguo está
[obsoleto](https://developers.mercadolibre.com.ar/en_us/billing-info) y Mercado Libre lo mantiene
solo por un tiempo limitado.

```python
billing = client.bills.get_normalized(order_id)
if billing is not None:
    print(billing.full_name, billing.doc_type, billing.doc_number)
    print(billing.address.city, billing.address.zip_code)
```

En Colombia (MCO), el endpoint nuevo de facturación no devuelve el código postal de facturación, así
que `address.zip_code` suele ser `None`. Si tu aplicación lo necesita, obtenlo de otra fuente; no
asumas que el código postal del envío es el de facturación, porque las direcciones pueden diferir.

`shipments.get_normalized(shipment_id)` devuelve un `ShipmentInfo` con el estado, el seguimiento, el
costo (un `Decimal`) y la dirección de entrega:

```python
shipment = client.shipments.get_normalized(shipment_id)
print(shipment.status, shipment.shipping_cost, shipment.currency_id)
```

Los campos de texto pueden ser `None` (por ejemplo mientras un documento está en proceso) y no se
inventan valores por defecto. Cada objeto conserva la respuesta completa en `raw`, que no aparece en
`repr` para no exponer datos personales.

---

### Comisiones y costos de envío

`items.get_listing_prices(price, *, category_id=None, site_id="MCO", ...)` devuelve una lista de
`ListingPrice` con la comisión de venta (`sale_fee_amount`, `percentage_fee`, `fixed_fee`) y la de
publicación. `items.get_listing_price(price, listing_type_id, ...)` devuelve solo la opción pedida.

`shipments.get_free_shipping_quote(...)` cotiza el envío gratis: con `item_id=...` o con
`dimensions=` (una tupla `(alto, ancho, largo, peso)` o una cadena `"HxWxL,G"`). El peso va en
gramos enteros. Con `dimensions` también son obligatorios `item_price` y `listing_type_id`, porque
sin ellos la cotización puede volver en cero.

```python
prices = client.items.get_listing_prices(100000, category_id="MCO1430")
gold = client.items.get_listing_price(100000, "gold_special", category_id="MCO1430")

quote = client.shipments.get_free_shipping_quote(
    dimensions=(10, 20, 30, 500),
    item_price=100000,
    listing_type_id="gold_special",
    logistic_type="xd_drop_off",
)
```

`shipments.get_costs(shipment_id)` es la fuente para conciliar: `buyer_cost` es lo que pagó el
comprador y `seller_cost` la suma de lo que se le cobró al vendedor.

### Publicaciones (user products y descripciones)

Si el vendedor tiene la etiqueta `user_product_seller`, la API exige `family_name` y rechaza
`title`; en caso contrario usa `title`. `items.is_user_product_seller()` consulta la etiqueta:

```python
if client.items.is_user_product_seller():
    payload["family_name"] = "Camisetas de algodon"
else:
    payload["title"] = "Camiseta de algodon"
```

`items.validate(payload)` envía `POST /items/validate` y devuelve un `ValidationResult` sin crear
nada. Un 400 con solo advertencias significa que la publicación es válida: `result.valid` es `True`
y las advertencias quedan en `result.warnings`; los errores de bloqueo quedan en `result.errors`.

Para vendedores de user products, las dimensiones del paquete se envían con
`seller_package_attributes(alto, ancho, largo, peso)`, con enteros en `cm` y gramos:

```python
from meli_sdk import seller_package_attributes

payload["attributes"] = seller_package_attributes(10, 20, 30, 500)
```

`items.set_description(item_id, plain_text)` actualiza la descripción; si el artículo aún no tiene
una, cae automáticamente de `PUT` a `POST`. `items.get_description(item_id)` devuelve el payload
crudo y `items.update_description` es un alias de `set_description`.

### Fotos

Instala el extra de imágenes: `pip install "meli-python-sdk[images]"`.

`items.upload_picture(source, *, filename=None, convert="auto")` sube una foto y devuelve un
`UploadedPicture`. `source` puede ser una ruta, `bytes` o un archivo binario.

*   `convert="auto"` (por defecto): sube tal cual un JPEG o PNG de hasta 10 MB; cualquier otro
    formato (WebP, GIF, BMP) o un archivo mayor se convierte a JPEG. **No** agranda una imagen
    pequeña.
*   `convert=True`: siempre convierte a JPEG y agranda con LANCZOS hasta que el lado menor tenga
    500 px.
*   `convert=False`: exige JPEG o PNG de hasta 10 MB; si no, lanza `ValueError`.

Mercado Libre acepta JPG, JPEG y PNG de hasta 10 MB y exige un mínimo de 500×500 px; no agranda las
imágenes, así que para fotos pequeñas usa `convert=True`. Después de subirla, enlázala al artículo:

```python
picture = client.items.upload_picture("fotos/camiseta.png", convert=True)
client.items.add_picture("MCO123456789", picture.id)
```

Para reemplazar o reordenar fotos se envía `PUT /items/{id}` con la lista completa de `pictures`.

## Persistencia en Bases de Datos (Estrategia `CallbackTokenStorage`)

Si quieres guardar los tokens de acceso en una base de datos (por ejemplo, en un modelo de Django, SQLAlchemy, o en Redis) en lugar de archivos JSON locales, utiliza `CallbackTokenStorage` inyectando funciones de carga y guardado:

```python
from meli_sdk import MeliClient, CallbackTokenStorage

# Supongamos que tienes un modelo Django o SQLAlchemy para las credenciales
def load_token_from_db():
    credential = CredencialMercadoLibre.objects.get(id=1)
    return {
        "access_token": credential.access_token,
        "refresh_token": credential.refresh_token,
        "expires_in": credential.expires_in,
        "created_at": credential.created_at,
        "expires_at": credential.expires_at,
        "user_id": credential.user_id,
    }

def save_token_to_db(token_data):
    # Esta función es llamada automáticamente por el cliente cada vez que el token se renueva
    CredencialMercadoLibre.objects.update_or_create(
        id=1,
        defaults={
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in"),
            "created_at": token_data.get("created_at"),
            "expires_at": token_data.get("expires_at"),
            "user_id": token_data.get("user_id"),
        }
    )

# Inicializar con almacenamiento de base de datos
db_storage = CallbackTokenStorage(load_callback=load_token_from_db, save_callback=save_token_to_db)

client = MeliClient(
    client_id="TU_CLIENT_ID",
    client_secret="TU_CLIENT_SECRET",
    token_storage=db_storage
)
```

---

## Desarrollo

Crea un entorno virtual e instala el proyecto en modo editable junto con las dependencias de
desarrollo:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Ejecuta la suite de pruebas con pytest:

```bash
python -m pytest
```

---

## Guía de Recursos Disponibles

### 1. Órdenes (`client.orders`)
*   `orders.get(order_id)`: Obtiene el detalle de una orden.
*   `orders.search(seller_id=None, year=None, month=None, *, status=None, sort="date_asc",
    utc_offset="-05:00", extra_params=None)`: Busca órdenes de un periodo de tiempo.
*   `orders.iter_all(seller_id=None, year=None, month=None, *, status=None, sort="date_asc",
    utc_offset="-05:00", page_size=50, extra_params=None)`: Generador que recorre todas las páginas.
*   `orders.get_pack(pack_id)`: Obtiene información de un paquete de envíos.

El rango de fechas se calcula en la zona horaria del vendedor. Colombia (`MCO`) usa `-05:00` sin
horario de verano; si vendes en otro país, pasa su offset:

```python
# Órdenes pagadas de febrero de 2026 en Colombia
client.orders.search(year=2026, month=2, status="paid")

# Mismo rango en UTC, ordenado de más reciente a más antiguo
client.orders.search(year=2026, month=2, sort="date_desc", utc_offset="+00:00")
```

`orders.iter_all` recorre todas las páginas y respeta el máximo de 50 órdenes por página. La
validación de `page_size` ocurre al consumir el generador, así que puedes encadenarlo con `break`
sin descargar el resto:

```python
for order in client.orders.iter_all(year=2026, month=11, status="paid"):
    print(order["id"])
```

### 2. Facturas (`client.bills`)
*   `bills.get_billing_info(order_id)`: Detalles de facturación del cliente.
*   `bills.has_fiscal_document(pack_id)`: Verifica si el paquete tiene una factura adjunta; una
    lista vacía se considera sin factura.
*   `bills.upload_fiscal_document(pack_id, document, *, filename=None)`: Sube una factura. Solo se
    aceptan archivos PDF.

```python
# Desde una ruta
client.bills.upload_fiscal_document(4028374928, "facturas/factura-123.pdf")

# Desde bytes, sin escribir un archivo temporal
with open("facturas/factura-123.pdf", "rb") as f:
    pdf_bytes = f.read()
client.bills.upload_fiscal_document(4028374928, pdf_bytes, filename="factura-123.pdf")
```

El documento debe empezar por `%PDF-`; también se acepta un objeto de archivo binario.

### 3. Envíos (`client.shipments`)
*   `shipments.get(shipment_id)`: Obtiene toda la información de tracking de un envío.

### 4. Publicaciones (`client.items`)
*   `items.create(body)`: Publica un nuevo producto.
*   `items.get(item_id)`: Detalle completo de una publicación.
*   `items.update(item_id, body)`: Actualización masiva de campos.
*   `items.update_price(item_id, nuevo_precio)`: Actualiza el precio del producto.
*   `items.update_stock(item_id, nuevo_stock)`: Actualiza el stock disponible.
*   `items.get_visits(item_id)`: Cantidad de visitas de una publicación.
*   `items.iter_all(seller_id=None, *, page_size=100, extra_params=None)`: Generador que recorre los
    IDs de todas las publicaciones con `search_type=scan`. El `scroll_id` caduca a los 5 minutos, así
    que consúmelo sin pausas largas.
*   `items.get_many(item_ids, *, attributes=None, include_errors=False)`: Descarga los detalles en
    lotes de 20 IDs y conserva el orden de entrada.

```python
from itertools import islice

# Primeras 100 publicaciones, para no mantener el scroll abierto demasiado tiempo
ids = list(islice(client.items.iter_all(), 100))
items = client.items.get_many(
    ids, attributes=["id", "title", "price", "available_quantity"]
)
```

`get_many` descarta por defecto las entradas con error; pasa `include_errors=True` para recibir
también los `{"code", "body"}` fallidos. El SDK siempre solicita el atributo `id`, aunque no lo
incluyas en `attributes`, para poder conservar el orden de entrada.

### 5. Métricas e Inteligencia (`client.metrics`)
*   `metrics.get_seller_info(seller_id=None)`: Datos públicos del vendedor.
*   `metrics.get_seller_reputation(seller_id=None)`: Termómetro de reputación (reclamos, cancelaciones, retrasos).
*   `metrics.get_item_reviews(item_id)`: Calificaciones por estrellas y comentarios de productos.
*   `metrics.get_trends(site_id, category_id=None)`: Palabras clave más buscadas en un país (ej. `MCO`) o categoría.
*   `metrics.get_questions(seller_id=None, item_id=None, status=None)`: Preguntas recibidas por el vendedor.

---

## Control de Errores

El módulo define excepciones claras que heredan de `MeliError`:

```python
from meli_sdk.exceptions import MeliAPIError, MeliTokenExpiredError

try:
    client.items.update_price("MCO999999", 5000)
except MeliAPIError as e:
    print(f"Error del API ({e.status_code}): {e.message} | Código: {e.error_code}")
except MeliTokenExpiredError:
    print("El refresh token ha expirado. Es necesario re-autenticar la aplicación manualmente.")
```

---

## Créditos y Contribuciones

*   **Autor**: Camilo Andrés Rodríguez
*   **Portal de Desarrolladores**: [Mercado Libre Developers](https://developers.mercadolibre.com/)

---

## Licencia

Este proyecto está bajo la Licencia [MIT](LICENSE).
