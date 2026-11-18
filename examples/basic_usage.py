import os
from dotenv import load_dotenv
from meli_sdk import Session, Order, Bill
from meli_sdk.exceptions import MeliAPIError


def run():
    # Cargar variables de entorno al ejecutar el ejemplo
    load_dotenv()
    print("=== Inicializando Sesión ===")
    try:
        session = Session(
            os.getenv("ML_KEYS_PATH", "ml_keys.json"),
            os.getenv("ML_TOKEN_PATH", "ml_token.json"),
            os.getenv("ML_USER_PATH", "ml_user.json"),
        )
        orders_client = Order(session)
        bills_client = Bill(session)
        print("✓ Sesión inicializada con éxito.\n")
    except Exception as e:
        print(f"✗ Error al inicializar sesión: {e}")
        return

    print("=== Listando Órdenes (Junio 2026) ===")
    try:
        response = orders_client.list(year=2026, month=6)
        results = response.get("results", [])
        total = response.get("paging", {}).get("total", 0)
        print(f"Total de órdenes encontradas: {total}")
        print(f"Mostrando las primeras {len(results)} órdenes:")
        print("-" * 80)
        print(f"{'ID Orden':<18} | {'Comprador':<15} | {'Monto':<10} | {'Estado':<10} | {'Pack ID':<18}")
        print("-" * 80)
        for order in results[:5]:
            order_id = order.get("id")
            buyer = order.get("buyer", {}).get("nickname", "N/A")
            total_amount = order.get("total_amount", 0)
            currency = order.get("currency_id", "")
            status = order.get("status", "N/A")
            pack_id = order.get("pack_id", "N/A")
            print(f"{order_id:<18} | {buyer:<15} | {total_amount:<10} {currency} | {status:<10} | {pack_id}")
        print("-" * 80 + "\n")
        
        if results:
            first_order = results[0]
            first_order_id = first_order.get("id")
            first_pack_id = first_order.get("pack_id")
            
            print(f"=== Detalle de la Orden {first_order_id} ===")
            order_detail = orders_client.info(first_order_id)
            print(f"ID: {order_detail.get('id')}")
            print(f"Fecha de Creación: {order_detail.get('date_created')}")
            print(f"Etiquetas: {', '.join(order_detail.get('tags', []))}\n")
            
            print(f"=== Información de Facturación para la Orden {first_order_id} ===")
            try:
                billing_info = bills_client.info(first_order_id)
                print(f"Información de facturación recibida con éxito.")
                # Imprimir un resumen de los campos más importantes
                billing_doc = billing_info.get("billing_info", {}).get("doc_number", "N/A")
                billing_name = billing_info.get("billing_info", {}).get("doc_name", "N/A")
                print(f"Documento: {billing_doc} | Nombre: {billing_name}")
            except MeliAPIError as e:
                print(f"No se pudo obtener información de facturación: {e.message} (HTTP {e.status_code})")
            print()
            
            if first_pack_id:
                print(f"=== Verificación de Documento Fiscal para el Pack {first_pack_id} ===")
                try:
                    has_doc = bills_client.documents(first_pack_id)
                    print(f"¿Tiene documento fiscal asociado?: {'SÍ' if has_doc else 'NO'}")
                except MeliAPIError as e:
                    print(f"Error al verificar documento fiscal: {e.message} (HTTP {e.status_code})")
                print()

    except MeliAPIError as e:
        print(f"✗ Error de la API de Mercado Libre: {e.message} (Código: {e.error_code}, HTTP {e.status_code})")
    except Exception as e:
        print(f"✗ Error inesperado durante la ejecución: {e}")


if __name__ == "__main__":
    run()

