# Registro de cambios

Todos los cambios relevantes de `meli-sdk` se documentan aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[versionado semántico](https://semver.org/lang/es/). Mientras el SDK esté en versión alfa
(`1.0.0aN`), una versión nueva puede traer cambios incompatibles.

## [Sin publicar]

### Añadido
- `MeliClient` acepta `timeout=` (un número o una tupla `(conexión, lectura)`) y `session=` para
  inyectar una `requests.Session` compartida; un `timeout` por llamada sobrescribe el valor del
  cliente.
- `MeliClient.close()` y el protocolo de context manager (`with MeliClient(...) as client:`) para
  cerrar la sesión cuando el cliente es su dueño.
- Reintentos automáticos y seguros: `429` para todos los métodos, `500`/`502`/`503`/`504` y errores
  de conexión solo para métodos idempotentes, con backoff exponencial y soporte de `Retry-After`
  (`max_retries`, `backoff_factor` y `max_backoff` configurables).

### Corregido
- Las peticiones y la renovación del token usan una `requests.Session` persistente y un timeout
  por defecto de 30 segundos.

## [1.0.0a1] - sin publicar

### Añadido
- Arnés de pruebas con pytest y `responses`, con pruebas de caracterización para transporte,
  tokens, facturas, órdenes y publicaciones. Los errores conocidos quedan registrados como
  `xfail(strict=True)` hasta que se corrijan.
- Distribución de compatibilidad `MeliAPIClient` 0.1.0, que reexporta `meli_sdk`, conserva los
  imports antiguos de submodules y emite un `FutureWarning`.
- Integración continua con GitHub Actions: ruff, pytest en Python 3.10 y 3.13, construcción del
  wheel y smoke tests del paquete y del shim.
- `pyproject.toml` con metadatos PEP 621, layout `src/`, marcador `py.typed` y extra `dev`.
- Configuración de ruff y licencia SPDX (`license = "MIT"`).

### Cambiado
- El paquete se renombra de `MeliAPIClient` a `meli-sdk` y el nombre de importación pasa a ser
  `meli_sdk`.
- El ejemplo de uso se mueve a `examples/basic_usage.py`.

### Cambios incompatibles
- `from MeliAPIClient import ...` deja de funcionar; hay que usar `from meli_sdk import ...`.
  La distribución `MeliAPIClient` 0.1.0 solo existe para señalar el cambio, no para mantener la
  API anterior.

### Corregido
- El SDK ya no carga el archivo `.env` del directorio actual al importarse. Solo la `Session`
  clásica lo lee, de forma perezosa, cuando faltan las claves o el token.
