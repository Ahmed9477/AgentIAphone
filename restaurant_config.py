"""
Configuration Family Food - Version CSV
Lit TOUTES les données depuis data.csv
"""

import pandas as pd
import os
from datetime import datetime

# Chemins des fichiers
MENU_CSV_PATH = "data.csv"

# Configuration générale (toujours fixe)
RESTAURANT_NAME = "FAMILY FOOD"

# Charger le CSV menu principal
def load_menu_from_csv():
    """Charge le menu depuis le CSV optimisé pour IA"""
    if not os.path.exists(MENU_CSV_PATH):
        print(f"❌ Fichier {MENU_CSV_PATH} introuvable!")
        return []

    try:
        df = pd.read_csv(MENU_CSV_PATH)

        # Normaliser les noms de colonnes (enlever espaces, minuscules)
        df.columns = df.columns.str.strip().str.lower()

        # Afficher les colonnes détectées
        print(f"✅ Menu CSV chargé: {len(df)} articles")
        print(f"📋 Colonnes détectées: {', '.join(df.columns.tolist())}")

        # Afficher les 3 premiers articles pour debug
        if len(df) > 0:
            print(f"📝 Exemples d'articles:")
            for idx, row in df.head(3).iterrows():
                nom = row.get('nom_affiche', 'N/A')
                prix = row.get('prix_unitaire', 'N/A')
                cat = row.get('categorie', 'N/A')
                print(f"   • {nom} - {prix}€ ({cat})")

        return df.to_dict('records')
    except Exception as e:
        print(f"❌ Erreur lecture CSV: {e}")
        import traceback
        traceback.print_exc()
        return []

MENU_DATA = load_menu_from_csv()

# ===== INFOS RESTAURANT (fixe, mais modifiable) =====
RESTAURANT_DATA = {
    "info": {
        "nom": "Family Food",
        "type": "Fast-Food Halal",
        "adresse": "Chanteloup-en-Brie, 77600",
        "telephone": "+33939037161",
        "email": "contact@familyfood.fr",
        "horaires": "12h-14h30 / 19h-23h",
        "description": "Fast-food halal spécialisé pizzas, burgers, tacos"
    },

    "services": {
        "livraison": {
            "frais": 3.00,
            "temps": "25-35 minutes",
            "minimum": 15.00,
            "zone": "Serris + 5km",
            "gratuit_si": 30.00
        },
        "emporter": {
            "reduction": 10,
            "temps": "15-20 minutes",
            "desc": "Remise 10%"
        },
        "sur_place": {
            "temps": "10-15 minutes",
            "desc": "Service rapide"
        }
    },

    "paiements": ["Espèces", "Carte Bancaire", "Lydia", "Ticket Restaurant"],

    "sauces": [
        "Blanche", "Harissa", "Algérienne", "Barbecue", "Mayo",
        "Ketchup", "Curry", "Samouraï", "Andalouse", "Miel Moutarde"
    ],

    "options": {
        "supplement_fromage": 1.00,
        "supplement_bacon": 1.50,
        "supplement_oeuf": 1.00,
        "extra_viande": 2.00,
        "pain_blonde": 0.50,
        "pain_supreme": 0.50
    },

    "promotions": [
        {"nom": "Livraison gratuite", "condition": ">=30€", "reduction": "100% frais"},
        {"nom": "Menu Étudiant", "desc": "-1€ sur tous les menus"}
    ]
}

# ===== FONCTIONS UTILITAIRES CSV =====

def get_item_by_name(item_name):
    """Recherche un article dans le CSV par nom ou synonymes"""
    if not MENU_DATA:
        return None

    item_name_lower = item_name.lower().strip()

    # Recherche exacte ou partielle
    for item in MENU_DATA:
        # Recherche par nom_affiche
        nom_affiche = str(item.get("nom_affiche", "")).lower().strip()

        # Match exact ou contient
        if item_name_lower == nom_affiche or item_name_lower in nom_affiche or nom_affiche in item_name_lower:
            return item

        # Recherche par synonymes (séparés par ;)
        synonymes = str(item.get("nom_synonymes", "")).lower().strip()
        if synonymes:
            # Diviser par ; et nettoyer
            syn_list = [s.strip() for s in synonymes.split(';')]
            for syn in syn_list:
                if syn and (item_name_lower == syn or item_name_lower in syn or syn in item_name_lower):
                    return item

    return None

def get_category_items(category):
    """Récupère tous les articles d'une catégorie"""
    return [item for item in MENU_DATA if item.get("categorie") == category]

def search_items(query):
    """Recherche floue dans le menu"""
    results = []
    query_lower = query.lower()

    for item in MENU_DATA:
        nom = str(item.get("nom_affiche", "")).lower()
        desc = str(item.get("description_courte", "")).lower()

        if query_lower in nom or query_lower in desc:
            results.append(item)

    return results[:5]

def get_all_categories():
    """Retourne toutes les catégories disponibles"""
    categories = set()
    for item in MENU_DATA:
        cat = item.get("categorie", "autre")
        if cat:
            categories.add(cat)
    return sorted(list(categories))

