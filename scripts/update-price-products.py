import json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]

OUTPUT = BASE / "docs" / "data" / "price-products.json"


def save_json(path, data):

    with open(path, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def build_initial_dataset():

    dataset = {

        "updated_at": datetime.utcnow().isoformat(),

        "source": "manual_seed",

        "products": [

            {
                "product": "Tej 1,5%",
                "category": "Tejtermék",
                "prices": {}
            },

            {
                "product": "Tojás (10 db)",
                "category": "Frissáru",
                "prices": {}
            },

            {
                "product": "Csirkemellfilé",
                "category": "Húsáru",
                "prices": {}
            },

            {
                "product": "Burgonya",
                "category": "Zöldség",
                "prices": {}
            },

            {
                "product": "Banán",
                "category": "Gyümölcs",
                "prices": {}
            }

        ]
    }

    save_json(OUTPUT, dataset)

    print("Price product dataset initialized")


if __name__ == "__main__":

    build_initial_dataset()
