from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
import json
from datetime import datetime
import os
from dotenv import load_dotenv

# Import depuis restaurant_config_csv.py
from restaurant_config import (
    RESTAURANT_NAME,
    RESTAURANT_DATA,
    MENU_DATA,
    get_item_by_name,
    get_category_items,
    search_items,
    get_all_categories,
    calculate_total,
    build_menu_context,
    format_order_summary
)

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEMORY_TIMEOUT = int(os.getenv("MEMORY_TIMEOUT", "1800"))  # 30 minutes

# Initialiser OpenAI
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ Client OpenAI initialisé avec succès")
except Exception as e:
    print(f"❌ Erreur lors de l'initialisation OpenAI: {e}")
    client = None

# Stockage des conversations avec timestamps
conversations = {}  # {call_sid: [{"role": str, "content": str, "time": datetime}]}


# ==================== FONCTIONS UTILITAIRES ====================

def cleanup_old_conversations():
    """Nettoie les conversations expirées ou trop longues"""
    now = datetime.now()
    to_delete = []

    for call_sid, conv in conversations.items():
        if not conv:
            to_delete.append(call_sid)
            continue

        # Supprimer si conversation trop longue (plus de 50 messages)
        if len(conv) > 50:
            to_delete.append(call_sid)
            continue

        # Supprimer si dernier message trop ancien (30 minutes)
        last_message_time = conv[-1].get("time", now)
        if (now - last_message_time).seconds > MEMORY_TIMEOUT:
            to_delete.append(call_sid)

    for sid in to_delete:
        print(f"🗑️  Nettoyage conversation: {sid}")
        del conversations[sid]

    if to_delete:
        print(f"✅ {len(to_delete)} conversation(s) nettoyée(s)")


def detect_conversation_stage(history):
    """Détecte automatiquement l'étape de la conversation"""
    # Compter les messages
    num_messages = len(history)

    # Analyser le contenu pour détecter l'étape
    user_messages = [msg["content"].lower() for msg in history if msg["role"] == "user"]
    assistant_messages = [msg["content"].lower() for msg in history if msg["role"] == "assistant"]

    # Si on a demandé le paiement, on est en finalisation
    if any("espèces" in msg or "carte" in msg or "ticket" in msg for msg in assistant_messages[-3:]):
        return "finalisation"

    # Si on a demandé nom/téléphone/adresse, on est en infos_client
    if any("nom" in msg or "téléphone" in msg or "adresse" in msg for msg in assistant_messages[-3:]):
        return "infos_client"

    # Si on a demandé sur place/emporter/livraison
    if any("sur place" in msg or "emporter" in msg or "livraison" in msg for msg in assistant_messages[-3:]):
        return "livraison"

    # Sinon on est en commande
    return "commande"


def extract_order_summary(history):
    """Extrait un résumé des articles commandés"""
    if not history:
        return "Nouvelle commande"

    # Extraire tous les articles mentionnés par l'utilisateur
    ordered_items = []

    for i, msg in enumerate(history):
        if msg["role"] == "user":
            content = msg["content"].lower()

            # Détecter les mots-clés d'articles
            keywords = ["kebab", "pizza", "burger", "tacos", "salade", "pâtes", "panini",
                        "dessert", "milkshake", "crêpe", "tarte", "coca", "fanta", "sprite"]

            for keyword in keywords:
                if keyword in content:
                    ordered_items.append(keyword)

    if ordered_items:
        summary = f"Articles: {', '.join(set(ordered_items))}"
        return summary[:100]

    return "Commande en cours"


