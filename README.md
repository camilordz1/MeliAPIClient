# MeliAPIClient

`MeliAPIClient` es un cliente moderno y robusto para interactuar con la API de Mercado Libre en Python. Diseñado con una arquitectura modular basada en composición, soporta el manejo de múltiples sesiones concurrentes, renovación automática de tokens, y almacenamiento flexible de credenciales (archivos locales, memoria o bases de datos), manteniendo el 100% de compatibilidad con desarrollos antiguos.

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
pip install MeliAPIClient
```

---

## Uso Básico (Interfaz Clásica)

Si ya tienes un script que utiliza el formato tradicional de tres archivos JSON (`ml_keys.json`, `ml_token.json`, `ml_user.json`), puedes continuar usándolo exactamente igual. El módulo renovará automáticamente el token de acceso usando el motor moderno de fondo.

```python
from MeliAPIClient import Session, Order, Bill, Ship

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
from MeliAPIClient import MeliClient, FileTokenStorage

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

---

## Persistencia en Bases de Datos (Estrategia `CallbackTokenStorage`)

Si quieres guardar los tokens de acceso en una base de datos (por ejemplo, en un modelo de Django, SQLAlchemy, o en Redis) en lugar de archivos JSON locales, utiliza `CallbackTokenStorage` inyectando funciones de carga y guardado:

```python
from MeliAPIClient import MeliClient, CallbackTokenStorage

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

## Guía de Recursos Disponibles

### 1. Órdenes (`client.orders`)
*   `orders.get(order_id)`: Obtiene el detalle de una orden.
*   `orders.search(seller_id=None, year=None, month=None)`: Busca órdenes de un periodo de tiempo.
*   `orders.get_pack(pack_id)`: Obtiene información de un paquete de envíos.

### 2. Facturas (`client.bills`)
*   `bills.get_billing_info(order_id)`: Detalles de facturación del cliente.
*   `bills.has_fiscal_document(pack_id)`: Verifica si el paquete tiene factura adjunta.
*   `bills.upload_fiscal_document(pack_id, file_path)`: Sube una factura en formato PDF.

### 3. Envíos (`client.shipments`)
*   `shipments.get(shipment_id)`: Obtiene toda la información de tracking de un envío.

### 4. Publicaciones (`client.items`)
*   `items.create(body)`: Publica un nuevo producto.
*   `items.get(item_id)`: Detalle completo de una publicación.
*   `items.update(item_id, body)`: Actualización masiva de campos.
*   `items.update_price(item_id, nuevo_precio)`: Actualiza el precio del producto.
*   `items.update_stock(item_id, nuevo_stock)`: Actualiza el stock disponible.
*   `items.get_visits(item_id)`: Cantidad de visitas de una publicación.

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
from MeliAPIClient.exceptions import MeliAPIError, MeliTokenExpiredError

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
