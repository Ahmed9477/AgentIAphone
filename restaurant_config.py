"""Configuration Family Food - Facile à modifier"""
RESTAURANT_NAME = "Family Food"
RESTAURANT_DATA = {
    "info": {
        "nom": "Family Food",
        "type": "Fast-Food Halal",
        "adresse": "Chanteloup-en-Brie, 77600",
        "telephone": "+33767021139",
        "email": "contact@familyfood.fr",
        "horaires": "12h-14h30 / 19h-23h"
    },

    "menu": {
        "burgers": [
            {"nom": "Classic Burger", "prix": 8.50, "desc": "Boeuf, salade, tomate"},
            {"nom": "Cheeseburger", "prix": 9.00, "desc": "Boeuf, cheddar fondu"},
            {"nom": "Bacon Burger", "prix": 10.50, "desc": "Boeuf, bacon croustillant"},
            {"nom": "Chicken Burger", "prix": 9.50, "desc": "Poulet pané croustillant"},
            {"nom": "Fish Burger", "prix": 9.00, "desc": "Filet de poisson pané"},
            {"nom": "Veggie Burger", "prix": 8.50, "desc": "Steak végétarien"}
        ],
        "tacos": [
            {"nom": "Tacos Poulet", "prix": 7.50, "desc": "Poulet, frites, sauce"},
            {"nom": "Tacos Viande", "prix": 7.50, "desc": "Boeuf haché, frites"},
            {"nom": "Tacos Mixte", "prix": 8.50, "desc": "Poulet + viande"},
            {"nom": "Tacos Cordon Bleu", "prix": 8.00, "desc": "Cordon bleu émietté"},
            {"nom": "Tacos XXL", "prix": 12.00, "desc": "Double portion + fromage"}
        ],
        "sandwichs": [
            {"nom": "Panini Poulet", "prix": 6.50, "desc": "Poulet, fromage"},
            {"nom": "Panini Jambon", "prix": 6.00, "desc": "Jambon, emmental"},
            {"nom": "Sandwich Américain", "prix": 7.00, "desc": "Boeuf, oignons"},
            {"nom": "Kebab", "prix": 7.50, "desc": "Pain libanais, kebab, salade"}
        ],
        "accompagnements": [
            {"nom": "Frites", "prix": 3.50},
            {"nom": "Grandes Frites", "prix": 4.50},
            {"nom": "Nuggets 6", "prix": 5.00},
            {"nom": "Onion Rings", "prix": 4.50},
            {"nom": "Salade", "prix": 3.00}
        ],
        "boissons": [
            {"nom": "Coca 33cl", "prix": 2.50},
            {"nom": "Sprite 33cl", "prix": 2.50},
            {"nom": "Eau 50cl", "prix": 2.00}
        ]
    },

    "services": {
        "livraison": {
            "frais": 2.50,
            "temps": "25-35 minutes",
            "minimum": 12.00,
            "zone": "Chanteloup + 5km"
        },
        "emporter": {
            "reduction": 10,  # %
            "temps": "15-20 minutes"
        }
    },

    "sauces": [
        "Blanche", "Harissa", "Algérienne", "Barbecue", "Mayo", "Ketchup"
    ],

    "paiements": ["Espèces", "Carte Bancaire", "Lydec Pay"]
}
