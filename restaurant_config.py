"""
Configuration Family Food - Facile à modifier
Tout ce qui concerne le restaurant est centralisé ici
"""

RESTAURANT_NAME = "Family Food"

RESTAURANT_DATA = {
    "info": {
        "nom": "Family Food",
        "type": "Fast-Food Halal",
        "adresse": "Chanteloup-en-Brie, 77600",
        "telephone": "+33939037161",
        "email": "contact@familyfood.fr",
        "horaires": "12h-14h30 / 19h-23h",
        "description": "Fast-food halal spécialisé en burgers, tacos et sandwichs"
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
            {"nom": "Frites", "prix": 3.50, "desc": "Portion normale"},
            {"nom": "Grandes Frites", "prix": 4.50, "desc": "Grande portion"},
            {"nom": "Nuggets 6", "prix": 5.00, "desc": "6 nuggets de poulet"},
            {"nom": "Onion Rings", "prix": 4.50, "desc": "Rondelles d'oignons panées"},
            {"nom": "Salade", "prix": 3.00, "desc": "Salade verte"}
        ],

        "boissons": [
            {"nom": "Coca 33cl", "prix": 2.50, "desc": "Coca-Cola"},
            {"nom": "Sprite 33cl", "prix": 2.50, "desc": "Sprite"},
            {"nom": "Fanta 33cl", "prix": 2.50, "desc": "Fanta Orange"},
            {"nom": "Ice Tea 33cl", "prix": 2.50, "desc": "Thé glacé pêche"},
            {"nom": "Eau 50cl", "prix": 2.00, "desc": "Eau minérale"}
        ],

        "desserts": [
            {"nom": "Tiramisu", "prix": 4.00, "desc": "Tiramisu maison"},
            {"nom": "Brownie", "prix": 3.50, "desc": "Brownie chocolat"},
            {"nom": "Muffin", "prix": 3.00, "desc": "Muffin au choix"}
        ]
    },

    "menus": {
        "Menu Burger": {
            "prix": 12.50,
            "contenu": ["Burger au choix", "Frites", "Boisson"],
            "desc": "Burger + Frites + Boisson"
        },
        "Menu Tacos": {
            "prix": 10.50,
            "contenu": ["Tacos au choix", "Frites", "Boisson"],
            "desc": "Tacos + Frites + Boisson"
        },
        "Menu Enfant": {
            "prix": 7.50,
            "contenu": ["Nuggets 6", "Petites Frites", "Boisson", "Surprise"],
            "desc": "Menu pour les enfants"
        }
    },

    "services": {
        "livraison": {
            "frais": 2.50,
            "temps": "25-35 minutes",
            "minimum": 12.00,
            "zone": "Chanteloup-en-Brie + 5km",
            "gratuit_si": 30.00  # Livraison gratuite au-dessus de 30€
        },
        "emporter": {
            "reduction": 10,  # %
            "temps": "15-20 minutes",
            "desc": "Remise de 10% sur toutes les commandes à emporter"
        },
        "sur_place": {
            "temps": "10-15 minutes",
            "desc": "Service à table"
        }
    },

    "sauces": [
        "Blanche",
        "Harissa",
        "Algérienne",
        "Barbecue",
        "Mayo",
        "Ketchup",
        "Curry",
        "Samouraï",
        "Andalouse"
    ],

    "paiements": [
        "Espèces",
        "Carte Bancaire",
        "Ticket Restaurant"
    ],

    "promotions": [
        {
            "nom": "Happy Hour",
            "desc": "-20% sur tous les burgers de 14h à 16h",
            "horaires": "14h-16h",
            "jours": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
        },
        {
            "nom": "Menu Étudiant",
            "desc": "Menu complet à 9€ avec carte étudiante",
            "condition": "Sur présentation carte étudiante"
        }
    ],

    "options": {
        "supplement_fromage": 1.00,
        "supplement_bacon": 1.50,
        "supplement_oeuf": 1.00,
        "sans_oignons": 0.00,
        "sans_tomate": 0.00,
        "pain_sans_gluten": 1.50
    }
}


# ===== FONCTIONS UTILITAIRES =====