def get_sauces_by_category(category):
    """Récupère les sauces compatibles avec une catégorie"""
    if category in ["tacos", "sandwich", "burger"]:
        return RESTAURANT_DATA["sauces"]
    return ["Blanche", "Ketchup", "Mayo"]

def calculate_total(items, delivery_type="sur_place"):
    """Calcule le total depuis les données CSV"""
    subtotal = 0

    for item in items:
        menu_item = get_item_by_name(item.get("nom", ""))
        price = menu_item.get("prix_unitaire", 0) if menu_item else item.get("prix", 0)
        qty = item.get("qty", 1)
        subtotal += float(price) * qty

    if delivery_type == "emporter":
        subtotal *= (1 - RESTAURANT_DATA["services"]["emporter"]["reduction"] / 100)

    if delivery_type == "livraison":
        frais = RESTAURANT_DATA["services"]["livraison"]["frais"]
        gratuit_si = RESTAURANT_DATA["services"]["livraison"]["gratuit_si"]
        if subtotal < gratuit_si:
            subtotal += frais

    return round(subtotal, 2)

def build_menu_context():
    """Construit le contexte menu à partir du CSV"""
    categories = get_all_categories()
    menu_text = []

    for cat in categories[:8]:
        items = get_category_items(cat)[:3]
        if items:
            cat_name = cat.replace("_", " ").title()
            menu_items = [f"{i['nom_affiche']} ({i['prix_unitaire']}€)" for i in items]
            menu_text.append(f"• {cat_name}: {', '.join(menu_items)}")

    sauces = ", ".join(RESTAURANT_DATA["sauces"][:10])

    return f"""
📋 MENU DISPONIBLE (extrait):
{chr(10).join(menu_text)}

🌶️ SAUCES: {sauces}

📂 CATÉGORIES COMPLÈTES: {', '.join(categories)}

💰 SERVICES:
• Livraison: +{RESTAURANT_DATA['services']['livraison']['frais']}€ (min {RESTAURANT_DATA['services']['livraison']['minimum']}€)
• À emporter: -{RESTAURANT_DATA['services']['emporter']['reduction']}%
• Sur place: service rapide

IMPORTANT: 
- Les articles avec prix_menu peuvent être pris en MENU (+boisson)
- Exemple: Kebab seul = 6€ | Menu Kebab = 9€ (avec boisson)
- Toujours proposer le menu si disponible (peut_etre_menu = true)
"""

def get_menu_text():
    """Texte complet du menu pour affichage"""
    menu_text = []
    for cat in get_all_categories():
        items = get_category_items(cat)
        if items:
            menu_text.append(f"\n{cat.upper()}:")
            for item in items[:5]:
                prix = item.get("prix_unitaire", 0)
                menu_text.append(f"  • {item['nom_affiche']} {prix}€")
    return "\n".join(menu_text)

def format_order_summary(items, delivery_type, client_info, payment_method):
    """Formate le récap depuis CSV"""
    summary = [f"=== COMMANDE {RESTAURANT_NAME} ===\n"]

    for item in items:
        menu_item = get_item_by_name(item.get("nom", ""))
        nom = menu_item.get("nom_affiche", item.get("nom", "Article"))
        prix = menu_item.get("prix_unitaire", item.get("prix", 0))
        qty = item.get("qty", 1)
        total_item = float(prix) * qty

        summary.append(f"{qty}x {nom} - {total_item}€")
        if item.get("sauce"):
            summary.append(f"   Sauce: {item['sauce']}")

    total = calculate_total(items, delivery_type)
    summary.append(f"\nTOTAL: {total}€")
    summary.append(f"TYPE: {delivery_type.upper()}")
    summary.append(f"NOM: {client_info.get('name', 'N/A')}")
    summary.append(f"TÉL: {client_info.get('phone', 'N/A')}")

    if delivery_type == "livraison":
        summary.append(f"ADRESSE: {client_info.get('address', 'N/A')}")

    summary.append(f"PAIEMENT: {payment_method}")
    summary.append("\n" + "="*40)

    return "\n".join(summary)

# ===== VALIDATION & TESTS =====
if __name__ == "__main__":
    print("🍔 CONFIGURATION CSV FAMILY FOOD")
    print(f"🏪 {RESTAURANT_NAME}")
    print(f"📊 Articles CSV: {len(MENU_DATA)}")
    print(f"📂 Catégories: {len(get_all_categories())}")
    print(f"🌐 Services: {list(RESTAURANT_DATA['services'].keys())}")

    print("\n🔍 TESTS DE RECHERCHE:")
    test_items = ["kebab", "pizza", "tacos", "burger", "margherita"]

    for item_name in test_items:
        result = get_item_by_name(item_name)
        if result:
            print(f"✅ '{item_name}' trouvé: {result['nom_affiche']} - {result['prix_unitaire']}€ (menu: {result.get('prix_menu', 'N/A')}€)")
        else:
            print(f"❌ '{item_name}' NON TROUVÉ")

    print(f"\n📋 Aperçu menu:\n{get_menu_text()[:500]}...")
    print("\n✅ Configuration CSV VALIDE !")