def get_ai_response(history, user_input):
    """
    Génère une réponse IA avec mémoire contextuelle depuis le CSV

    Args:
        history: Historique de la conversation
        user_input: Dernier message de l'utilisateur

    Returns:
        str: Réponse de l'assistant
    """

    # Détection automatique de l'étape
    stage = detect_conversation_stage(history)
    order_summary = extract_order_summary(history)

    # Construire le contexte menu depuis le CSV
    menu_context = build_menu_context()

    # Récupérer les sauces depuis la config
    sauces = ", ".join(RESTAURANT_DATA["sauces"][:8]) + "..."

    # Construction du prompt système adaptatif
    system_prompt = f"""Tu es l'assistant vocal de {RESTAURANT_NAME}, {RESTAURANT_DATA['info']['type']}.

📋 CONTEXTE ACTUEL:
• Commande en cours: {order_summary}
• Étape: {stage}
• Historique: {len(history)} messages

{menu_context}

🎯 TON RÔLE - ÉTAPES PRÉCISES:

1. COMMANDE INITIALE:
   - Demander "Que souhaitez-vous commander?"
   - Identifier l'article dans le CSV (utiliser nom_affiche ou synonymes)
   - Si article trouvé ET peut_etre_menu=true → proposer le menu
   - Exemple: "Menu Kebab avec boisson ?" (ne pas donner le prix)

2. POUR CHAQUE ARTICLE:

   A) SI MENU ACCEPTÉ:
   - Sauce: "Quelle sauce?" (UNE SEULE sauce, si client dit plusieurs → demander laquelle choisir)
   - Boisson: "Quelle boisson?" (lister si demandé: Coca 25cl, Coca 50cl, Evian, etc.)
   - Accepter toutes boissons raisonnables (Coca, Ice Tea, Fanta, Sprite, etc.) même si pas dans CSV exact

   B) SI ARTICLE SEUL:
   - Demander uniquement les options pertinentes
   - Pas de boisson si pas menu

3. APRÈS CHAQUE ARTICLE:
   - TOUJOURS dire: "Ça sera tout?" ou "Autre chose?"
   - JAMAIS "Combien voulez-vous?"
   - Si client dit "oui" ou "c'est bon" → passer à la livraison
   - Si client ajoute article → recommencer étape 1

4. TYPE DE COMMANDE:
   - "Sur place, à emporter ou livraison?"

5. INFOS CLIENT:
   - Nom
   - Téléphone
   - Si livraison: Adresse complète

6. PAIEMENT (OBLIGATOIRE):
   - "Espèces, carte ou ticket restaurant?"

7. RÉCAPITULATIF FINAL (TRÈS IMPORTANT):
   - AVANT de dire le récap, RELIS TOUTE la conversation pour identifier TOUS les articles
   - Lister TOUS les articles commandés dans l'ordre chronologique
   - Pour chaque article mentionner:
     * Si MENU: "Menu [Article]" + sauce(s) + boisson
     * Si SEUL: "[Article]" + détails
   - Calculer le VRAI total en additionnant TOUS les prix de TOUS les articles
   - Ne JAMAIS oublier un article qui a été commandé plus tôt dans la conversation

   EXEMPLE DE RÉCAP COMPLET:
   "Menu Kebab sauce algérienne Ice Tea, Menu Pizza Orientale Coca, Tarte Tatin. Sur place. Total 24.50€. Jafar 0767021139, espèces. Merci! Prêt dans 15 minutes. END_CALL"

   ⚠️ CRITIQUE: Avant de faire le récap, vérifie mentalement:
   - Combien d'articles différents ont été commandés dans TOUTE la conversation?
   - Est-ce que je les ai TOUS listés dans mon récap?
   - Est-ce que mon total correspond à la somme de TOUS les prix?

✅ RÈGLES STRICTES:
• Maximum 15 mots par réponse (sauf récap final et listes demandées)
• UNE SEULE sauce par sandwich/burger/kebab
• Si client dit plusieurs sauces → demander "Laquelle préférez-vous?"
• Accepter boissons courantes même si pas exact dans CSV (Coca, Ice Tea, Fanta, Sprite, Oasis)
• TOUJOURS se souvenir de TOUS les articles commandés
• RÉCAP FINAL = liste complète de TOUT ce qui a été commandé
• Total = somme de TOUS les prix (menu ou unitaire selon le cas)

🥤 GESTION BOISSONS:
• Menu Kebab = 9€ (avec boisson)
• Menu Burger = prix_menu du burger (avec boisson)
• Menu Tacos = prix_menu du tacos (avec boisson)
• Boisson seule = 2.50€ environ
• Accepter: Coca, Ice Tea, Fanta, Sprite, Oasis, Evian, etc.

🧮 CALCUL TOTAL (EXEMPLE):
Menu Kebab (9€) + Menu Cheese Burger (11.50€) + Milk Shake (4€) = 24.50€

❌ INTERDICTIONS:
• Ne JAMAIS oublier un article commandé dans le récap
• Ne JAMAIS dire "boisson non incluse" si c'est un menu
• Ne JAMAIS calculer un total partiel
• Ne JAMAIS accepter plusieurs sauces (forcer le choix d'UNE seule)
• Ne pas refuser Ice Tea, Fanta, Sprite si client demande

🎤 MÉMOIRE CONVERSATIONNELLE:
Tu DOIS te souvenir de TOUT ce qui a été dit:
- Tous les articles commandés (kebab, burger, dessert, etc.)
- Toutes les sauces choisies
- Toutes les boissons demandées
- Tous les détails de personnalisation

Dans le récap final, LISTE ABSOLUMENT TOUT dans l'ordre chronologique.

SAUCES DISPONIBLES: {sauces}

📝 EXEMPLE PARFAIT:
Client: "Un kebab"
Toi: "Menu avec boisson?"

Client: "Oui"
Toi: "Quelle sauce?"

Client: "Algérienne et barbecue"
Toi: "Désolé, une seule sauce. Algérienne ou barbecue?"

Client: "Algérienne"
Toi: "Quelle boisson?"

Client: "Ice Tea"
Toi: "Parfait. Ça sera tout?"

Client: "Un burger cheese"
Toi: "Menu avec boisson?"

Client: "Oui"
Toi: "Quelle boisson?"

Client: "Coca"
Toi: "Ça sera tout?"

Client: "Un milkshake"
Toi: "Quel parfum?"

Client: "Chocolat"
Toi: "Ça sera tout?"

Client: "Oui"
Toi: "Sur place, emporter ou livraison?"

Client: "Sur place"
Tou: "Votre nom?"

Client: "Jafar"
Toi: "Votre téléphone?"

Client: "0767021139"
Toi: "Espèces ou carte?"

Client: "Espèces"
Toi: "Menu Kebab sauce algérienne Ice Tea, Menu Cheese Burger Coca, Milk Shake chocolat. Sur place. Total 24.50€. Jafar 0767021139, espèces. Merci! Prêt dans 15 minutes. END_CALL"
"""

    # Construction des messages pour l'API
    messages = [{"role": "system", "content": system_prompt}]

    # Ajouter TOUS les messages de l'historique (pas seulement les 10 derniers)
    # pour garantir que l'IA se souvienne de TOUT
    messages.extend([
        {"role": msg["role"], "content": msg["content"]}
        for msg in history
    ])

    # Ajouter le message actuel
    messages.append({"role": "user", "content": user_input})

    try:
        if client is None:
            return "Service temporairement indisponible. Veuillez rappeler."

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=150,  # Augmenté pour le récap final
            timeout=5  # Timeout de 5 secondes
        )

        ai_reply = response.choices[0].message.content.strip()
        ai_reply = ai_reply.replace('"', '').replace('*', '')

        return ai_reply

    except Exception as e:
        print(f"❌ Erreur API OpenAI: {e}")

        fallback_responses = {
            "commande": "Que souhaitez-vous commander?",
            "livraison": "Sur place, emporter ou livraison?",
            "infos_client": "Votre nom et téléphone?",
            "finalisation": "Espèces ou carte?"
        }

        return fallback_responses.get(stage, "Pouvez-vous répéter?")