def get_item_by_name(item_name):
    """Recherche un article dans le menu par son nom"""
    item_name_lower = item_name.lower()

    for category, items in RESTAURANT_DATA["menu"].items():
        for item in items:
            if item_name_lower in item["nom"].lower():
                return {
                    **item,
                    "category": category
                }

    return None


def get_category_items(category):
    """Récupère tous les articles d'une catégorie"""
    return RESTAURANT_DATA["menu"].get(category, [])


def calculate_total(items, delivery_type="sur_place"):
    """
    Calcule le total d'une commande

    Args:
        items: Liste des articles avec quantités
        delivery_type: "livraison", "emporter", ou "sur_place"

    Returns:
        float: Total de la commande
    """
    subtotal = 0

    for item in items:
        price = item.get("prix", 0)
        quantity = item.get("qty", 1)
        subtotal += price * quantity

    # Appliquer la réduction emporter
    if delivery_type == "emporter":
        reduction = RESTAURANT_DATA["services"]["emporter"]["reduction"]
        subtotal = subtotal * (1 - reduction / 100)

    # Ajouter les frais de livraison
    if delivery_type == "livraison":
        frais = RESTAURANT_DATA["services"]["livraison"]["frais"]
        gratuit_si = RESTAURANT_DATA["services"]["livraison"]["gratuit_si"]

        if subtotal < gratuit_si:
            subtotal += frais

    return round(subtotal, 2)


def is_delivery_available(address=None, total=0):
    """Vérifie si la livraison est disponible"""
    min_order = RESTAURANT_DATA["services"]["livraison"]["minimum"]

    if total < min_order:
        return False, f"Commande minimum de {min_order}€ pour la livraison"

    # Ici vous pouvez ajouter une vérification de zone géographique
    # Pour l'instant, on accepte tout
    return True, "Livraison disponible"


def get_menu_text():
    """Génère un texte du menu pour l'IA"""
    menu_text = []

    for category, items in RESTAURANT_DATA["menu"].items():
        menu_text.append(f"\n{category.upper()}:")
        for item in items[:5]:  # Limiter à 5 items par catégorie
            menu_text.append(f"  • {item['nom']}: {item['prix']}€")

    return "\n".join(menu_text)


def format_order_summary(items, delivery_type, client_info, payment_method):
    """Formate un résumé de commande lisible"""
    summary = []
    summary.append(f"=== COMMANDE {RESTAURANT_NAME} ===\n")

    # Articles
    summary.append("ARTICLES:")
    for item in items:
        qty = item.get("qty", 1)
        name = item.get("nom", "Article")
        price = item.get("prix", 0)
        summary.append(f"  {qty}x {name} - {price * qty}€")

        if item.get("sauce"):
            summary.append(f"     Sauce: {item['sauce']}")

    # Total
    total = calculate_total(items, delivery_type)
    summary.append(f"\nTOTAL: {total}€")

    # Type de commande
    summary.append(f"\nTYPE: {delivery_type.upper()}")

    # Infos client
    summary.append(f"\nCLIENT:")
    summary.append(f"  Nom: {client_info.get('name', 'N/A')}")
    summary.append(f"  Téléphone: {client_info.get('phone', 'N/A')}")

    if delivery_type == "livraison":
        summary.append(f"  Adresse: {client_info.get('address', 'N/A')}")

    # Paiement
    summary.append(f"\nPAIEMENT: {payment_method}")

    # Temps d'attente
    temps = RESTAURANT_DATA["services"][delivery_type]["temps"]
    summary.append(f"\nTEMPS ESTIMÉ: {temps}")

    summary.append(f"\n{'=' * 40}")

    return "\n".join(summary)


# ===== VALIDATION =====

if __name__ == "__main__":
    # Test de la configuration
    print("🍔 Configuration Family Food")
    print(f"Restaurant: {RESTAURANT_NAME}")
    print(f"Type: {RESTAURANT_DATA['info']['type']}")
    print(f"Adresse: {RESTAURANT_DATA['info']['adresse']}")
    print(f"\nCatégories du menu: {', '.join(RESTAURANT_DATA['menu'].keys())}")
    print(f"Nombre total d'articles: {sum(len(items) for items in RESTAURANT_DATA['menu'].values())}")
    print(f"Sauces disponibles: {len(RESTAURANT_DATA['sauces'])}")
    print("\n✅ Configuration valide !")