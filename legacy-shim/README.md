# MeliAPIClient (obsoleto)

> **Este paquete ahora se llama [`meli-python-sdk`](https://pypi.org/project/meli-python-sdk/).**
> `MeliAPIClient` ya no recibirá actualizaciones.

```bash
pip uninstall MeliAPIClient
pip install meli-python-sdk
```

```python
# Antes
from MeliAPIClient import MeliClient

# Después
from meli_sdk import MeliClient
```

La versión 0.1.0 de `MeliAPIClient` solo instala `meli-python-sdk`, reexporta sus nombres y emite un
`FutureWarning` al importarse. Consulta el
[README de `meli-sdk`](https://github.com/camilordz1/meli-sdk#readme) para la guía de uso.

SDK **no oficial**: este proyecto no está afiliado ni respaldado por Mercado Libre.
