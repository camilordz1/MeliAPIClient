from MeliAPIClient import Session
from MeliAPIClient import Order
from MeliAPIClient import Bill


def run():

    session = Session("ml_keys.json", 'ml_token.json', "ml_user.json")
    orders = Order(session)
    bills = Bill(session)

    print(orders.list(year=2024, month=5))
    bills()

if __name__ == "__main__":
    run()