# ==================== ROUTES VOCALES ====================

@app.route("/voice", methods=["POST"])
def voice():
    """Point d'entrée initial de l'appel"""
    call_sid = request.values.get("CallSid", "unknown")[:8]
    caller = request.values.get("From", "inconnu")

    print(f"\n📞 NOUVEL APPEL - CallSid: {call_sid} - De: {caller}")

    response = VoiceResponse()
    response.say(
        f"Bonjour, bienvenue chez {RESTAURANT_NAME}! Que souhaitez-vous commander?",
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    gather = Gather(
        input="speech",
        language="fr-FR",
        speechTimeout="auto",
        action="/process",
        method="POST",
        hints="pizza burger kebab tacos frites sandwich menu boisson livraison emporter",
        timeout=10
    )

    response.append(gather)
    response.say(
        "Je n'ai pas entendu votre réponse. Au revoir.",
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    return Response(str(response), mimetype="text/xml")


@app.route("/process", methods=["POST"])
def process():
    """Traite chaque réponse vocale du client"""
    speech = request.values.get("SpeechResult", "").strip()
    call_sid = request.values.get("CallSid", "unknown")[:8]
    confidence = request.values.get("Confidence", "0")

    print(f"\n📞 [{call_sid}] 👤 Client: '{speech}' (confiance: {confidence})")

    if not speech:
        response = VoiceResponse()
        response.say(
            "Je n'ai pas compris. Pouvez-vous répéter?",
            language="fr-FR",
            voice="Google.fr-FR-Neural2-B"
        )

        gather = Gather(
            input="speech",
            language="fr-FR",
            speechTimeout="auto",
            action="/process",
            method="POST",
            timeout=10
        )
        response.append(gather)

        return Response(str(response), mimetype="text/xml")

    # Initialiser la conversation si nécessaire
    if call_sid not in conversations:
        conversations[call_sid] = []

    conv = conversations[call_sid]

    # Ajouter le message utilisateur avec timestamp
    conv.append({
        "role": "user",
        "content": speech,
        "time": datetime.now()
    })

    # Obtenir la réponse de l'IA
    ai_reply = get_ai_response(conv[:-1], speech)

    print(f"📞 [{call_sid}] 🤖 Bot: '{ai_reply}'")

    # Ajouter la réponse du bot avec timestamp
    conv.append({
        "role": "assistant",
        "content": ai_reply,
        "time": datetime.now()
    })

    # Vérifier si c'est la fin de la conversation
    should_end = "END_CALL" in ai_reply.upper()

    # Retirer END_CALL de la réponse vocale
    ai_reply_clean = ai_reply.replace("END_CALL", "").replace("end_call", "").strip()

    response = VoiceResponse()
    response.say(
        ai_reply_clean,
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    if should_end:
        print(f"📴 [{call_sid}] ✅ APPEL TERMINÉ - Commande complète")
        response.hangup()
        save_order(call_sid, conv)
    else:
        gather = Gather(
            input="speech",
            language="fr-FR",
            speechTimeout="auto",
            action="/process",
            method="POST",
            timeout=10
        )
        response.append(gather)

        response.say(
            "Êtes-vous toujours là? Au revoir.",
            language="fr-FR",
            voice="Google.fr-FR-Neural2-B"
        )

    cleanup_old_conversations()

    return Response(str(response), mimetype="text/xml")


def save_order(call_sid, conversation):
    """Sauvegarde la commande finale avec extraction CSV"""
    try:
        os.makedirs("orders", exist_ok=True)

        timestamp = datetime.now()
        date_str = timestamp.strftime('%Y%m%d_%H%M%S')

        # 1. Sauvegarder la conversation complète (JSON)
        order_data = {
            "call_sid": call_sid,
            "timestamp": timestamp.isoformat(),
            "conversation": conversation
        }

        filename_json = f"orders/conversation_{call_sid}_{date_str}.json"
        with open(filename_json, 'w', encoding='utf-8') as f:
            json.dump(order_data, f, ensure_ascii=False, indent=2, default=str)

        print(f"💾 Conversation sauvegardée: {filename_json}")

        # 2. Créer bon de commande lisible
        order_summary = extract_order_from_conversation(conversation, call_sid, timestamp)

        filename_txt = f"orders/commande_{call_sid}_{date_str}.txt"
        with open(filename_txt, 'w', encoding='utf-8') as f:
            f.write(order_summary)

        print(f"📄 Bon de commande créé: {filename_txt}")

    except Exception as e:
        print(f"⚠️  Erreur sauvegarde commande: {e}")


def extract_order_from_conversation(conversation, call_sid, timestamp):
    """Extrait les informations de commande depuis la conversation"""
    import re

    # Initialisation des variables
    client_name = ""
    client_phone = ""
    client_address = ""
    delivery_type = ""
    payment_method = ""
    order_items = []
    total = ""
    initial_total = ""
    discount_info = ""

    # Parser la conversation pour extraire les infos
    for i, msg in enumerate(conversation):
        content = msg.get("content", "").lower()

        # Détecter le nom
        if i > 0 and "nom" in conversation[i - 1].get("content", "").lower():
            if msg["role"] == "user":
                client_name = msg["content"]

        # Détecter le téléphone
        if i > 0 and "téléphone" in conversation[i - 1].get("content", "").lower():
            if msg["role"] == "user":
                client_phone = msg["content"]

        # Détecter l'adresse
        if i > 0 and "adresse" in conversation[i - 1].get("content", "").lower():
            if msg["role"] == "user":
                client_address = msg["content"]

        # Détecter le type de commande
        if msg["role"] == "user":
            if "livraison" in content:
                delivery_type = "Livraison"
            elif "emporter" in content or "à emporter" in content:
                delivery_type = "À emporter"
            elif "sur place" in content:
                delivery_type = "Sur place"

        # Détecter le paiement
        if msg["role"] == "user" and i > 0:
            prev_content = conversation[i - 1].get("content", "").lower()
            if "paiement" in prev_content or "espèce" in prev_content or "carte" in prev_content:
                if "carte" in content:
                    payment_method = "Carte bancaire"
                elif "espèce" in content:
                    payment_method = "Espèces"
                elif "ticket" in content:
                    payment_method = "Ticket restaurant"

    # Extraire les articles du récapitulatif final
    for msg in reversed(conversation):
        if msg["role"] == "assistant" and "END_CALL" in msg.get("content", ""):
            recap = msg["content"]

            # Extraire le total avec réduction
            reduction_match = re.search(
                r'total initial\s+(\d+(?:[.,]\d+)?)\s*€.*après réduction\s+(\d+(?:[.,]\d+)?)\s*€',
                recap.lower()
            )
            if reduction_match:
                initial_total = reduction_match.group(1).replace(',', '.') + " €"
                total = reduction_match.group(2).replace(',', '.') + " €"
                discount_info = " (réduction -10% appliquée)"
            else:
                total_match = re.search(r'total\s*:?\s*(\d+(?:[.,]\d+)?)\s*(?:euros?|€)', recap.lower())
                if total_match:
                    total = total_match.group(1).replace(',', '.') + " €"

            # Parser le récapitulatif pour les articles
            recap_clean = recap.replace("END_CALL", "").strip()

            if "Total" in recap_clean or "total" in recap_clean:
                recap_items = re.split(r'[Tt]otal', recap_clean)[0].strip()
            else:
                recap_items = recap_clean

            recap_items = re.split(r'[Mm]erci', recap_items)[0].strip()

            # Segments séparés par des points
            segments = recap_items.split('.')

            for segment in segments:
                segment = segment.strip()
                if not segment or len(segment) < 5:
                    continue

                skip_keywords = ['votre', 'sera', 'prêt', 'minute', 'merci', 'paiement',
                                 'espèces', 'carte', 'ticket', 'livraison au', 'emporter',
                                 'sur place', 'nom', 'téléphone', 'adresse']

                if any(keyword in segment.lower() for keyword in skip_keywords):
                    continue

                if segment:
                    order_items.append(segment[0].upper() + segment[1:])

            break

    # Construire le bon de commande
    bon = []
    bon.append("=" * 60)
    bon.append(f"         {RESTAURANT_NAME.upper()}")
    bon.append(f"           BON DE COMMANDE #{call_sid}")
    bon.append("=" * 60)
    bon.append(f"Date/Heure : {timestamp.strftime('%d/%m/%Y à %H:%M:%S')}")
    bon.append("")

    # Informations client
    bon.append("CLIENT :")
    bon.append(f"  Nom       : {client_name or 'Non renseigné'}")
    bon.append(f"  Téléphone : {client_phone or 'Non renseigné'}")
    if client_address:
        bon.append(f"  Adresse   : {client_address}")
    bon.append("")

    # Type de commande
    bon.append(f"TYPE : {delivery_type or 'Non renseigné'}")
    bon.append("")

    # Détails de la commande
    bon.append("COMMANDE :")
    bon.append("-" * 60)

    if order_items:
        for i, item in enumerate(order_items, 1):
            bon.append(f"  {i}. {item}")
    else:
        bon.append("  [Voir conversation pour détails]")

    bon.append("-" * 60)
    bon.append("")

    # Total
    if initial_total and discount_info:
        bon.append(f"SOUS-TOTAL : {initial_total}")
        bon.append(f"RÉDUCTION : -10% (à emporter)")
        bon.append(f"TOTAL : {total}")
    else:
        bon.append(f"TOTAL : {total}" if total else "TOTAL : Voir récapitulatif")
    bon.append("")

    # Paiement
    bon.append(f"PAIEMENT : {payment_method or 'Non renseigné'}")
    bon.append("")

    # Temps estimé
    if delivery_type:
        if "livraison" in delivery_type.lower():
            temps = RESTAURANT_DATA["services"]["livraison"]["temps"]
        elif "emporter" in delivery_type.lower():
            temps = RESTAURANT_DATA["services"]["emporter"]["temps"]
        else:
            temps = RESTAURANT_DATA["services"]["sur_place"]["temps"]
        bon.append(f"TEMPS ESTIMÉ : {temps}")

    bon.append("")
    bon.append("=" * 60)
    bon.append(f"Contact : {RESTAURANT_DATA['info']['telephone']}")
    bon.append(f"Adresse : {RESTAURANT_DATA['info']['adresse']}")
    bon.append("=" * 60)

    return "\n".join(bon)


# ==================== ROUTES API ====================

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def home():
    """Page d'accueil / Health check"""
    cleanup_old_conversations()

    return jsonify({
        "status": "online",
        "restaurant": RESTAURANT_NAME,
        "active_conversations": len(conversations),
        "ai_enabled": client is not None,
        "menu_items": len(MENU_DATA),
        "categories": len(get_all_categories()),
        "version": "2.0-CSV"
    })


@app.route("/api/stats", methods=["GET"])
def stats():
    """Statistiques du serveur"""
    cleanup_old_conversations()

    return jsonify({
        "restaurant": RESTAURANT_NAME,
        "conversations_actives": len(conversations),
        "total_messages": sum(len(conv) for conv in conversations.values()),
        "ai_status": "active" if client else "inactive",
        "menu_items_csv": len(MENU_DATA),
        "categories": get_all_categories()
    })


@app.route("/api/menu", methods=["GET"])
def get_menu():
    """Retourne le menu depuis le CSV"""
    return jsonify({
        "restaurant": RESTAURANT_NAME,
        "total_items": len(MENU_DATA),
        "categories": get_all_categories(),
        "items": MENU_DATA[:20]  # Premiers 20 items
    })


@app.route("/api/search", methods=["GET"])
def search_menu():
    """Recherche dans le menu CSV"""
    query = request.args.get("q", "")
    if not query:
        return jsonify({"error": "Paramètre 'q' requis"}), 400

    results = search_items(query)
    return jsonify({
        "query": query,
        "results": results
    })


@app.route("/api/conversations", methods=["GET"])
def get_conversations():
    """Liste toutes les conversations actives"""
    cleanup_old_conversations()

    conversations_list = []
    for call_sid, conv in conversations.items():
        conversations_list.append({
            "call_sid": call_sid,
            "messages": len(conv),
            "last_activity": conv[-1]["time"].isoformat() if conv else None
        })

    return jsonify(conversations_list)


@app.route("/clear", methods=["POST"])
def clear():
    """Efface toutes les conversations"""
    global conversations
    count = len(conversations)
    conversations.clear()
    print(f"🗑️  {count} conversation(s) effacée(s)")

    return jsonify({
        "cleared": True,
        "count": count
    })


# ==================== MIDDLEWARE ====================

@app.after_request
def after_request(response):
    """Nettoyage automatique après chaque requête"""
    if not hasattr(app, 'request_count'):
        app.request_count = 0

    app.request_count += 1

    # Nettoyer toutes les 10 requêtes
    if app.request_count % 10 == 0:
        cleanup_old_conversations()

    return response


# ==================== LANCEMENT ====================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🍔 AGENT IA RESTAURANT - SYSTÈME VOCAL INTELLIGENT (CSV)")
    print("=" * 60)
    print(f"🏪 Restaurant: {RESTAURANT_NAME}")
    print(f"🤖 IA: {'✅ Active (OpenAI)' if client else '❌ Inactive'}")
    print(f"🧠 Mémoire: {MEMORY_TIMEOUT // 60} minutes")
    print(f"📊 Articles CSV: {len(MENU_DATA)}")
    print(f"📂 Catégories: {len(get_all_categories())}")
    print(f"🌐 URL locale: http://localhost:5000")
    print(f"📞 Webhook: http://votre-ngrok.com/voice")
    print("=" * 60)
    print("\n🚀 Serveur démarré - En attente d'appels...\n")

    app.run(debug=True, port=5000, host="0.0.0.0")